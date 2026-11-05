"""Nhập sổ điểm danh theo tiết từ tệp dạng lưới (D-121): đọc tiêu đề cột, kiểm từng ô, phân quyền,
xem trước không ghi, xác nhận ghi vào đúng sổ theo tiết của D-120.

Tài khoản seed: gv.van.11 dạy Ngữ văn 11A2; gv.toan.11 dạy Toán 11A2 và chủ nhiệm 11A1; gvcn.11a2
chủ nhiệm 11A2; bgh1 là BGH. Năm học seed 05/09/2026 đến 31/05/2027.
"""

from datetime import date
from typing import Any

import pytest
from sqlalchemy import select

from app.classes.academic import Lesson, LessonAbsence
from app.classes.models import ClassStudent, Student
from app.core.enums import AttendanceStatus
from app.imports.lessons import parse_lesson_header
from tests.imports.conftest import ImportApi, build_csv, build_xlsx

FIRST, LAST = date(2026, 9, 5), date(2027, 5, 31)
LITERATURE = "gv.van.11@example.com"
MATH = "gv.toan.11@example.com"


# --- Đọc tiêu đề cột (hàm thuần) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("05/10 Tiết 2", (date(2026, 10, 5), 2)),
        ("5/10 T2", (date(2026, 10, 5), 2)),
        ("05/10/2026 - Tiết 3", (date(2026, 10, 5), 3)),
        ("Tiết 4 (12/01)", (date(2027, 1, 12), 4)),  # tháng 1: năm sau của năm học
        ("2026-10-05 tiet 10", (date(2026, 10, 5), 10)),
        ("12-01-27 T1", (date(2027, 1, 12), 1)),
        ("Thứ 2 05/10 Tiết 5", (date(2026, 10, 5), 5)),  # "Thứ 2" không bị đọc là tiết 2
        ("STT", None),
        ("Ghi chú", None),
        ("Họ và tên", None),
    ],
)
def test_lesson_headers_are_read_as_date_and_period(
    header: str, expected: tuple[date, int] | None
) -> None:
    assert parse_lesson_header(header, FIRST, LAST) == expected


@pytest.mark.parametrize(
    ("header", "fragment"),
    [("05/10", "thiếu tiết"), ("31/02 T1", "không có thật"), ("2026-13-01 T1", "không có thật")],
)
def test_broken_lesson_headers_explain_the_problem(header: str, fragment: str) -> None:
    result = parse_lesson_header(header, FIRST, LAST)
    assert isinstance(result, str) and fragment in result


# --- Qua API ------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.imports.lessons.today", lambda: date(2026, 11, 5))


def roster(imp: ImportApi, class_name: str = "11A2") -> list[tuple[str, str, int]]:
    rows = imp.session.execute(
        select(Student.student_code, Student.full_name, ClassStudent.id)
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .where(ClassStudent.class_id == imp.class_id_of(class_name))
        .order_by(Student.student_code)
    ).all()
    return [(r[0], r[1], r[2]) for r in rows]


def grid(imp: ImportApi, headers: list[str], marks: dict[int, list[str]]) -> list[list[Any]]:
    """Lưới cả lớp: ô trống là có mặt; `marks` theo vị trí học sinh -> ô của từng cột tiết."""
    rows: list[list[Any]] = [["STT", "Mã HS", "Họ và tên", *headers]]
    for index, (code, name, _cs) in enumerate(roster(imp)):
        rows.append([index + 1, code, name, *marks.get(index, [""] * len(headers))])
    return rows


def upload(imp: ImportApi, rows: list[list[Any]], email: str = LITERATURE, **kw: Any) -> Any:
    return imp.upload(
        email,
        "11A2",
        "lessons",
        build_xlsx(rows),
        subject_id=imp.subject_id_of(kw.pop("subject", "Ngữ văn")),
        **kw,
    )


def absences(imp: ImportApi) -> dict[tuple[date, int, int], AttendanceStatus]:
    imp.session.expire_all()
    rows = imp.session.execute(
        select(Lesson.date, Lesson.lesson_no, LessonAbsence.class_student_id, LessonAbsence.status)
        .join(LessonAbsence, LessonAbsence.lesson_id == Lesson.id)
        .where(Lesson.class_id == imp.class_id_of("11A2"))
    ).all()
    return {(r[0], r[1], r[2]): r[3] for r in rows}


