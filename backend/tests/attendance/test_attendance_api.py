"""Điểm danh ngày, điểm danh theo tiết và đối chiếu (D-120): phân quyền 4 vai trò, vắng do nhà
trường cử đi không tính buổi nghỉ, lý do vắng, lịch sử, sổ theo tiết, đối chiếu.

Tài khoản seed: gvcn.11a2 chủ nhiệm 11A2; gv.van.11 dạy Ngữ văn 11A2; gv.toan.11 dạy Toán 11A2 và
chủ nhiệm 11A1; bgh1 là BGH; admin là Admin. Năm học seed 05/09/2026 đến 31/05/2027.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.academic import Attendance, Lesson
from app.classes.models import ClassStudent
from app.core.enums import AttendanceStatus
from app.imports.models import AttendanceChange

pytestmark = pytest.mark.db

API = "/api/v1"
HOMEROOM = "gvcn.11a2@example.com"
LITERATURE = "gv.van.11@example.com"
MATH = "gv.toan.11@example.com"
PRINCIPAL = "bgh1@example.com"
ADMIN = "admin@example.com"
DAY = date(2026, 10, 5)  # thứ Hai, trong năm học
Headers = Callable[[str], dict[str, str]]
Finder = Callable[[str], int]


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "Hôm nay" cố định cuối năm học để mọi ngày trong năm đều điểm danh được."""
    monkeypatch.setattr("app.attendance.router._today", lambda: date(2027, 5, 31))


@pytest.fixture
def ids(class_id_of: Finder, subject_id_of: Finder, db_session: Session) -> dict[str, int]:
    class_id = class_id_of("11A2")
    student_id, class_student_id = db_session.execute(
        select(ClassStudent.student_id, ClassStudent.id)
        .where(ClassStudent.class_id == class_id)
        .order_by(ClassStudent.student_id)
        .limit(1)
    ).one()
    return {
        "class": class_id,
        "student": student_id,
        "class_student": class_student_id,
        "literature": subject_id_of("Ngữ văn"),
        "math": subject_id_of("Toán"),
    }


def day_url(ids: dict[str, int], day: date = DAY) -> str:
    return f"{API}/classes/{ids['class']}/attendance/days/{day.isoformat()}"


def lesson_url(ids: dict[str, int], subject: str, day: date = DAY, number: int = 2) -> str:
    return (
        f"{API}/classes/{ids['class']}/subjects/{ids[subject]}/lessons/{day.isoformat()}/{number}"
    )


def year_of(client: TestClient, headers: dict[str, str], ids: dict[str, int]) -> dict[str, Any]:
    body = client.get(f"{API}/classes/{ids['class']}/attendance", headers=headers).json()
    row = next(r for r in body["rows"] if r["student_id"] == ids["student"])
    result: dict[str, Any] = row["year"]
    return result


def set_day(client: TestClient, ids: dict[str, int], status: str, **extra: Any) -> Any:
    return client.put(
        day_url(ids),
        headers=extra.pop("headers"),
        json={"entries": [{"student_id": ids["student"], "status": status, **extra}]},
    )


# --- Phân quyền ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "status", "can_edit"),
    [
        (HOMEROOM, 200, True),
        (PRINCIPAL, 200, False),
        (MATH, 403, None),  # dạy Toán ở lớp này nhưng không chủ nhiệm
        (LITERATURE, 403, None),
        (ADMIN, 403, None),
    ],
)
def test_who_may_view_daily_attendance(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    email: str,
    status: int,
    can_edit: bool | None,
) -> None:
    headers = auth_headers(email)
    month = api_client.get(f"{API}/classes/{ids['class']}/attendance", headers=headers)
    one_day = api_client.get(day_url(ids), headers=headers)

    assert month.status_code == status and one_day.status_code == status
    if can_edit is not None:
        assert month.json()["can_edit"] is can_edit and one_day.json()["can_edit"] is can_edit


@pytest.mark.parametrize("email", [PRINCIPAL, MATH, LITERATURE, ADMIN])
def test_only_the_homeroom_teacher_records_daily_attendance(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], email: str
) -> None:
    response = set_day(api_client, ids, "absent_excused", headers=auth_headers(email))
    assert response.status_code == 403


