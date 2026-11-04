"""Nhiều năm học (D-113): tạo năm, chép lớp và cho học sinh lên lớp, năm hiện hành, và mọi danh sách
"toàn trường" lọc theo năm. Xem năm cũ vẫn theo phân quyền của chính lớp năm đó."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assistant.scope import load_scope
from app.auth.models import User
from app.classes.models import ClassStudent, SchoolClass, SchoolYear
from app.classes.years import current_year
from app.core.enums import RiskLevel
from app.imports.roster import class_memberships
from app.warning.repository import insert_alert

pytestmark = pytest.mark.db

API = "/api/v1"
ADMIN = "admin@example.com"
PRINCIPAL = "bgh1@example.com"
HOMEROOM_11A2 = "gvcn.11a2@example.com"
Headers = Callable[[str], dict[str, str]]
NEXT_YEAR = {"name": "2027-2028", "start_date": "2027-09-05", "end_date": "2028-05-31"}


def seed_year(session: Session) -> SchoolYear:
    year = current_year(session)
    assert year is not None and year.name == "2026-2027"
    return year


def class_in(session: Session, year_id: int, name: str) -> SchoolClass:
    found = session.scalar(
        select(SchoolClass).where(SchoolClass.school_year_id == year_id, SchoolClass.name == name)
    )
    assert found is not None, f"Không có lớp {name} trong năm {year_id}"
    return found


def students_of(session: Session, class_id: int) -> set[int]:
    return set(
        session.scalars(select(ClassStudent.student_id).where(ClassStudent.class_id == class_id))
    )


def create_year(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = client.post(
        f"{API}/admin/school-years", headers=headers, json={**NEXT_YEAR, **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Danh sách năm và phân quyền -----------------------------------------------------------------


@pytest.mark.parametrize("email", [ADMIN, PRINCIPAL, HOMEROOM_11A2, "gv.van.11@example.com"])
def test_every_signed_in_user_can_list_years(
    api_client: TestClient, auth_headers: Headers, email: str
) -> None:
    response = api_client.get(f"{API}/school-years", headers=auth_headers(email))
    assert response.status_code == 200
    rows = response.json()
    assert [(r["name"], r["is_current"]) for r in rows] == [("2026-2027", True)]


def test_listing_years_needs_sign_in(api_client: TestClient) -> None:
    assert api_client.get(f"{API}/school-years").status_code == 401


@pytest.mark.parametrize("email", [PRINCIPAL, HOMEROOM_11A2])
def test_only_admin_manages_years(
    api_client: TestClient, auth_headers: Headers, db_session: Session, email: str
) -> None:
    headers = auth_headers(email)
    year_id = seed_year(db_session).id
    assert (
        api_client.post(f"{API}/admin/school-years", headers=headers, json=NEXT_YEAR).status_code
        == 403
    )
    assert (
        api_client.patch(f"{API}/admin/school-years/{year_id}", headers=headers, json=NEXT_YEAR)
    ).status_code == 403
    assert (
        api_client.post(f"{API}/admin/school-years/{year_id}/current", headers=headers)
    ).status_code == 403
    assert db_session.scalar(select(func.count()).select_from(SchoolYear)) == 1


# --- Tạo năm, chép lớp, lên lớp ------------------------------------------------------------------


def test_new_year_without_rollover_is_empty_and_not_current(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    body = create_year(api_client, auth_headers(ADMIN))

    assert body["classes_created"] == 0 and body["students_promoted"] == 0
    assert body["school_year"]["is_current"] is False
    assert seed_year(db_session).is_current  # năm cũ vẫn là năm hiện hành


def test_rollover_copies_classes_and_moves_students_up_one_grade(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    old = seed_year(db_session)
    body = create_year(api_client, auth_headers(ADMIN), rollover=True)
    new_id = body["school_year"]["id"]

    # 9 lớp của seed (3 lớp mỗi khối) được tạo lại; HS khối 10 và 11 lên lớp, khối 12 ra trường.
    assert body["classes_created"] == 9
    assert body["students_promoted"] == 6 * 40
    assert students_of(db_session, class_in(db_session, new_id, "11A1").id) == students_of(
        db_session, class_in(db_session, old.id, "10A1").id
    )
    assert students_of(db_session, class_in(db_session, new_id, "12A2").id) == students_of(
        db_session, class_in(db_session, old.id, "11A2").id
    )
    assert students_of(db_session, class_in(db_session, new_id, "10A1").id) == set()
    new_10a1 = class_in(db_session, new_id, "10A1")
    assert new_10a1.homeroom_teacher_id is None  # GVCN, phân công để trống


def test_rollover_needs_an_earlier_year(api_client: TestClient, auth_headers: Headers) -> None:
    earlier = {"name": "2025-2026", "start_date": "2025-09-05", "end_date": "2026-05-31"}
    response = api_client.post(
        f"{API}/admin/school-years",
        headers=auth_headers(ADMIN),
        json={**earlier, "rollover": True},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "2026-2027"},  # trùng tên
        {"start_date": "2027-05-01"},  # chồng ngày với năm seed (kết thúc 31/5/2027)
    ],
)
def test_new_year_must_not_clash_with_an_existing_one(
    api_client: TestClient, auth_headers: Headers, overrides: dict[str, str]
) -> None:
    response = api_client.post(
        f"{API}/admin/school-years", headers=auth_headers(ADMIN), json={**NEXT_YEAR, **overrides}
    )
    assert response.status_code == 409


def test_only_one_year_is_current(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    new_id = create_year(api_client, headers)["school_year"]["id"]

    response = api_client.post(f"{API}/admin/school-years/{new_id}/current", headers=headers)

    assert response.status_code == 200 and response.json()["is_current"] is True
    years = api_client.get(f"{API}/school-years", headers=headers).json()
    assert [(y["name"], y["is_current"]) for y in years] == [
        ("2027-2028", True),
        ("2026-2027", False),
    ]


def test_class_names_and_homerooms_are_per_year(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    new_id = create_year(api_client, headers)["school_year"]["id"]
    teacher = db_session.scalar(select(User.id).where(User.email == HOMEROOM_11A2))

    # Cùng tên 11A2 và cùng GVCN với năm seed: được, vì khác năm học.
    response = api_client.post(
        f"{API}/admin/classes",
        headers=headers,
        json={
            "grade_level": 11,
            "name": "11A2",
            "homeroom_teacher_id": teacher,
            "school_year_id": new_id,
        },
    )
    assert response.status_code == 201, response.text

    # Nhưng trong cùng năm thì vẫn không được.
    again = api_client.post(
        f"{API}/admin/classes",
        headers=headers,
        json={"grade_level": 11, "name": "11A2", "school_year_id": new_id},
    )
    assert again.status_code == 409


def test_admin_school_page_shows_one_year_at_a_time(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    new_id = create_year(api_client, headers, rollover=True)["school_year"]["id"]

    current = api_client.get(f"{API}/admin/school", headers=headers).json()
    chosen = api_client.get(
        f"{API}/admin/school", headers=headers, params={"school_year_id": new_id}
    ).json()

    assert current["school_year"]["name"] == "2026-2027" and len(current["classes"]) == 9
    assert chosen["school_year"]["name"] == "2027-2028" and len(chosen["classes"]) == 9
    assert {c["id"] for c in current["classes"]}.isdisjoint({c["id"] for c in chosen["classes"]})
    assert [y["name"] for y in chosen["years"]] == ["2027-2028", "2026-2027"]
    unknown = api_client.get(f"{API}/admin/school", headers=headers, params={"school_year_id": 999})
    assert unknown.status_code == 404


# --- Xem theo năm: giáo viên, BGH ----------------------------------------------------------------


def test_teacher_sees_last_year_classes_when_choosing_that_year(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    admin = auth_headers(ADMIN)
    old = seed_year(db_session)
    new_id = create_year(api_client, admin, rollover=True, make_current=True)["school_year"]["id"]
    teacher = auth_headers(HOMEROOM_11A2)

    now = api_client.get(f"{API}/me/assignments", headers=teacher).json()
    before = api_client.get(
        f"{API}/me/assignments", headers=teacher, params={"school_year_id": old.id}
    ).json()

    assert now["school_year"]["id"] == new_id and now["homeroom_classes"] == []
    assert before["school_year"]["name"] == "2026-2027"
    assert [c["name"] for c in before["homeroom_classes"]] == ["11A2"]
    # Lớp năm cũ vẫn mở được: quyền theo chính lớp đó (GVCN của 11A2 năm 2026-2027).
    old_class = class_in(db_session, old.id, "11A2").id
    dashboard = api_client.get(f"{API}/classes/{old_class}/dashboard", headers=teacher)
    assert dashboard.status_code == 200
    # Lớp 11A2 của năm mới chưa có GVCN: giáo viên này không được xem.
    new_class = class_in(db_session, new_id, "11A2").id
    assert (
        api_client.get(f"{API}/classes/{new_class}/dashboard", headers=teacher).status_code == 403
    )


def test_principal_grade_overview_and_alerts_follow_the_chosen_year(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    old = seed_year(db_session)
    create_year(api_client, auth_headers(ADMIN), rollover=True, make_current=True)
    bgh = auth_headers(PRINCIPAL)

    new_grade = api_client.get(f"{API}/grades/11/overview", headers=bgh).json()
    old_grade = api_client.get(
        f"{API}/grades/11/overview", headers=bgh, params={"school_year_id": old.id}
    ).json()
    old_ids = {
        c.id
        for c in db_session.scalars(select(SchoolClass).where(SchoolClass.school_year_id == old.id))
    }
    assert len(old_grade["classes"]) == len(new_grade["classes"]) == 3
    assert {c["class_id"] for c in old_grade["classes"]} <= old_ids
    assert not {c["class_id"] for c in new_grade["classes"]} & old_ids

    # Một cảnh báo mức Cao cho một em của lớp 11A2 năm seed.
    member = db_session.scalar(
        select(ClassStudent.id).where(
            ClassStudent.class_id == class_in(db_session, old.id, "11A2").id
        )
    )
    assert member is not None
    insert_alert(
        db_session,
        class_student_id=member,
        level=RiskLevel.HIGH,
        risk_score=None,
        reasons={"rules": [], "as_of": None},
        model_version=None,
    )
    db_session.flush()

    new_alerts = api_client.get(f"{API}/alerts", headers=bgh).json()
    old_alerts = api_client.get(
        f"{API}/alerts", headers=bgh, params={"school_year_id": old.id}
    ).json()
    assert new_alerts["alerts"] == [] and new_alerts["counts"]["high"] == 0
    assert [a["class_name"] for a in old_alerts["alerts"]] == ["11A2"]
    assert old_alerts["counts"]["high"] == 1


def test_assistant_scope_only_lists_classes_of_the_year(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    old = seed_year(db_session)
    new_id = create_year(api_client, auth_headers(ADMIN), rollover=True)["school_year"]["id"]
    principal = db_session.scalar(select(User).where(User.email == PRINCIPAL))
    assert principal is not None

    old_scope = load_scope(db_session, principal, school_year_id=old.id)
    new_scope = load_scope(db_session, principal, school_year_id=new_id)

    assert old_scope.year_name == "2026-2027" and new_scope.year_name == "2027-2028"
    assert len(old_scope.classes) == len(new_scope.classes) == 9
    assert set(old_scope.class_ids).isdisjoint(new_scope.class_ids)


def test_roster_conflict_check_only_looks_at_the_same_year(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    old = seed_year(db_session)
    new_id = create_year(api_client, auth_headers(ADMIN))["school_year"]["id"]

    # HS1102001 học 11A2 năm seed: năm mới em chưa thuộc lớp nào, nên nhập vào lớp năm mới được.
    assert class_memberships(db_session, ["HS1102001"], school_year_id=new_id) == {}
    assert (
        class_memberships(db_session, ["HS1102001"], school_year_id=old.id)["HS1102001"][0][1]
        == "11A2"
    )
