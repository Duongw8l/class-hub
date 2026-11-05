"""Rèn luyện của lớp chủ nhiệm (D-119): phân quyền 4 vai trò, sửa / nhập tay, lịch sử, cả năm theo
học kỳ II, kiểm tra giá trị.

Tài khoản seed: gvcn.11a2 chủ nhiệm 11A2; gv.toan.11 dạy Toán 11A2 và chủ nhiệm 11A1; bgh1 là BGH;
admin là Admin.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.models import AuditLog
from app.classes.academic import ConductResult
from app.classes.models import ClassStudent
from app.core.enums import AuditAction, ConductChangeReason, ConductLevel, ConductPeriod
from app.imports.models import ConductChange

pytestmark = pytest.mark.db

API = "/api/v1"
HOMEROOM = "gvcn.11a2@example.com"
Headers = Callable[[str], dict[str, str]]
Finder = Callable[[str], int]


@pytest.fixture
def ids(class_id_of: Finder, db_session: Session) -> dict[str, int]:
    class_id = class_id_of("11A2")
    student_id, class_student_id = db_session.execute(
        select(ClassStudent.student_id, ClassStudent.id)
        .where(ClassStudent.class_id == class_id)
        .order_by(ClassStudent.student_id)
        .limit(1)
    ).one()
    outsider = db_session.scalar(
        select(ClassStudent.student_id).where(ClassStudent.class_id == class_id_of("11A3")).limit(1)
    )
    assert outsider
    return {
        "class": class_id,
        "student": student_id,
        "class_student": class_student_id,
        "outsider": outsider,
    }


def student_url(ids: dict[str, int], student: str = "student") -> str:
    return f"{API}/classes/{ids['class']}/conduct/students/{ids[student]}"


def put(client: TestClient, headers: dict[str, str], ids: dict[str, int], **body: Any) -> Response:
    payload = {"reason": "review", **body}
    return client.put(student_url(ids), headers=headers, json=payload)


def stored(session: Session, ids: dict[str, int], period: str) -> ConductResult | None:
    session.expire_all()
    return session.scalar(
        select(ConductResult).where(
            ConductResult.class_student_id == ids["class_student"],
            ConductResult.period == ConductPeriod(period),
        )
    )


def changes(session: Session, ids: dict[str, int]) -> list[ConductChange]:
    session.expire_all()
    return list(
        session.scalars(
            select(ConductChange)
            .where(ConductChange.class_student_id == ids["class_student"])
            .order_by(ConductChange.id)
        )
    )


# --- Phân quyền ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "status", "can_edit"),
    [
        (HOMEROOM, 200, True),  # GVCN của lớp
        ("bgh1@example.com", 200, False),  # BGH chỉ xem
        ("gv.toan.11@example.com", 403, None),  # GVBM dạy lớp này, chủ nhiệm lớp khác
        ("gv.van.11@example.com", 403, None),  # GVBM thuần
        ("admin@example.com", 403, None),
    ],
)
def test_who_may_view(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    email: str,
    status: int,
    can_edit: bool | None,
) -> None:
    headers = auth_headers(email)
    whole = api_client.get(f"{API}/classes/{ids['class']}/conduct", headers=headers)
    one = api_client.get(student_url(ids), headers=headers)

    assert whole.status_code == status and one.status_code == status
    if can_edit is not None:
        assert whole.json()["can_edit"] is can_edit and one.json()["can_edit"] is can_edit


@pytest.mark.parametrize(
    "email",
    ["bgh1@example.com", "gv.toan.11@example.com", "gv.van.11@example.com", "admin@example.com"],
)
def test_only_the_homeroom_teacher_may_edit(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], email: str
) -> None:
    headers = auth_headers(email)
    response = put(api_client, headers, ids, entries=[{"period": "hk1", "level": "fail"}])
    fill = api_client.post(f"{API}/classes/{ids['class']}/conduct/year-from-hk2", headers=headers)

    assert response.status_code == 403 and fill.status_code == 403


def test_unauthenticated_gets_401(api_client: TestClient, ids: dict[str, int]) -> None:
    assert api_client.get(f"{API}/classes/{ids['class']}/conduct").status_code == 401
    assert api_client.put(student_url(ids), json={}).status_code == 401


# --- Xem ---------------------------------------------------------------------------------------


def test_class_table_has_every_student_with_three_periods_and_counts(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    body = api_client.get(
        f"{API}/classes/{ids['class']}/conduct", headers=auth_headers(HOMEROOM)
    ).json()

    assert body["class_info"]["name"] == "11A2" and len(body["rows"]) == 40
    assert all([e["period"] for e in r["entries"]] == ["hk1", "hk2", "year"] for r in body["rows"])
    for period, counts in body["counts"].items():
        assert sum(counts.values()) == 40, period
        stored_count = sum(
            1
            for r in body["rows"]
            for e in r["entries"]
            if e["period"] == period and e["level"] is not None
        )
        assert stored_count == 40 - counts["missing"]
    # Không có thông tin phụ huynh hay ngày sinh.
    assert set(body["rows"][0]) == {
        "student_id",
        "student_code",
        "full_name",
        "entries",
        "change_count",
    }
    logged = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.VIEW_CLASS_CONDUCT)
    ).all()
    assert logged


# --- Sửa ---------------------------------------------------------------------------------------


def test_editing_replaces_the_level_and_records_history(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    before = stored(db_session, ids, "hk1")
    old_level = before.level if before else None
    new_level = "fail" if old_level is not ConductLevel.FAIL else "good"

    response = put(
        api_client,
        auth_headers(HOMEROOM),
        ids,
        entries=[{"period": "hk1", "level": new_level, "comment": "  Cần nhắc nhở thêm.  "}],
        note="Theo biên bản họp lớp",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entries"][0] == {
        "period": "hk1",
        "level": new_level,
        "comment": "Cần nhắc nhở thêm.",
    }
    after = stored(db_session, ids, "hk1")
    assert after is not None and after.level is ConductLevel(new_level)
    [change] = changes(db_session, ids)
    assert change.old_level is old_level and change.new_level is ConductLevel(new_level)
    assert change.reason is ConductChangeReason.REVIEW and change.note == "Theo biên bản họp lớp"
    assert body["history"][0]["reason_label"] == "Xét lại"
    log = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.EDIT_CONDUCT)
    ).all()[-1]
    assert log.details["periods"] == ["hk1"]


def test_a_missing_period_can_be_entered(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    db_session.execute(
        delete(ConductResult).where(ConductResult.class_student_id == ids["class_student"])
    )
    db_session.commit()

    response = put(
        api_client,
        auth_headers(HOMEROOM),
        ids,
        reason="supplement",
        entries=[{"period": "year", "level": "fair"}],
    )

    assert response.status_code == 200, response.text
    row = stored(db_session, ids, "year")
    assert row is not None and row.level is ConductLevel.FAIR and row.comment is None
    [change] = changes(db_session, ids)
    assert change.old_level is None and change.new_level is ConductLevel.FAIR


def test_only_changed_periods_are_recorded_and_nothing_changed_is_400(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    headers = auth_headers(HOMEROOM)
    first = put(
        api_client,
        headers,
        ids,
        entries=[{"period": "hk1", "level": "good"}, {"period": "hk2", "level": "fair"}],
    )
    assert first.status_code == 200, first.text
    recorded = len(changes(db_session, ids))

    # Gửi lại đúng các giá trị đang có, chỉ đổi học kỳ II: một dòng lịch sử mới.
    second = put(
        api_client,
        headers,
        ids,
        entries=[{"period": "hk1", "level": "good"}, {"period": "hk2", "level": "pass"}],
    )
    assert second.status_code == 200
    assert len(changes(db_session, ids)) == recorded + 1

    same = put(api_client, headers, ids, entries=[{"period": "hk2", "level": "pass"}])
    assert same.status_code == 400
    assert len(changes(db_session, ids)) == recorded + 1


def test_saving_refreshes_alerts_of_the_class(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[int] = []
    monkeypatch.setattr("app.imports.hooks.on_data_changed", called.append)
    response = put(
        api_client,
        auth_headers(HOMEROOM),
        ids,
        entries=[{"period": "hk1", "level": "fail", "comment": "Thử"}],
    )
    assert response.status_code == 200, response.text
    assert called == [ids["class"]]


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"entries": [{"period": "hk3", "level": "good"}]}, "hk1"),
        ({"entries": [{"period": "hk1", "level": "xuat-sac"}]}, "good"),
        ({"entries": [{"period": "hk1"}]}, "level"),
        ({"entries": []}, "at least 1"),
        ({"reason": "other", "entries": [{"period": "hk1", "level": "good"}]}, "ghi chú"),
        (
            {"entries": [{"period": "hk1", "level": "good"}, {"period": "hk1", "level": "fair"}]},
            "hai lần",
        ),
        ({"entries": [{"period": "hk1", "level": "good", "comment": "x" * 501}]}, "500"),
    ],
)
def test_invalid_input_is_rejected_and_writes_nothing(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    db_session: Session,
    body: dict[str, Any],
    fragment: str,
) -> None:
    response = put(api_client, auth_headers(HOMEROOM), ids, **body)

    assert response.status_code == 422
    assert fragment in response.text
    assert changes(db_session, ids) == []


def test_student_of_another_class_is_404(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int]
) -> None:
    response = api_client.put(
        student_url(ids, "outsider"),
        headers=auth_headers(HOMEROOM),
        json={"reason": "review", "entries": [{"period": "hk1", "level": "good"}]},
    )
    assert response.status_code == 404


# --- Cả năm theo học kỳ II ---------------------------------------------------------------------


def test_year_from_hk2_fills_only_empty_years_with_the_hk2_level(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int], db_session: Session
) -> None:
    class_students = list(
        db_session.scalars(select(ClassStudent.id).where(ClassStudent.class_id == ids["class"]))
    )
    # Bắt đầu: không ai có cả năm; em đầu tiên học kỳ II "Đạt", cả lớp còn lại giữ nguyên.
    db_session.execute(
        delete(ConductResult).where(
            ConductResult.class_student_id.in_(class_students),
            ConductResult.period == ConductPeriod.YEAR,
        )
    )
    db_session.execute(
        delete(ConductResult).where(ConductResult.class_student_id == ids["class_student"])
    )
    db_session.add(
        ConductResult(
            class_student_id=ids["class_student"], period=ConductPeriod.HK2, level=ConductLevel.PASS
        )
    )
    db_session.commit()
    with_hk2 = db_session.scalar(
        select(ConductResult.id)
        .where(
            ConductResult.class_student_id.in_(class_students),
            ConductResult.period == ConductPeriod.HK2,
        )
        .limit(1)
    )
    assert with_hk2 is not None
    headers = auth_headers(HOMEROOM)
    expected = api_client.get(f"{API}/classes/{ids['class']}/conduct", headers=headers).json()[
        "year_fillable"
    ]

    response = api_client.post(
        f"{API}/classes/{ids['class']}/conduct/year-from-hk2", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == {"filled": expected} and expected > 0
    year = stored(db_session, ids, "year")
    assert year is not None and year.level is ConductLevel.PASS
    [change] = [c for c in changes(db_session, ids) if c.period is ConductPeriod.YEAR]
    assert change.reason is ConductChangeReason.SUPPLEMENT and change.old_level is None
    # Bấm lần nữa: không còn em nào trống, không ghi gì.
    again = api_client.post(f"{API}/classes/{ids['class']}/conduct/year-from-hk2", headers=headers)
    assert again.json() == {"filled": 0}