def test_unauthenticated_gets_401(api_client: TestClient, ids: dict[str, int]) -> None:
    assert api_client.get(f"{API}/classes/{ids['class']}/attendance").status_code == 401
    assert api_client.get(lesson_url(ids, "literature")).status_code == 401


# --- Điểm danh ngày ------------------------------------------------------------------------------


def test_month_view_lists_days_cells_and_year_totals(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int]
) -> None:
    body = api_client.get(
        f"{API}/classes/{ids['class']}/attendance?month=2026-10", headers=auth_headers(HOMEROOM)
    ).json()

    assert body["month"] == "2026-10" and body["months"][0] == "2026-09"
    assert body["limits"] == {"notice": 30, "high": 40, "maximum": 45}
    assert len(body["rows"]) == 40 and body["days"]
    assert all(d.startswith("2026-10") for d in body["days"])
    for row in body["rows"]:
        year = row["year"]
        assert year["absent_total"] == year["excused"] + year["unexcused"]
    assert sum(body["counts"].values()) == sum(1 for r in body["rows"] if r["year"]["level"])


def test_school_duty_is_not_counted_as_an_absence(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    headers = auth_headers(HOMEROOM)
    assert set_day(api_client, ids, "present", headers=headers).status_code in (200, 400)
    before = year_of(api_client, headers, ids)

    absent = set_day(api_client, ids, "absent_excused", reason="sick", headers=headers)
    assert absent.status_code == 200, absent.text
    after_absent = year_of(api_client, headers, ids)
    assert after_absent["absent_total"] == before["absent_total"] + 1

    duty = set_day(
        api_client,
        ids,
        "school_duty",
        reason="competition",
        note="Thi học sinh giỏi cấp tỉnh",
        headers=headers,
    )
    assert duty.status_code == 200, duty.text
    after_duty = year_of(api_client, headers, ids)
    assert after_duty["absent_total"] == before["absent_total"]  # không còn là buổi nghỉ
    assert after_duty["school_duty"] == before["school_duty"] + 1

    entry = next(e for e in duty.json()["entries"] if e["student_id"] == ids["student"])
    assert (entry["status"], entry["reason"], entry["note"]) == (
        "school_duty",
        "competition",
        "Thi học sinh giỏi cấp tỉnh",
    )
    # Lịch sử: hai lần đổi gần nhất của ngày này, mới nhất trước.
    history = [h for h in duty.json()["history"] if h["student_id"] == ids["student"]]
    assert [h["new_status"] for h in history[:2]] == ["school_duty", "absent_excused"]
    db_session.expire_all()
    stored = db_session.scalar(
        select(Attendance).where(
            Attendance.class_student_id == ids["class_student"], Attendance.date == DAY
        )
    )
    assert stored is not None and stored.status is AttendanceStatus.SCHOOL_DUTY
    # Hồ sơ học sinh cũng đếm riêng.
    profile = api_client.get(
        f"{API}/classes/{ids['class']}/students/{ids['student']}/profile?semester=year",
        headers=headers,
    ).json()
    assert profile["attendance"]["school_duty"] == after_duty["school_duty"]
    assert profile["attendance"]["absent_total"] == after_duty["absent_total"]


def test_saving_the_same_values_is_400_and_writes_no_history(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    headers = auth_headers(HOMEROOM)
    first = set_day(api_client, ids, "absent_unexcused", headers=headers)
    assert first.status_code == 200
    count = db_session.scalar(
        select(AttendanceChange.id)
        .where(AttendanceChange.class_student_id == ids["class_student"])
        .order_by(AttendanceChange.id.desc())
        .limit(1)
    )
    again = set_day(api_client, ids, "absent_unexcused", headers=headers)
    assert again.status_code == 400
    latest = db_session.scalar(
        select(AttendanceChange.id)
        .where(AttendanceChange.class_student_id == ids["class_student"])
        .order_by(AttendanceChange.id.desc())
        .limit(1)
    )
    assert latest == count


def test_saving_refreshes_alerts_of_the_class(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[int] = []
    monkeypatch.setattr("app.imports.hooks.on_data_changed", called.append)
    set_day(api_client, ids, "present", headers=auth_headers(HOMEROOM))
    response = set_day(api_client, ids, "absent_unexcused", headers=auth_headers(HOMEROOM))
    assert response.status_code == 200
    assert called and called[-1] == ids["class"]


@pytest.mark.parametrize(
    ("entry", "day", "fragment"),
    [
        ({"status": "present", "reason": "sick"}, DAY, "có mặt"),
        ({"status": "absent_excused", "reason": "other"}, DAY, "ghi chú"),
        ({"status": "nghi"}, DAY, "present"),
        ({"status": "absent_excused"}, date(2026, 8, 1), "ngoài năm học"),
        ({"status": "absent_excused"}, date(2027, 7, 1), "ngoài năm học"),
    ],
)
def test_invalid_daily_entries_are_rejected(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    entry: dict[str, Any],
    day: date,
    fragment: str,
) -> None:
    response = api_client.put(
        day_url(ids, day),
        headers=auth_headers(HOMEROOM),
        json={"entries": [{"student_id": ids["student"], **entry}]},
    )
    assert response.status_code == 422
    assert fragment in response.text


def test_a_future_day_cannot_be_recorded(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.attendance.router._today", lambda: date(2026, 10, 1))
    response = set_day(api_client, ids, "absent_excused", headers=auth_headers(HOMEROOM))
    assert response.status_code == 422 and "chưa tới" in response.text


def test_a_student_of_another_class_is_rejected(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    class_id_of: Finder,
    db_session: Session,
) -> None:
    outsider = db_session.scalar(
        select(ClassStudent.student_id).where(ClassStudent.class_id == class_id_of("11A3"))
    )
    response = api_client.put(
        day_url(ids),
        headers=auth_headers(HOMEROOM),
        json={"entries": [{"student_id": outsider, "status": "absent_excused"}]},
    )
    assert response.status_code == 422


# --- Theo tiết ---------------------------------------------------------------------------------


def mark(student_id: int, status: str = "absent_unexcused", **extra: Any) -> dict[str, Any]:
    return {"entries": [{"student_id": student_id, "status": status, **extra}]}


def test_subject_teacher_records_a_lesson_and_others_may_only_view(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    url = lesson_url(ids, "literature")
    blank = api_client.get(url, headers=auth_headers(LITERATURE)).json()
    assert blank["exists"] is False and blank["can_edit"] is True
    assert all(e["status"] == "present" for e in blank["entries"])

    saved = api_client.put(
        url,
        headers=auth_headers(LITERATURE),
        json=mark(ids["student"], "absent_excused", reason="sick", note="Có giấy của phụ huynh"),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["exists"] is True
    marked = [e for e in body["entries"] if e["status"] != "present"]
    assert [(e["student_id"], e["status"], e["reason"]) for e in marked] == [
        (ids["student"], "absent_excused", "sick")
    ]

    # GVCN và BGH xem được, không sửa được; GVBM môn khác, Admin không xem được môn này.
    for email, view, can_edit in [(HOMEROOM, 200, False), (PRINCIPAL, 200, False)]:
        response = api_client.get(url, headers=auth_headers(email))
        assert response.status_code == view and response.json()["can_edit"] is can_edit
    for email in (MATH, ADMIN):
        assert api_client.get(url, headers=auth_headers(email)).status_code == 403
    for email in (HOMEROOM, PRINCIPAL, MATH, ADMIN):
        assert (
            api_client.put(url, headers=auth_headers(email), json=mark(ids["student"])).status_code
            == 403
        )

    # Ghi lại: danh sách mới thay hẳn danh sách cũ (cả lớp có mặt).
    cleared = api_client.put(url, headers=auth_headers(LITERATURE), json={"entries": []})
    assert all(e["status"] == "present" for e in cleared.json()["entries"])

    summary = api_client.get(
        f"{API}/classes/{ids['class']}/subjects/{ids['literature']}/lessons?month=2026-10",
        headers=auth_headers(LITERATURE),
    ).json()
    assert summary["lesson_count"] == 1
    assert [(lesson["date"], lesson["lesson_no"]) for lesson in summary["lessons"]] == [
        ("2026-10-05", 2)
    ]


def test_subject_teacher_cannot_record_school_duty(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int]
) -> None:
    response = api_client.put(
        lesson_url(ids, "literature"),
        headers=auth_headers(LITERATURE),
        json=mark(ids["student"], "school_duty"),
    )
    assert response.status_code == 422 and "chủ nhiệm" in response.text


def test_the_same_lesson_slot_cannot_be_taken_by_another_subject(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int]
) -> None:
    first = api_client.put(
        lesson_url(ids, "literature"), headers=auth_headers(LITERATURE), json={"entries": []}
    )
    assert first.status_code == 200
    clash = api_client.put(
        lesson_url(ids, "math"), headers=auth_headers(MATH), json={"entries": []}
    )
    assert clash.status_code == 409 and "Ngữ văn" in clash.text
    view = api_client.get(lesson_url(ids, "math"), headers=auth_headers(MATH)).json()
    assert view["taken_by"] == "Ngữ văn" and view["exists"] is False


def test_a_lesson_can_be_deleted_by_its_teacher_only(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    url = lesson_url(ids, "literature")
    api_client.put(url, headers=auth_headers(LITERATURE), json=mark(ids["student"]))
    assert api_client.delete(url, headers=auth_headers(HOMEROOM)).status_code == 403
    assert api_client.delete(url, headers=auth_headers(LITERATURE)).json() == {"deleted": True}
    db_session.expire_all()
    assert db_session.scalar(select(Lesson.id).where(Lesson.class_id == ids["class"])) is None
    assert api_client.delete(url, headers=auth_headers(LITERATURE)).status_code == 404


@pytest.mark.parametrize("number", [0, 11])
def test_lesson_number_is_between_1_and_10(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], number: int
) -> None:
    response = api_client.get(
        lesson_url(ids, "literature", number=number), headers=auth_headers(LITERATURE)
    )
    assert response.status_code == 422


# --- Đối chiếu tiết – ngày -------------------------------------------------------------------


def mismatches(client: TestClient, headers: dict[str, str], ids: dict[str, int]) -> list[Any]:
    body = client.get(
        f"{API}/classes/{ids['class']}/attendance?month=2026-10", headers=headers
    ).json()
    return [m for m in body["mismatches"] if m["student_id"] == ids["student"]]


def test_absent_in_a_lesson_but_present_for_the_day_is_flagged_until_explained(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int]
) -> None:
    homeroom = auth_headers(HOMEROOM)
    set_day(api_client, ids, "present", headers=homeroom)
    api_client.put(
        lesson_url(ids, "literature"), headers=auth_headers(LITERATURE), json=mark(ids["student"])
    )

    [flag] = mismatches(api_client, homeroom, ids)
    assert flag["kind"] == "lesson_absent_day_present"
    assert (flag["subject_name"], flag["lesson_no"], flag["day_status"]) == (
        "Ngữ văn",
        2,
        "present",
    )
    # Ngày đó em được trường cử đi: không còn lệch.
    set_day(api_client, ids, "school_duty", reason="competition", headers=homeroom)
    assert mismatches(api_client, homeroom, ids) == []


def test_absent_for_the_day_but_present_in_a_lesson_is_flagged(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int]
) -> None:
    homeroom = auth_headers(HOMEROOM)
    set_day(api_client, ids, "absent_unexcused", headers=homeroom)
    api_client.put(
        lesson_url(ids, "literature"), headers=auth_headers(LITERATURE), json={"entries": []}
    )

    [flag] = mismatches(api_client, homeroom, ids)
    assert flag["kind"] == "day_absent_lesson_present" and flag["lesson_status"] == "present"
    # GVCN thấy ngay trong ngày: các tiết GVBM đánh dấu của từng em.
    api_client.put(
        lesson_url(ids, "literature"), headers=auth_headers(LITERATURE), json=mark(ids["student"])
    )
    entry = next(
        e
        for e in api_client.get(day_url(ids), headers=homeroom).json()["entries"]
        if e["student_id"] == ids["student"]
    )
    assert entry["lesson_marks"] == ["Tiết 2 Ngữ văn: vắng không phép"]
