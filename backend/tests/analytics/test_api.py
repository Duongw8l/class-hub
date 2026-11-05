"""Ba endpoint số liệu: ma trận phân quyền 4 vai trò, nội dung, kiểu dữ liệu và nhật ký (D-053).

Tài khoản (xem README): gvcn.11a2 chỉ chủ nhiệm 11A2; gv.toan.11 chủ nhiệm 11A1 và dạy Toán ở 11A1,
11A2, 11A3 (cộng dồn); gv.van.11 dạy Văn ở cả 3 lớp 11; gv.toan.12 chủ nhiệm 12A1; bgh1 là BGH;
admin là Admin.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AuditLog, User
from app.auth.tokens import create_access_token
from app.core.enums import AuditAction

pytestmark = pytest.mark.db

Headers = Callable[[str], dict[str, str]]
ClassId = Callable[[str], int]
SubjectId = Callable[[str], int]

FORBIDDEN = {"detail": "Bạn không có quyền truy cập dữ liệu này."}


def get(client: TestClient, url: str, headers: dict[str, str] | None = None) -> Any:
    return client.get(url, headers=headers or {})


# --- Dashboard lớp -------------------------------------------------------------------------------

DASHBOARD_ALLOWED = [
    ("gvcn.11a2@example.com", "11A2"),  # GVCN thuần, lớp mình
    ("gv.toan.11@example.com", "11A1"),  # cộng dồn: lớp chủ nhiệm
    ("bgh1@example.com", "11A2"),
    ("bgh1@example.com", "12A3"),
]
DASHBOARD_DENIED = [
    ("gvcn.11a2@example.com", "11A3"),  # GVCN lớp khác cùng khối
    ("gvcn.11a2@example.com", "10A1"),
    ("gv.toan.11@example.com", "11A2"),  # cộng dồn: lớp chỉ dạy Toán, không phải cả lớp
    ("gv.van.11@example.com", "11A2"),  # GVBM thuần
    ("gv.van.11@example.com", "11A1"),
    ("admin@example.com", "11A2"),
]


@pytest.mark.parametrize(("email", "class_name"), DASHBOARD_ALLOWED)
def test_dashboard_allowed(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, email: str, class_name: str
) -> None:
    url = f"/api/v1/classes/{class_id_of(class_name)}/dashboard"
    response = get(api_client, url, auth_headers(email))

    assert response.status_code == 200
    body = response.json()
    assert body["class_info"]["name"] == class_name
    assert body["student_count"] == 40


@pytest.mark.parametrize(("email", "class_name"), DASHBOARD_DENIED)
def test_dashboard_denied(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, email: str, class_name: str
) -> None:
    url = f"/api/v1/classes/{class_id_of(class_name)}/dashboard"
    response = get(api_client, url, auth_headers(email))

    assert response.status_code == 403
    assert response.json() == FORBIDDEN


def test_dashboard_content_for_class_11a2(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId
) -> None:
    url = f"/api/v1/classes/{class_id_of('11A2')}/dashboard?semester=1"
    body = get(api_client, url, auth_headers("gvcn.11a2@example.com")).json()

    assert body["period"] == "1"
    assert set(body["learning_levels"]) == {"good", "fair", "pass", "fail", "incomplete"}
    assert set(body["conduct_levels"]) == {"good", "fair", "pass", "fail", "missing"}
    assert sum(body["learning_levels"].values()) == 40
    assert body["promotion"] is None
    codes = {a["student_code"]: a for a in body["attention"]}
    assert "absent_notice" in codes["HS1102001"]["reasons"]  # em An nghỉ 38 buổi
    assert "subject_below_fail" in codes["HS1102002"]["reasons"]  # Toán 3,0
    assert "guardian_name" not in str(body) and "guardian_phone" not in str(body)
    toan = next(s for s in body["subjects"] if s["name"] == "Toán")
    assert isinstance(toan["mean"], float)  # số, không phải chuỗi
    assert toan["below_fail"] >= 1


def test_dashboard_for_the_whole_year_adds_promotion_counts(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId
) -> None:
    url = f"/api/v1/classes/{class_id_of('12A1')}/dashboard?semester=year"
    body = get(api_client, url, auth_headers("gv.toan.12@example.com")).json()

    promotion = body["promotion"]
    assert promotion["eligible"] + promotion["not_eligible"] + promotion["unknown"] == 40
    assert body["absent_over_limit_students"] >= 1  # HS1201003 nghỉ 46 buổi
    assert body["absent_notice_students"] >= body["absent_over_limit_students"]


@pytest.mark.parametrize("semester", ["0", "3", "ca-nam", ""])
def test_dashboard_rejects_an_unknown_semester(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, semester: str
) -> None:
    url = f"/api/v1/classes/{class_id_of('11A2')}/dashboard?semester={semester}"

    assert get(api_client, url, auth_headers("bgh1@example.com")).status_code == 422


def test_dashboard_of_a_missing_class_is_403_for_teachers_and_404_for_principal(
    api_client: TestClient, auth_headers: Headers
) -> None:
    url = "/api/v1/classes/999999/dashboard"

    for email in ("gvcn.11a2@example.com", "gv.van.11@example.com", "admin@example.com"):
        assert get(api_client, url, auth_headers(email)).status_code == 403
    assert get(api_client, url, auth_headers("bgh1@example.com")).status_code == 404


# --- Bảng điểm một môn ---------------------------------------------------------------------------

SCORES_ALLOWED = [
    ("gv.toan.11@example.com", "11A2", "Toán"),  # GVBM đúng lớp-môn (cộng dồn với chủ nhiệm 11A1)
    ("gv.van.11@example.com", "11A2", "Ngữ văn"),
    ("gvcn.11a2@example.com", "11A2", "Toán"),  # GVCN xem mọi môn của lớp mình
    ("gvcn.11a2@example.com", "11A2", "Giáo dục thể chất"),
    ("bgh1@example.com", "11A2", "Toán"),
]
SCORES_DENIED = [
    ("gv.toan.11@example.com", "11A2", "Ngữ văn"),  # đúng lớp, sai môn
    ("gv.van.11@example.com", "11A2", "Toán"),
    ("gv.van.11@example.com", "10A2", "Ngữ văn"),  # đúng môn, sai khối
    ("gvcn.11a2@example.com", "11A3", "Toán"),  # lớp khác
    ("admin@example.com", "11A2", "Toán"),
]


@pytest.mark.parametrize(("email", "class_name", "subject"), SCORES_ALLOWED)
def test_subject_scores_allowed(
    api_client: TestClient,
    auth_headers: Headers,
    class_id_of: ClassId,
    subject_id_of: SubjectId,
    email: str,
    class_name: str,
    subject: str,
) -> None:
    url = f"/api/v1/classes/{class_id_of(class_name)}/subjects/{subject_id_of(subject)}/scores"
    response = get(api_client, url, auth_headers(email))

    assert response.status_code == 200
    assert response.json()["subject"]["name"] == subject
    assert len(response.json()["rows"]) == 40


@pytest.mark.parametrize(("email", "class_name", "subject"), SCORES_DENIED)
def test_subject_scores_denied(
    api_client: TestClient,
    auth_headers: Headers,
    class_id_of: ClassId,
    subject_id_of: SubjectId,
    email: str,
    class_name: str,
    subject: str,
) -> None:
    url = f"/api/v1/classes/{class_id_of(class_name)}/subjects/{subject_id_of(subject)}/scores"
    response = get(api_client, url, auth_headers(email))

    assert response.status_code == 403
    assert response.json() == FORBIDDEN


def test_subject_scores_content_for_the_boundary_students(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, subject_id_of: SubjectId
) -> None:
    url = (
        f"/api/v1/classes/{class_id_of('12A1')}/subjects/{subject_id_of('Toán')}/scores?semester=1"
    )
    body = get(api_client, url, auth_headers("gv.toan.12@example.com")).json()

    rows = {r["student_code"]: r for r in body["rows"]}
    assert body["semester"] == 1
    assert body["subject"]["regular_required"] == 4  # Toán 105 tiết
    assert body["thresholds"] == {"fail": 3.5, "passing": 5.0, "fair": 6.5, "good": 8.0}
    for code, value in (("HS1201004", 3.4), ("HS1201005", 3.5), ("HS1201006", 5.0)):
        row = rows[code]
        assert row["average"] == value and isinstance(row["average"], float)
        assert row["year_average"] == value  # hai học kỳ bằng nhau thì cả năm bằng chính giá trị đó
        assert row["tx"] == [value] * 4 and row["midterm"] == value and row["final"] == value
        assert row["complete"] is True and row["tx_missing"] == 0
    distribution = body["distribution"]
    assert sum(distribution.values()) == 40
    assert distribution["below_fail"] >= 1  # HS1201004
    assert body["incomplete_count"] == 0


def test_comment_subject_has_results_but_no_averages(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, subject_id_of: SubjectId
) -> None:
    url = (
        f"/api/v1/classes/{class_id_of('11A2')}"
        f"/subjects/{subject_id_of('Giáo dục thể chất')}/scores?semester=2"
    )
    body = get(api_client, url, auth_headers("gvcn.11a2@example.com")).json()

    assert body["subject"]["assessment_type"] == "comment"
    assert body["mean"] is None
    assert all(r["average"] is None and r["tx"] == [] for r in body["rows"])
    assert {r["comment_result"] for r in body["rows"]} <= {"pass", "fail"}
    assert body["comment_fail_count"] == sum(r["comment_result"] == "fail" for r in body["rows"])


def test_subject_not_taught_in_the_class_is_404_for_those_allowed_to_ask(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, subject_id_of: SubjectId
) -> None:
    # 11A1 học Vật lí, Hóa học, Địa lí, Tin học; không học Âm nhạc.
    url = f"/api/v1/classes/{class_id_of('11A1')}/subjects/{subject_id_of('Âm nhạc')}/scores"

    assert get(api_client, url, auth_headers("gv.toan.11@example.com")).status_code == 404  # GVCN
    assert get(api_client, url, auth_headers("bgh1@example.com")).status_code == 404
    assert get(api_client, url, auth_headers("gv.van.11@example.com")).status_code == 403


def test_subject_scores_rejects_a_bad_semester_and_unknown_class(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, subject_id_of: SubjectId
) -> None:
    headers = auth_headers("bgh1@example.com")
    base = f"/api/v1/classes/{class_id_of('11A2')}/subjects/{subject_id_of('Toán')}/scores"

    assert get(api_client, f"{base}?semester=3", headers).status_code == 422
    assert get(api_client, f"{base}?semester=year", headers).status_code == 422
    missing = f"/api/v1/classes/999999/subjects/{subject_id_of('Toán')}/scores"
    assert get(api_client, missing, headers).status_code == 404


# --- Tổng quan khối -------------------------------------------------------------------------------


def test_grade_overview_compares_the_three_classes(
    api_client: TestClient, auth_headers: Headers
) -> None:
    response = get(
        api_client, "/api/v1/grades/12/overview?semester=year", auth_headers("bgh1@example.com")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grade_level"] == 12 and body["period"] == "year"
    assert [c["name"] for c in body["classes"]] == ["12A1", "12A2", "12A3"]
    assert sum(c["student_count"] for c in body["classes"]) == 120
    assert all(sum(c["learning_levels"].values()) == 40 for c in body["classes"])
    assert body["classes"][0]["absent_over_limit_students"] >= 1  # 12A1 có HS nghỉ 46 buổi
    subjects = {s["name"]: s for s in body["subjects"]}
    assert "Toán" in subjects and "Ngữ văn" in subjects
    assert len(subjects["Toán"]["class_means"]) == 3 and subjects["Toán"]["class_count"] == 3
    assert all(isinstance(m["mean"], float) for m in subjects["Toán"]["class_means"])
    # Mọi môn của khối (D-116): môn lựa chọn chỉ một tổ hợp học vẫn có, chỉ với lớp học môn đó.
    music = subjects["Âm nhạc"]
    assert music["assessment_type"] == "comment" and music["class_count"] == 1
    [only] = music["class_means"]
    assert only["mean"] is None and only["comment_pass"] + only["comment_fail"] > 0
    # Môn điểm số đứng trước môn nhận xét.
    kinds = [s["assessment_type"] for s in body["subjects"]]
    assert kinds == sorted(kinds, key=lambda kind: kind != "score")


def test_grade_overview_adds_promotion_counts_for_the_whole_year_only(
    api_client: TestClient, auth_headers: Headers
) -> None:
    headers = auth_headers("bgh1@example.com")
    year = get(api_client, "/api/v1/grades/12/overview?semester=year", headers).json()
    first = get(api_client, "/api/v1/grades/12/overview?semester=1", headers).json()

    assert all(c["promotion"] is None for c in first["classes"])
    for item in year["classes"]:
        promotion = item["promotion"]
        assert sum(promotion.values()) == item["student_count"]
        # Cùng số với dashboard lớp: một nguồn tính duy nhất trong Analytics.
        dashboard = get(
            api_client, f"/api/v1/classes/{item['class_id']}/dashboard?semester=year", headers
        ).json()
        assert promotion == dashboard["promotion"]


@pytest.mark.parametrize(
    "email",
    [
        "gvcn.11a2@example.com",
        "gv.toan.12@example.com",  # GVCN 12A1, cũng không có quyền cấp khối
        "gv.van.11@example.com",
        "admin@example.com",
    ],
)
def test_grade_overview_is_for_principal_only(
    api_client: TestClient, auth_headers: Headers, email: str
) -> None:
    response = get(api_client, "/api/v1/grades/11/overview", auth_headers(email))

    assert response.status_code == 403
    assert response.json() == FORBIDDEN


def test_grade_overview_of_a_nonexistent_grade(
    api_client: TestClient, auth_headers: Headers
) -> None:
    assert (
        get(api_client, "/api/v1/grades/9/overview", auth_headers("bgh1@example.com")).status_code
        == 404
    )
    assert (
        get(
            api_client, "/api/v1/grades/9/overview", auth_headers("gvcn.11a2@example.com")
        ).status_code
        == 403
    )


# --- Học sinh cần hỗ trợ trong một môn (D-118) ----------------------------------------------------

SUPPORT_ALLOWED = [
    ("gv.van.11@example.com", "11A2", "Ngữ văn"),  # GVBM đúng lớp-môn
    ("gv.toan.11@example.com", "11A2", "Toán"),
    ("gvcn.11a2@example.com", "11A2", "Toán"),  # GVCN: mọi môn của lớp mình
    ("bgh1@example.com", "11A2", "Ngữ văn"),
]
SUPPORT_DENIED = [
    ("gv.van.11@example.com", "11A2", "Toán"),  # môn không dạy
    ("gv.van.11@example.com", "10A1", "Ngữ văn"),  # lớp không dạy
    ("gvcn.11a2@example.com", "11A3", "Toán"),  # lớp khác
    ("admin@example.com", "11A2", "Toán"),
]


@pytest.mark.parametrize(("email", "class_name", "subject"), SUPPORT_ALLOWED)
def test_subject_support_allowed(
    api_client: TestClient,
    auth_headers: Headers,
    class_id_of: ClassId,
    subject_id_of: SubjectId,
    email: str,
    class_name: str,
    subject: str,
) -> None:
    url = (
        f"/api/v1/classes/{class_id_of(class_name)}/subjects/{subject_id_of(subject)}"
        "/support?semester=1"
    )
    response = get(api_client, url, auth_headers(email))

    assert response.status_code == 200
    body = response.json()
    assert body["semester"] == 1 and body["subject"]["name"] == subject
    assert sum(body["counts"].values()) == len(body["students"])
    for student in body["students"]:
        assert student["reasons"] and student["level"] == student["reasons"][0]["level"]
        # Chỉ điểm môn này: không có chuyên cần, rèn luyện hay thông tin phụ huynh.
        assert set(student) == {
            "student_id",
            "student_code",
            "full_name",
            "level",
            "reasons",
            "average",
            "average_semester1",
            "comment_result",
        }


@pytest.mark.parametrize(("email", "class_name", "subject"), SUPPORT_DENIED)
def test_subject_support_denied(
    api_client: TestClient,
    auth_headers: Headers,
    class_id_of: ClassId,
    subject_id_of: SubjectId,
    email: str,
    class_name: str,
    subject: str,
) -> None:
    url = f"/api/v1/classes/{class_id_of(class_name)}/subjects/{subject_id_of(subject)}/support"
    response = get(api_client, url, auth_headers(email))

    assert response.status_code == 403
    assert response.json() == FORBIDDEN


def test_subject_support_matches_the_score_table(
    api_client: TestClient, auth_headers: Headers, class_id_of: ClassId, subject_id_of: SubjectId
) -> None:
    headers = auth_headers("gv.toan.11@example.com")
    base = f"/api/v1/classes/{class_id_of('11A2')}/subjects/{subject_id_of('Toán')}"
    support = get(api_client, f"{base}/support?semester=1", headers).json()
    scores = get(api_client, f"{base}/scores?semester=1", headers).json()

    below = {
        r["student_id"] for r in scores["rows"] if r["average"] is not None and r["average"] < 5
    }
    flagged = {
        s["student_id"]
        for s in support["students"]
        if {r["code"] for r in s["reasons"]} & {"average_below_fail", "average_below_pass"}
    }
    assert flagged == below
    assert support["mean"] == scores["mean"]
    assert support["stats"]["support_group"] == len(below)


def test_my_support_lists_every_class_subject_i_teach_and_nothing_else(
    api_client: TestClient, auth_headers: Headers
) -> None:
    body = get(api_client, "/api/v1/me/support", auth_headers("gv.van.11@example.com")).json()

    pairs = [(i["class_info"]["name"], i["subject"]["name"]) for i in body["items"]]
    assert pairs == [("11A1", "Ngữ văn"), ("11A2", "Ngữ văn"), ("11A3", "Ngữ văn")]
    assert all(i["semester"] in (1, 2) for i in body["items"])


@pytest.mark.parametrize("email", ["bgh1@example.com", "admin@example.com"])
def test_my_support_is_empty_for_non_teachers(
    api_client: TestClient, auth_headers: Headers, email: str
) -> None:
    response = get(api_client, "/api/v1/me/support", auth_headers(email))
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_my_support_is_audited_per_class_subject(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    get(api_client, "/api/v1/me/support?semester=1", auth_headers("gv.van.11@example.com"))

    rows = [r for r in audit(db_session) if (r.details or {}).get("view") == "support"]
    assert len(rows) == 3
    assert all(r.action is AuditAction.VIEW_SUBJECT_SCORES for r in rows)


# --- Xác thực -------------------------------------------------------------------------------------


def test_all_three_endpoints_require_login(
    api_client: TestClient, db_session: Session, class_id_of: ClassId, subject_id_of: SubjectId
) -> None:
    admin_id = db_session.scalar(select(User.id).where(User.email == "admin@example.com"))
    assert admin_id is not None
    expired, _ = create_access_token(admin_id, now=datetime.now(UTC) - timedelta(hours=3))
    urls = [
        f"/api/v1/classes/{class_id_of('11A2')}/dashboard",
        f"/api/v1/classes/{class_id_of('11A2')}/subjects/{subject_id_of('Toán')}/scores",
        "/api/v1/grades/11/overview",
        f"/api/v1/classes/{class_id_of('11A2')}/subjects/{subject_id_of('Toán')}/support",
        "/api/v1/me/support",
    ]

    for url in urls:
        assert get(api_client, url).status_code == 401
        assert get(api_client, url, {"Authorization": f"Bearer {expired}"}).status_code == 401
        assert get(api_client, url, {"Authorization": "Bearer rac"}).status_code == 401


# --- Nhật ký --------------------------------------------------------------------------------------


def audit(session: Session) -> list[AuditLog]:
    return list(session.scalars(select(AuditLog).order_by(AuditLog.id)))


def test_dashboard_and_scores_are_logged_but_denials_and_grade_overview_are_not(
    api_client: TestClient,
    auth_headers: Headers,
    db_session: Session,
    class_id_of: ClassId,
    subject_id_of: SubjectId,
) -> None:
    eleven_a2 = class_id_of("11A2")
    toan = subject_id_of("Toán")
    assert audit(db_session) == []

    # Bị từ chối, 404 và tổng quan khối (chỉ số liệu gộp, không tên học sinh): không ghi
    get(api_client, f"/api/v1/classes/{eleven_a2}/dashboard", auth_headers("gv.van.11@example.com"))
    get(api_client, "/api/v1/classes/999999/dashboard", auth_headers("bgh1@example.com"))
    get(api_client, "/api/v1/grades/11/overview", auth_headers("bgh1@example.com"))
    assert audit(db_session) == []

    get(
        api_client,
        f"/api/v1/classes/{eleven_a2}/dashboard?semester=2",
        auth_headers("bgh1@example.com"),
    )
    get(
        api_client,
        f"/api/v1/classes/{eleven_a2}/subjects/{toan}/scores?semester=1",
        auth_headers("gv.toan.11@example.com"),
    )

    dashboard_row, scores_row = audit(db_session)
    assert dashboard_row.action is AuditAction.VIEW_CLASS_DASHBOARD
    assert dashboard_row.class_id == eleven_a2
    assert dashboard_row.details == {"semester": "2", "student_count": 40}
    assert scores_row.action is AuditAction.VIEW_SUBJECT_SCORES
    assert scores_row.class_id == eleven_a2
    assert scores_row.details == {"subject_id": toan, "semester": 1, "student_count": 40}
