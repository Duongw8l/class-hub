"""Sửa / nhập tay điểm của một học sinh (D-115): phân quyền, ghi đè, lịch sử, kiểm tra giá trị.

Tài khoản seed: gv.toan.11 dạy Toán 11A2; gv.van.11 dạy Ngữ văn 11A2; gvcn.11a2 chủ nhiệm 11A2;
bgh1 là BGH; admin là Admin.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.models import AuditLog
from app.auth.tokens import create_access_token
from app.classes.academic import Assessment
from app.classes.models import ClassStudent, TeachingAssignment
from app.core.enums import AssessmentKind, AuditAction, CommentResult, ScoreChangeReason
from app.imports.models import AssessmentChange

pytestmark = pytest.mark.db

API = "/api/v1"
TEACHER = "gv.toan.11@example.com"
Headers = Callable[[str], dict[str, str]]
Finder = Callable[[str], int]


@pytest.fixture
def ids(class_id_of: Finder, subject_id_of: Finder, db_session: Session) -> dict[str, int]:
    class_id = class_id_of("11A2")
    other_class = class_id_of("11A3")
    student_id = db_session.scalar(
        select(ClassStudent.student_id)
        .where(ClassStudent.class_id == class_id)
        .order_by(ClassStudent.student_id)
        .limit(1)
    )
    outsider = db_session.scalar(
        select(ClassStudent.student_id).where(ClassStudent.class_id == other_class).limit(1)
    )
    class_student_id = db_session.scalar(
        select(ClassStudent.id).where(
            ClassStudent.class_id == class_id, ClassStudent.student_id == student_id
        )
    )
    assert student_id and outsider and class_student_id
    return {
        "class": class_id,
        "math": subject_id_of("Toán"),
        "pe": subject_id_of("Giáo dục thể chất"),
        "student": student_id,
        "outsider": outsider,
        "class_student": class_student_id,
    }


def url(ids: dict[str, int], subject: str = "math", student: str = "student") -> str:
    return f"{API}/classes/{ids['class']}/subjects/{ids[subject]}/students/{ids[student]}/scores"


def put(client: TestClient, headers: dict[str, str], ids: dict[str, int], **body: Any) -> Response:
    payload = {"semester": 1, "reason": "retest", **body}
    return client.put(url(ids), headers=headers, json=payload)


def stored(session: Session, ids: dict[str, int], kind: str, seq: int) -> Assessment | None:
    session.expire_all()
    return session.scalar(
        select(Assessment).where(
            Assessment.class_student_id == ids["class_student"],
            Assessment.subject_id == ids["math"],
            Assessment.semester == 1,
            Assessment.kind == AssessmentKind(kind),
            Assessment.seq == seq,
        )
    )


# --- Phân quyền ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "status", "can_edit"),
    [
        (TEACHER, 200, True),
        ("gvcn.11a2@example.com", 200, False),
        ("bgh1@example.com", 200, False),
        ("gv.van.11@example.com", 403, None),  # dạy môn khác ở lớp này
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
    response = api_client.get(url(ids), headers=auth_headers(email), params={"semester": 1})
    assert response.status_code == status, response.text
    if can_edit is not None:
        assert response.json()["can_edit"] is can_edit


@pytest.mark.parametrize(
    "email",
    ["gvcn.11a2@example.com", "bgh1@example.com", "gv.van.11@example.com", "admin@example.com"],
)
def test_only_the_assigned_teacher_may_edit(
    api_client: TestClient,
    auth_headers: Headers,
    db_session: Session,
    ids: dict[str, int],
    email: str,
) -> None:
    before = stored(db_session, ids, "tx", 1)
    assert before is not None
    response = put(
        api_client, auth_headers(email), ids, entries=[{"kind": "tx", "seq": 1, "score": 9.9}]
    )
    assert response.status_code == 403
    assert stored(db_session, ids, "tx", 1).score == before.score  # type: ignore[union-attr]
    assert db_session.scalar(select(AssessmentChange.id)) is None


def test_unauthenticated_gets_401(api_client: TestClient, ids: dict[str, int]) -> None:
    assert api_client.get(url(ids)).status_code == 401
    assert api_client.put(url(ids), json={}).status_code == 401


# --- Sửa, nhập bù, lịch sử -------------------------------------------------------------------


def test_editing_replaces_the_score_and_records_history(
    api_client: TestClient, auth_headers: Headers, db_session: Session, ids: dict[str, int]
) -> None:
    row = stored(db_session, ids, "ck", 1)
    assert row is not None and row.score is not None
    old_score = row.score
    new = Decimal("9.5") if old_score != Decimal("9.5") else Decimal("8.0")

    response = put(
        api_client,
        auth_headers(TEACHER),
        ids,
        entries=[{"kind": "ck", "seq": 1, "score": float(new)}],
        note="Kiểm tra lại ngày 10/12",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert {"kind": "ck", "seq": 1, "score": float(new), "comment_result": None} in body["entries"]
    assert stored(db_session, ids, "ck", 1).score == new  # type: ignore[union-attr]
    [change] = body["history"]
    assert change["old_score"] == float(old_score) and change["new_score"] == float(new)
    assert change["reason"] == "retest" and change["reason_label"] == "Kiểm tra lại"
    assert change["note"] == "Kiểm tra lại ngày 10/12"
    assert change["changed_by"]  # họ tên giáo viên

    # ĐTB do Analytics tính lại khi đọc: bảng điểm môn thấy điểm mới.
    scores = api_client.get(
        f"{API}/classes/{ids['class']}/subjects/{ids['math']}/scores",
        headers=auth_headers(TEACHER),
        params={"semester": 1},
    ).json()
    row = next(r for r in scores["rows"] if r["student_id"] == ids["student"])
    assert row["final"] == float(new)

    audit = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.EDIT_SCORES)
    ).all()
    assert len(audit) == 1 and audit[0].details["changed"] == 1


def test_missing_score_can_be_entered(
    api_client: TestClient, auth_headers: Headers, db_session: Session, ids: dict[str, int]
) -> None:
    db_session.execute(
        delete(Assessment).where(
            Assessment.class_student_id == ids["class_student"],
            Assessment.subject_id == ids["math"],
            Assessment.semester == 1,
            Assessment.kind == AssessmentKind.TX,
            Assessment.seq == 2,
        )
    )
    db_session.commit()

    response = put(
        api_client,
        auth_headers(TEACHER),
        ids,
        reason="makeup",
        entries=[{"kind": "tx", "seq": 2, "score": 7}],
    )

    assert response.status_code == 200, response.text
    assert stored(db_session, ids, "tx", 2).score == Decimal("7.0")  # type: ignore[union-attr]
    change = db_session.scalar(select(AssessmentChange))
    assert change is not None
    assert change.old_score is None and change.new_score == Decimal("7.0")
    assert change.reason is ScoreChangeReason.MAKEUP


def test_only_changed_entries_are_recorded(
    api_client: TestClient, auth_headers: Headers, db_session: Session, ids: dict[str, int]
) -> None:
    same = stored(db_session, ids, "tx", 1)
    assert same is not None and same.score is not None
    response = put(
        api_client,
        auth_headers(TEACHER),
        ids,
        reason="correction",
        entries=[
            {"kind": "tx", "seq": 1, "score": float(same.score)},
            {"kind": "gk", "seq": 1, "score": 0.5},
        ],
    )
    assert response.status_code == 200, response.text
    changes = db_session.scalars(select(AssessmentChange)).all()
    assert [(c.kind, c.seq) for c in changes] == [(AssessmentKind.GK, 1)]


def test_nothing_changed_is_rejected(
    api_client: TestClient, auth_headers: Headers, db_session: Session, ids: dict[str, int]
) -> None:
    same = stored(db_session, ids, "tx", 1)
    assert same is not None and same.score is not None
    response = put(
        api_client,
        auth_headers(TEACHER),
        ids,
        entries=[{"kind": "tx", "seq": 1, "score": float(same.score)}],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Không có điểm nào thay đổi."
    assert db_session.scalar(select(AssessmentChange.id)) is None


def test_saving_refreshes_alerts_of_the_class(
    api_client: TestClient,
    auth_headers: Headers,
    ids: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[int] = []
    monkeypatch.setattr("app.imports.hooks.on_data_changed", called.append)
    response = put(
        api_client, auth_headers(TEACHER), ids, entries=[{"kind": "gk", "seq": 1, "score": 0.1}]
    )
    assert response.status_code == 200, response.text
    assert called == [ids["class"]]


# --- Kiểm tra giá trị ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"entries": [{"kind": "tx", "seq": 1, "score": 8.25}]}, "decimal"),
        ({"entries": [{"kind": "tx", "seq": 1, "score": 11}]}, "less than or equal"),
        ({"entries": [{"kind": "tx", "seq": 1, "score": -1}]}, "greater than or equal"),
        ({"entries": [{"kind": "gk", "seq": 2, "score": 5}]}, "một đầu điểm"),
        ({"entries": [{"kind": "tx", "seq": 1}]}, "đúng một giá trị"),
        ({"entries": [{"kind": "tx", "seq": 9, "score": 5}]}, "đầu điểm thường xuyên"),
        ({"entries": [{"kind": "ck", "seq": 1, "comment_result": "pass"}]}, "cần điểm số"),
        ({"reason": "other", "entries": [{"kind": "tx", "seq": 1, "score": 5}]}, "ghi chú"),
        (
            {
                "entries": [
                    {"kind": "tx", "seq": 1, "score": 5},
                    {"kind": "tx", "seq": 1, "score": 6},
                ]
            },
            "hai lần",
        ),
    ],
)
def test_invalid_input_is_rejected_and_writes_nothing(
    api_client: TestClient,
    auth_headers: Headers,
    db_session: Session,
    ids: dict[str, int],
    body: dict[str, Any],
    fragment: str,
) -> None:
    response = put(api_client, auth_headers(TEACHER), ids, **body)
    assert response.status_code == 422, response.text
    assert fragment in response.text
    assert db_session.scalar(select(AssessmentChange.id)) is None


def test_student_of_another_class_is_404(
    api_client: TestClient, auth_headers: Headers, ids: dict[str, int]
) -> None:
    response = api_client.get(url(ids, student="outsider"), headers=auth_headers(TEACHER))
    assert response.status_code == 404
    assert response.json()["detail"] == "Học sinh này không thuộc lớp."


def test_comment_subject_takes_pass_or_fail(
    api_client: TestClient, auth_headers: Headers, db_session: Session, ids: dict[str, int]
) -> None:
    teacher_id = db_session.scalar(
        select(TeachingAssignment.teacher_id).where(
            TeachingAssignment.class_id == ids["class"],
            TeachingAssignment.subject_id == ids["pe"],
        )
    )
    assert teacher_id is not None
    headers = {"Authorization": f"Bearer {create_access_token(teacher_id)[0]}"}

    view = api_client.get(url(ids, "pe"), headers=headers).json()
    assert view["is_comment_subject"] is True and view["tx_slots"] == 0

    wrong = api_client.put(
        url(ids, "pe"),
        headers=headers,
        json={
            "semester": 1,
            "reason": "retest",
            "entries": [{"kind": "ck", "seq": 1, "score": 8}],
        },
    )
    assert wrong.status_code == 422 and "nhận xét" in wrong.json()["detail"]

    current = next(e for e in view["entries"] if e["kind"] == "ck")["comment_result"]
    new = "fail" if current == "pass" else "pass"
    response = api_client.put(
        url(ids, "pe"),
        headers=headers,
        json={
            "semester": 1,
            "reason": "retest",
            "entries": [{"kind": "ck", "seq": 1, "comment_result": new}],
        },
    )
    assert response.status_code == 200, response.text
    change = db_session.scalar(select(AssessmentChange))
    assert change is not None and change.new_comment_result is CommentResult(new)
