"""Nhập nhiều tài khoản giáo viên từ một tệp Excel/CSV (chỉ Admin).

Khác luồng nhập của Giai đoạn 4 (gắn với một lớp): đây là thao tác toàn trường, chỉ Admin, tạo
TÀI KHOẢN MỚI. Dùng lại các hàm thuần của `app/imports/` để đọc và ánh xạ cột, nhưng validate
riêng vì bản ghi là (họ tên, email, vai trò) chứ không phải học sinh.

Nguyên tắc: xem trước rồi mới xác nhận; còn dòng lỗi thì không tạo gì; mật khẩu tạm chỉ trả về một
lần trong phản hồi xác nhận, không bao giờ lưu vào DB hay nhật ký.
"""

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.admin_schemas import (
    EMAIL_PATTERN,
    CreatedCredentialOut,
    UserImportConfirmOut,
    UserImportFieldOut,
    UserImportMessageOut,
    UserImportPreviewOut,
    UserImportRowOut,
    UserImportSummaryOut,
)
from app.auth.audit import record_access
from app.auth.models import User, UserImportJob
from app.classes.models import Subject
from app.core.authorize import AuthorizationError, authorize_admin
from app.core.enums import AuditAction, ImportStatus, UserRole
from app.core.labels import label_vi
from app.core.security import generate_temporary_password, hash_password
from app.imports.columns import FieldSpec, detect_header_line, normalize_header, resolve_mapping
from app.imports.parsing import RawTable, read_grid, table_from_grid
from app.imports.validation import Message, _cell, _check_duplicate, _header, column_index

MAX_NAME_LENGTH = 100  # khớp users.full_name
MAX_EMAIL_LENGTH = 255  # khớp users.email
MAX_NOTE_LENGTH = 255  # khớp users.note
EMAIL_RE = re.compile(EMAIL_PATTERN)
JOB_TTL = timedelta(hours=24)
PREVIEW_ROW_LIMIT = 500  # số dòng "bình thường" tối đa trong bản xem trước; dòng lỗi luôn có đủ

# Vai trò cho phép tạo qua tệp: Giáo viên và Ban giám hiệu (không tạo admin qua tệp, D-110).
_TEACHER_ALIASES = frozenset({"giaovien", "gv", "teacher", "gvbm", "gvcn"})
_PRINCIPAL_ALIASES = frozenset(
    {"bangiamhieu", "bgh", "principal", "hieutruong", "phohieutruong", "banlanhdao"}
)

USER_IMPORT_FIELDS: list[FieldSpec] = [
    FieldSpec(
        "full_name",
        "Họ và tên",
        frozenset(
            {"hovaten", "hoten", "tengiaovien", "hotengiaovien", "fullname", "ten", "giaovien"}
        ),
    ),
    FieldSpec(
        "email",
        "Email",
        frozenset({"email", "thudientu", "diachiemail", "mail", "emailgiaovien", "hop thu"}),
    ),
    FieldSpec(
        "role",
        "Vai trò",
        frozenset({"vaitro", "role", "chucvu", "chucdanh", "vitri"}),
        required=False,
    ),
    FieldSpec(
        "specialty",
        "Bộ môn",
        frozenset({"bomon", "mon", "monhoc", "chuyenmon", "subject", "specialty", "mongiangday"}),
        required=False,
    ),
    FieldSpec(
        "note",
        "Ghi chú",
        frozenset({"ghichu", "note", "notes", "chuthich", "remark", "ghichu/chuthich"}),
        required=False,
    ),
]


class UserImportJobNotFound(Exception):
    """Không có bản xem trước này."""


class UserImportJobExpired(Exception):
    """Bản xem trước đã quá hạn 24 giờ: phải tải lại tệp."""


class UserImportJobInvalid(Exception):
    """Bản xem trước còn dòng lỗi: không được xác nhận."""


class UserImportConflict(Exception):
    """Một email trong tệp đã được tạo (bởi thao tác khác) từ lúc xem trước."""


def parse_user_role(text: str) -> UserRole | None:
    """Chuỗi vai trò trong tệp thành UserRole. Rỗng → Giáo viên. Admin/không hợp lệ → None."""
    key = normalize_header(text)
    if not key:
        return UserRole.TEACHER
    if key in _TEACHER_ALIASES:
        return UserRole.TEACHER
    if key in _PRINCIPAL_ALIASES:
        return UserRole.PRINCIPAL
    return None


_TEACHER_PREFIXES = ("giaovienmon", "giaovien", "gvmon", "gv")