@pytest.mark.db
def test_a_grid_file_previews_then_writes_the_lesson_book(imp: ImportApi) -> None:
    headers = ["05/10 Tiết 2", "07/10 Tiết 1"]
    rows = grid(imp, headers, {0: ["P", ""], 1: ["K", "M"], 2: ["", "Có mặt"]})

    response = upload(imp, rows)
    body = response.json()

    assert response.status_code == 200, response.text
    assert body["summary"]["error_rows"] == 0 and body["can_confirm"] is True
    assert body["summary"]["total_rows"] == 40
    assert body["summary"]["records_to_create"] == 80  # 40 em x 2 tiết mới
    assert body["ignored_columns"] == ["STT"]
    lesson_fields = [f for f in body["fields"] if f["name"].startswith("lesson:")]
    assert [(f["label"], f["column"]) for f in lesson_fields] == [
        ("05/10 T2", "05/10 Tiết 2"),
        ("07/10 T1", "07/10 Tiết 1"),
    ]
    first_row = next(r for r in body["rows"] if r["line"] == 2)
    assert first_row["values"]["lesson:2026-10-05:2"] == "Vắng CP"
    assert absences(imp) == {}  # xem trước không ghi gì

    confirmed = imp.confirm(LITERATURE, body["job_id"])
    assert confirmed.status_code == 200, confirmed.text
    students = roster(imp)
    assert absences(imp) == {
        (date(2026, 10, 5), 2, students[0][2]): AttendanceStatus.ABSENT_EXCUSED,
        (date(2026, 10, 5), 2, students[1][2]): AttendanceStatus.ABSENT_UNEXCUSED,
        (date(2026, 10, 7), 1, students[1][2]): AttendanceStatus.LATE,
    }
    # Sổ theo tiết thấy ngay hai tiết vừa nhập.
    book = imp.client.get(
        f"/api/v1/classes/{imp.class_id_of('11A2')}/subjects/{imp.subject_id_of('Ngữ văn')}"
        "/lessons?month=2026-10",
        headers=imp.auth_headers(LITERATURE),
    ).json()
    assert book["lesson_count"] == 2


@pytest.mark.db
def test_re_importing_changes_only_the_cells_that_differ(imp: ImportApi) -> None:
    headers = ["05/10 Tiết 2"]
    first = upload(imp, grid(imp, headers, {0: ["P"]})).json()
    imp.confirm(LITERATURE, first["job_id"])

    # Em 0 đi học, em 1 vắng không phép; còn lại như cũ.
    second = upload(imp, grid(imp, headers, {0: [""], 1: ["K"]})).json()

    assert second["summary"]["records_to_update"] == 2
    assert second["summary"]["records_unchanged"] == 38
    changed = next(r for r in second["rows"] if r["line"] == 2)
    assert changed["existing"] == {"lesson:2026-10-05:2": "Vắng CP"}
    imp.confirm(LITERATURE, second["job_id"])
    students = roster(imp)
    assert absences(imp) == {
        (date(2026, 10, 5), 2, students[1][2]): AttendanceStatus.ABSENT_UNEXCUSED
    }


@pytest.mark.db
@pytest.mark.parametrize(
    ("header", "cell", "fragment"),
    [
        ("05/10 Tiết 2", "x", "không hợp lệ"),
        ("05/10 Tiết 2", "Cử đi", "chủ nhiệm"),
        ("05/10 Tiết 11", "", "từ 1 đến 10"),
        ("05/08 Tiết 1", "", "ngoài năm học"),
        ("20/11 Tiết 1", "", "chưa tới"),
        ("05/10", "", "thiếu tiết"),
    ],
)
def test_bad_cells_and_headers_block_the_import(
    imp: ImportApi, header: str, cell: str, fragment: str
) -> None:
    body = upload(imp, grid(imp, [header], {0: [cell]})).json()

    assert body["can_confirm"] is False and body["summary"]["error_rows"] >= 1
    messages = [m["message"] for r in body["rows"] for m in r["messages"]]
    assert any(fragment in m for m in messages), messages


@pytest.mark.db
def test_a_lesson_already_taken_by_another_subject_is_an_error(imp: ImportApi) -> None:
    taken = upload(imp, grid(imp, ["05/10 Tiết 2"], {}), MATH, subject="Toán").json()
    imp.confirm(MATH, taken["job_id"])

    body = upload(imp, grid(imp, ["05/10 Tiết 2"], {0: ["P"]})).json()

    assert body["can_confirm"] is False
    assert any("Toán" in m["message"] for r in body["rows"] for m in r["messages"])


@pytest.mark.db
def test_two_columns_for_the_same_lesson_are_an_error(imp: ImportApi) -> None:
    body = upload(imp, grid(imp, ["05/10 Tiết 2", "5/10/2026 T2"], {})).json()
    assert body["can_confirm"] is False
    assert any("Trùng tiết" in m["message"] for r in body["rows"] for m in r["messages"])


@pytest.mark.db
def test_a_file_without_lesson_columns_lists_what_is_missing(imp: ImportApi) -> None:
    rows = [["Mã HS", "Họ và tên"], *[[c, n] for c, n, _ in roster(imp)]]
    body = upload(imp, rows).json()
    assert body["job_id"] is None
    assert any("cột tiết học" in m for m in body["missing_required"])


@pytest.mark.db
@pytest.mark.parametrize(
    "email",
    ["gvcn.11a2@example.com", "gv.toan.11@example.com", "bgh1@example.com", "admin@example.com"],
)
def test_only_the_assigned_subject_teacher_may_import(imp: ImportApi, email: str) -> None:
    response = upload(imp, grid(imp, ["05/10 Tiết 2"], {}), email)
    assert response.status_code == 403


@pytest.mark.db
def test_subject_is_required(imp: ImportApi) -> None:
    response = imp.upload(LITERATURE, "11A2", "lessons", build_csv([["Mã HS"], ["HS1"]]))
    assert response.status_code == 422 and "subject_id" in response.text
