"""Nhập giáo viên từ tệp (chỉ Admin, D-110): phân quyền 4 vai trò, kiểm dòng, an toàn mật khẩu."""

import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import AuditLog, User, UserImportJob
from app.auth.user_import import USER_IMPORT_FIELDS, parse_user_role, validate_users
from app.core.enums import AuditAction, ImportStatus, UserRole
from app.core.security import verify_password
from app.imports.columns import resolve_mapping
from app.imports.parsing import table_from_grid

pytestmark = pytest.mark.db

API = "/api/v1"
ADMIN = "admin@example.com"
NON_ADMINS = [
    "bgh1@example.com",
    "gvcn.11a2@example.com",
    "gv.van.11@example.com",
    "gv.toan.10@example.com",
]
Headers = Callable[[str], dict[str, str]]
HEADER = ["Họ và tên", "Email", "Vai trò"]
VALID_ROWS = [
    ["Nguyễn Văn An", "import.an@truonghoc.local", "Giáo viên"],
    ["Trần Thị Bình", "import.binh@truonghoc.local", "Ban giám hiệu"],
    ["Lê Hoàng Cường", "import.cuong@truonghoc.local", ""],
]


def csv_bytes(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    buffer.write(",".join(HEADER) + "\r\n")
    for row in rows:
        buffer.write(",".join(row) + "\r\n")
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def preview(
    client: TestClient, headers: dict[str, str], rows: list[list[str]], name: str = "gv.csv"
) -> object:
    return client.post(
        f"{API}/admin/users/import",
        headers=headers,
        files={"file": (name, csv_bytes(rows), "text/csv")},
    )


def confirm(client: TestClient, headers: dict[str, str], job_id: str) -> object:
    return client.post(f"{API}/admin/users/import/{job_id}/confirm", headers=headers)


# --- Logic thuần: parse_user_role và validate_users ---------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", UserRole.TEACHER),
        ("Giáo viên", UserRole.TEACHER),
        ("giao vien", UserRole.TEACHER),
        ("GV", UserRole.TEACHER),
        ("Ban giám hiệu", UserRole.PRINCIPAL),
        ("BGH", UserRole.PRINCIPAL),
        ("Hiệu trưởng", UserRole.PRINCIPAL),
        ("admin", None),
        ("Quản trị", None),
        ("linh tinh", None),
    ],
)
def test_parse_user_role(text: str, expected: UserRole | None) -> None:
    assert parse_user_role(text) is expected


def _validate(rows: list[list[str]], existing: frozenset[str] = frozenset()):
    table = table_from_grid([HEADER, *rows], 1)
    mapping = resolve_mapping(table.headers, USER_IMPORT_FIELDS).mapping
    return validate_users(table, mapping, existing_emails=existing)


def test_valid_rows_are_new_with_parsed_roles() -> None:
    results = _validate(VALID_ROWS)
    assert [r.status for r in results] == ["ok", "ok", "ok"]
    assert [r.action for r in results] == ["new", "new", "new"]
    assert [r.role for r in results] == [UserRole.TEACHER, UserRole.PRINCIPAL, UserRole.TEACHER]


def test_each_rule_flags_its_row() -> None:
    rows = [
        ["", "import.a@truonghoc.local", "Giáo viên"],  # thiếu tên
        ["Có Tên", "", "Giáo viên"],  # thiếu email
        ["Có Tên", "khong-hop-le", "Giáo viên"],  # email sai
        ["Có Tên", "import.b@truonghoc.local", "Sếp tổng"],  # vai trò không hợp lệ
        ["X" * 101, "import.c@truonghoc.local", ""],  # tên quá dài
    ]
    results = _validate(rows)
    assert all(r.status == "error" for r in results)
    assert "Thiếu họ và tên" in results[0].messages[0].message
    assert "Thiếu email" in results[1].messages[0].message
    assert "không hợp lệ" in results[2].messages[0].message
    assert "Vai trò" in results[3].messages[0].message
    assert "dài quá" in results[4].messages[0].message


def test_duplicate_email_in_file_flags_the_second_row() -> None:
    rows = [
        ["Người Một", "trung@truonghoc.local", "Giáo viên"],
        ["Người Hai", "TRUNG@truonghoc.local", "Giáo viên"],  # trùng, khác hoa thường
    ]
    results = _validate(rows)
    assert results[0].status == "ok"
    assert results[1].status == "error" and "trùng" in results[1].messages[0].message


def test_email_already_in_db_is_an_error() -> None:
    rows = [["Người Mới", "da.co@truonghoc.local", "Giáo viên"]]
    results = _validate(rows, existing=frozenset({"da.co@truonghoc.local"}))
    assert results[0].status == "error" and "đã có tài khoản" in results[0].messages[0].message


# --- Phân quyền -------------------------------------------------------------------------------


@pytest.mark.parametrize("email", NON_ADMINS)
def test_non_admin_cannot_preview_and_creates_nothing(
    api_client: TestClient, auth_headers: Headers, db_session: Session, email: str
) -> None:
    users_before = db_session.scalar(select(func.count()).select_from(User))
    response = preview(api_client, auth_headers(email), VALID_ROWS)
    assert response.status_code == 403
    assert db_session.scalar(select(func.count()).select_from(User)) == users_before