def _teacher_with_subject(
    text: str, subjects_by_norm: Mapping[str, tuple[int, str]]
) -> tuple[int, str] | None:
    """'Giáo viên Toán' → (id, 'Toán'); không khớp môn nào trong danh mục → None."""
    key = normalize_header(text)
    for prefix in _TEACHER_PREFIXES:
        if key.startswith(prefix) and key[len(prefix) :] in subjects_by_norm:
            return subjects_by_norm[key[len(prefix) :]]
    return None


@dataclass
class UserRowResult:
    line: int
    full_name: str | None = None
    email: str | None = None
    role: UserRole | None = None
    # Nhãn nhận diện (không cấp quyền). specialty_subject_id null khi để trống/không khớp danh mục.
    specialty_subject_id: int | None = None
    specialty: str | None = None  # tên môn đã khớp (để hiện lại trong bản xem trước)
    note: str | None = None
    status: Literal["ok", "warning", "error"] = "ok"
    action: Literal["new"] | None = None
    messages: list[Message] = field(default_factory=list)

    def error(self, column: str | None, message: str) -> None:
        self.status = "error"
        self.messages.append(Message(column, message))

    def warn(self, column: str | None, message: str) -> None:
        # Cảnh báo không chặn xác nhận (khác lỗi); không hạ cấp một dòng đã lỗi.
        if self.status != "error":
            self.status = "warning"
        self.messages.append(Message(column, message))

    def finish(self) -> "UserRowResult":
        self.action = None if self.status == "error" else "new"
        return self


def _squash(text: str) -> str:
    return " ".join(text.split())


def validate_users(
    table: RawTable,
    mapping: Mapping[str, str | None],
    *,
    existing_emails: frozenset[str],
    subjects_by_norm: Mapping[str, tuple[int, str]],
) -> list[UserRowResult]:
    """Kiểm từng dòng. Thuần, không đụng DB: nhận sẵn email đã có và danh mục môn (đã chuẩn hoá)."""
    index = column_index(table.headers, mapping)
    name_column = _header(table.headers, index, "full_name", "Họ và tên")
    email_column = _header(table.headers, index, "email", "Email")
    role_column = _header(table.headers, index, "role", "Vai trò")
    specialty_column = _header(table.headers, index, "specialty", "Bộ môn")
    note_column = _header(table.headers, index, "note", "Ghi chú")
    seen_email: dict[str, int] = {}
    results: list[UserRowResult] = []
    for row in table.rows:
        result = UserRowResult(line=row.line)
        name = _squash(_cell(row, index, "full_name"))
        result.full_name = name or None
        email = _cell(row, index, "email").strip()
        result.email = email or None

        if not name:
            result.error(name_column, "Thiếu họ và tên.")
        elif len(name) > MAX_NAME_LENGTH:
            result.error(name_column, f"Họ và tên dài quá {MAX_NAME_LENGTH} ký tự.")

        if not email:
            result.error(email_column, "Thiếu email.")
        elif len(email) > MAX_EMAIL_LENGTH:
            result.error(email_column, f"Email dài quá {MAX_EMAIL_LENGTH} ký tự.")
        elif not EMAIL_RE.match(email):
            result.error(email_column, f"Email '{email}' không hợp lệ.")
        else:
            lowered = email.lower()
            _check_duplicate(result, seen_email, lowered, email_column, "Email")
            if lowered in existing_emails:
                result.error(email_column, f"Email '{email}' đã có tài khoản.")

        role_text = _cell(row, index, "role")
        role = parse_user_role(role_text)
        role_subject = None
        if role is None:
            # "Giáo viên Toán" / "GV Ngữ văn": vai trò Giáo viên kèm môn (D-112).
            role_subject = _teacher_with_subject(role_text, subjects_by_norm)
            if role_subject is not None:
                role = UserRole.TEACHER
        if role is None:
            result.error(
                role_column,
                f"Vai trò '{role_text}' không hợp lệ (nhận 'Giáo viên', 'Giáo viên <môn>' như "
                "'Giáo viên Toán', hoặc 'Ban giám hiệu').",
            )
        else:
            result.role = role

        # Bộ môn: chỉ là nhãn. Để trống thì bỏ qua; không khớp danh mục thì cảnh báo (không chặn),
        # tài khoản vẫn được tạo nhưng không gắn bộ môn.
        specialty_text = _squash(_cell(row, index, "specialty"))
        if role_subject is not None and not specialty_text:
            result.specialty_subject_id, result.specialty = role_subject
        elif specialty_text and role is UserRole.PRINCIPAL:
            result.warn(specialty_column, "Ban giám hiệu không có môn dạy; bỏ qua cột Bộ môn.")
        elif specialty_text:
            match = subjects_by_norm.get(normalize_header(specialty_text))
            if match is None:
                result.warn(
                    specialty_column,
                    f"Không có bộ môn '{specialty_text}' trong danh mục; sẽ tạo không gắn bộ môn.",
                )
            else:
                result.specialty_subject_id, result.specialty = match

        note = _squash(_cell(row, index, "note"))
        if len(note) > MAX_NOTE_LENGTH:
            result.warn(note_column, f"Ghi chú dài quá {MAX_NOTE_LENGTH} ký tự; đã cắt bớt.")
            note = note[:MAX_NOTE_LENGTH]
        result.note = note or None

        results.append(result.finish())
    return results