def test_unauthenticated_gets_401(api_client: TestClient) -> None:
    assert preview(api_client, {}, VALID_ROWS).status_code == 401
    assert confirm(api_client, {}, "00000000-0000-0000-0000-000000000000").status_code == 401


def test_non_admin_cannot_confirm_admin_job(api_client: TestClient, auth_headers: Headers) -> None:
    job_id = preview(api_client, auth_headers(ADMIN), VALID_ROWS).json()["job_id"]
    assert confirm(api_client, auth_headers("bgh1@example.com"), job_id).status_code == 403


# --- Luồng xem trước và xác nhận trên DB -------------------------------------------------------


def test_preview_creates_no_users_then_confirm_creates_them(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    users_before = db_session.scalar(select(func.count()).select_from(User))

    body = preview(api_client, headers, VALID_ROWS).json()
    assert body["summary"]["error_rows"] == 0
    assert body["summary"]["new_rows"] == 3 and body["can_confirm"] is True
    assert db_session.scalar(select(func.count()).select_from(User)) == users_before  # chưa tạo

    result = confirm(api_client, headers, body["job_id"]).json()
    assert result["created"] == 3 and len(result["credentials"]) == 3
    assert db_session.scalar(select(func.count()).select_from(User)) == (users_before or 0) + 3

    # Tài khoản mới hoạt động và vai trò đúng.
    created = {c["email"]: c for c in result["credentials"]}
    binh = db_session.scalar(select(User).where(User.email == "import.binh@truonghoc.local"))
    assert binh is not None and binh.is_active and binh.role is UserRole.PRINCIPAL
    assert created["import.an@truonghoc.local"]["role"] == "teacher"


def test_created_teacher_can_log_in_with_temp_password(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    body = preview(api_client, auth_headers(ADMIN), VALID_ROWS).json()
    result = confirm(api_client, auth_headers(ADMIN), body["job_id"]).json()
    cred = next(c for c in result["credentials"] if c["email"] == "import.an@truonghoc.local")

    user = db_session.scalar(select(User).where(User.email == "import.an@truonghoc.local"))
    assert user is not None
    # Mật khẩu tạm khớp hash đã lưu (đăng nhập được); hash KHÔNG phải bản rõ.
    assert verify_password(cred["temporary_password"], user.password_hash)
    assert user.password_hash != cred["temporary_password"]


def test_password_is_never_stored_or_logged(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    body = preview(api_client, auth_headers(ADMIN), VALID_ROWS).json()
    result = confirm(api_client, auth_headers(ADMIN), body["job_id"]).json()
    passwords = [c["temporary_password"] for c in result["credentials"]]

    job = db_session.get(UserImportJob, body["job_id"])
    assert job is not None and job.rows == [] and job.status is ImportStatus.CONFIRMED

    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.IMPORT_USERS)
    ).all()
    assert len(audits) == 1
    audit = audits[0]
    detail_text = str(audit.details)
    assert audit.details["created"] == 3
    for password in passwords:
        assert password not in detail_text


def test_rows_with_errors_block_confirm_and_create_nothing(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    rows = [*VALID_ROWS, ["Thiếu Email", "", "Giáo viên"]]
    users_before = db_session.scalar(select(func.count()).select_from(User))

    body = preview(api_client, headers, rows).json()
    assert body["summary"]["error_rows"] == 1 and body["can_confirm"] is False

    assert confirm(api_client, headers, body["job_id"]).status_code == 422
    assert db_session.scalar(select(func.count()).select_from(User)) == users_before


def test_existing_seed_email_in_file_is_flagged(
    api_client: TestClient, auth_headers: Headers
) -> None:
    rows = [["Trùng Email", "gv.toan.11@example.com", "Giáo viên"]]
    body = preview(api_client, auth_headers(ADMIN), rows).json()
    assert body["summary"]["error_rows"] == 1 and body["can_confirm"] is False
    assert "đã có tài khoản" in body["rows"][0]["messages"][0]["message"]


def test_confirm_is_idempotent(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    body = preview(api_client, headers, VALID_ROWS).json()
    first = confirm(api_client, headers, body["job_id"]).json()
    assert first["created"] == 3 and len(first["credentials"]) == 3

    second = confirm(api_client, headers, body["job_id"]).json()
    assert second["already_confirmed"] is True
    assert second["created"] == 3 and second["credentials"] == []
    # Không tạo thêm lần hai.
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.email.like("import.%@truonghoc.local"))
        )
        == 3
    )


def test_expired_preview_cannot_be_confirmed(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    body = preview(api_client, headers, VALID_ROWS).json()
    job = db_session.get(UserImportJob, body["job_id"])
    assert job is not None
    job.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()

    assert confirm(api_client, headers, body["job_id"]).status_code == 410


def test_missing_required_column_gives_no_job(
    api_client: TestClient, auth_headers: Headers
) -> None:
    buffer = b"\xef\xbb\xbf" + "Tên,Ghi chú\r\nAi đó,abc\r\n".encode()
    response = api_client.post(
        f"{API}/admin/users/import",
        headers=auth_headers(ADMIN),
        files={"file": ("gv.csv", buffer, "text/csv")},
    )
    body = response.json()
    assert body["job_id"] is None and body["can_confirm"] is False
    assert "Email" in body["missing_required"]