def purge_expired(session: Session) -> None:
    session.execute(delete(UserImportJob).where(UserImportJob.expires_at < datetime.now(UTC)))


def _summary(results: Sequence[UserRowResult]) -> UserImportSummaryOut:
    new_rows = sum(1 for r in results if r.action == "new")
    return UserImportSummaryOut(
        total_rows=len(results),
        error_rows=sum(1 for r in results if r.status == "error"),
        warning_rows=sum(1 for r in results if r.status == "warning"),
        new_rows=new_rows,
        has_changes=new_rows > 0,
    )


def _row_out(result: UserRowResult) -> UserImportRowOut:
    return UserImportRowOut(
        line=result.line,
        full_name=result.full_name,
        email=result.email,
        role=result.role,
        role_label=None if result.role is None else label_vi(result.role),
        specialty=result.specialty,
        note=result.note,
        status=result.status,
        action=result.action,
        messages=[
            UserImportMessageOut(column=m.column, message=m.message) for m in result.messages
        ],
    )


def _rows_for_preview(results: Sequence[UserRowResult]) -> tuple[list[UserImportRowOut], bool]:
    """Mọi dòng lỗi và cảnh báo, cộng dòng khác cho tới PREVIEW_ROW_LIMIT, theo thứ tự dòng."""
    flagged = [r for r in results if r.status != "ok"]
    room = max(0, PREVIEW_ROW_LIMIT - len(flagged))
    chosen = {id(r) for r in flagged}
    for result in results:
        if room == 0:
            break
        if id(result) not in chosen:
            chosen.add(id(result))
            room -= 1
    shown = [r for r in results if id(r) in chosen]
    return [_row_out(r) for r in shown], len(shown) < len(results)


def _emails_in(table: RawTable, mapping: Mapping[str, str | None]) -> list[str]:
    index = column_index(table.headers, mapping)
    emails = (_cell(row, index, "email").strip().lower() for row in table.rows)
    return sorted({email for email in emails if email})


def _existing_emails(session: Session, emails: Sequence[str]) -> frozenset[str]:
    if not emails:
        return frozenset()
    rows = session.execute(
        select(func.lower(User.email)).where(func.lower(User.email).in_(list(emails)))
    )
    return frozenset(email for (email,) in rows)


def _subjects_by_norm(session: Session) -> dict[str, tuple[int, str]]:
    """Danh mục môn, khoá theo tên đã chuẩn hoá, để khớp cột 'Bộ môn' trong tệp (không dấu/hoa)."""
    rows = session.execute(select(Subject.id, Subject.name))
    return {normalize_header(name): (sid, name) for sid, name in rows}


def create_preview(
    session: Session,
    admin: User,
    *,
    filename: str,
    data: bytes,
    mapping: Mapping[str, str | None] | None = None,
    header_row: int | None = None,
) -> UserImportPreviewOut:
    """Đọc, ánh xạ, kiểm tệp; lưu job. KHÔNG tạo tài khoản nào.

    Ném ImportFileError (parsing.py) khi tệp không đọc được; người gọi đổi thành HTTP.
    """
    purge_expired(session)
    grid = read_grid(filename, data)
    header_line = header_row or detect_header_line(grid, USER_IMPORT_FIELDS)
    table = table_from_grid(grid, header_line)
    resolution = resolve_mapping(table.headers, USER_IMPORT_FIELDS, explicit=mapping)

    field_out = [
        UserImportFieldOut(
            name=spec.name,
            label=spec.label,
            required=spec.required,
            column=resolution.mapping.get(spec.name),
        )
        for spec in USER_IMPORT_FIELDS
    ]
    common = {
        "file_name": filename,
        "header_line": header_line,
        "detected_columns": [h for h in table.headers if h],
        "fields": field_out,
        "missing_required": resolution.missing_required,
        "ignored_columns": resolution.ignored_columns,
        "notes": resolution.notes,
    }

    if resolution.missing_required:
        return UserImportPreviewOut(
            job_id=None,
            summary=_summary([]),
            can_confirm=False,
            expires_at=None,
            rows=[],
            truncated=False,
            **common,
        )

    existing = _existing_emails(session, _emails_in(table, resolution.mapping))
    results = validate_users(
        table,
        resolution.mapping,
        existing_emails=existing,
        subjects_by_norm=_subjects_by_norm(session),
    )
    summary = _summary(results)
    records = (
        []
        if summary.error_rows
        else [
            {
                "full_name": r.full_name,
                "email": r.email,
                "role": r.role.value,
                "specialty_subject_id": r.specialty_subject_id,
                "note": r.note,
            }
            for r in results
            if r.role is not None and r.full_name is not None and r.email is not None
        ]
    )
    job = UserImportJob(
        admin_id=admin.id,
        status=ImportStatus.PREVIEWED,
        file_name=filename[:255],
        summary=summary.model_dump(),
        rows=records,
        expires_at=datetime.now(UTC) + JOB_TTL,
    )
    session.add(job)
    session.commit()

    shown, truncated = _rows_for_preview(results)
    return UserImportPreviewOut(
        job_id=job.id,
        summary=summary,
        can_confirm=summary.error_rows == 0 and summary.total_rows > 0,
        expires_at=job.expires_at,
        rows=shown,
        truncated=truncated,
        **common,
    )


def _confirm_result(job: UserImportJob, *, already: bool) -> UserImportConfirmOut:
    created = int(job.summary.get("result", {}).get("created", 0))
    return UserImportConfirmOut(
        job_id=job.id,
        status=job.status,
        created=created,
        already_confirmed=already,
        credentials=[],
    )


def confirm_job(session: Session, admin: User, job_id: uuid.UUID) -> UserImportConfirmOut:
    """Tạo tài khoản của một bản xem trước. Trả danh sách mật khẩu tạm (chỉ lần này).

    Chỉ người tạo job được xác nhận, và quyền Admin được kiểm lại. Job được khoá (FOR UPDATE) nên
    hai lần bấm cùng lúc chỉ tạo một lần; xác nhận lại job đã xong trả kết quả cũ (không mật khẩu).
    """
    job = session.execute(
        select(UserImportJob).where(UserImportJob.id == job_id).with_for_update()
    ).scalar_one_or_none()
    if job is None:
        raise UserImportJobNotFound
    if job.admin_id != admin.id:
        raise AuthorizationError
    authorize_admin(admin)  # nhập giáo viên từ tệp chỉ dành cho Admin

    if job.status is ImportStatus.CONFIRMED:
        return _confirm_result(job, already=True)
    if job.expires_at <= datetime.now(UTC):
        raise UserImportJobExpired
    if job.summary.get("error_rows", 0) > 0:
        raise UserImportJobInvalid

    credentials: list[CreatedCredentialOut] = []
    try:
        created_users: list[tuple[User, str]] = []
        for record in job.rows:
            password = generate_temporary_password()
            user = User(
                email=record["email"].lower(),
                full_name=record["full_name"],
                role=UserRole(record["role"]),
                password_hash=hash_password(password),
                is_active=True,
                specialty_subject_id=record.get("specialty_subject_id"),
                note=record.get("note"),
            )
            session.add(user)
            created_users.append((user, password))
        session.flush()  # phát hiện email trùng (chỉ mục duy nhất) trước khi ghi nhật ký

        for user, password in created_users:
            credentials.append(
                CreatedCredentialOut(
                    full_name=user.full_name,
                    email=user.email,
                    role=user.role,
                    role_label=label_vi(user.role),
                    temporary_password=password,
                )
            )
        job.status = ImportStatus.CONFIRMED
        job.confirmed_at = datetime.now(UTC)
        job.summary = {**job.summary, "result": {"created": len(created_users)}}
        job.rows = []  # không giữ lại bản ghi sau khi đã tạo
        record_access(
            session,
            admin,
            AuditAction.IMPORT_USERS,
            class_id=None,
            details={
                "job_id": str(job.id),
                "created": len(created_users),
                "user_ids": [user.id for user, _ in created_users],
            },
            commit=False,
        )
        session.commit()
    except IntegrityError as error:  # email vừa bị tạo bởi thao tác khác
        session.rollback()
        raise UserImportConflict from error

    return UserImportConfirmOut(
        job_id=job.id,
        status=ImportStatus.CONFIRMED,
        created=len(credentials),
        already_confirmed=False,
        credentials=credentials,
    )
