"""Nhập sổ điểm danh theo tiết của giáo viên bộ môn từ tệp dạng lưới (D-121).

Dùng khi điểm danh không có mạng: giáo viên ghi trên Excel giống sổ giấy rồi tải lên sau.

- Mỗi học sinh một dòng (cột Mã HS, Họ và tên như các loại nhập khác).
- Mỗi tiết đã dạy một cột, tiêu đề gồm ngày và tiết: "05/10 T2", "05/10/2026 - Tiết 2",
  "Tiết 2 (5/10)", "2026-10-05 T2". Năm có thể bỏ: lấy theo năm học của lớp.
- Ô trống hoặc "Có mặt" là có mặt; P / CP / Có phép là vắng có phép; K / KP / Không phép là vắng
  không phép; M / Muộn là đi muộn. "Cử đi" không nhận ở đây: GVCN xác nhận ở điểm danh ngày.

Kết quả ghi vào cùng sổ theo tiết (`lessons`, `lesson_absences`, D-120): mỗi ô thay trạng thái
của em đó ở tiết đó; em không có trong tệp giữ nguyên. Tiết đã được môn khác điểm danh, ngày ngoài
năm học hoặc chưa tới, tiết ngoài 1 đến 10, hai cột trùng một tiết: lỗi, không ghi gì.
"""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.classes.academic import Lesson, LessonAbsence
from app.classes.models import Subject
from app.core.enums import AttendanceStatus
from app.imports.models import ImportJob
from app.imports.parsing import RawTable
from app.imports.validation import (
    RowResult,
    StudentRef,
    _check_duplicate,
    _header,
    _identify,
    _new_result,
    column_index,
)
from app.imports.values import CellError, parse_attendance_status

MAX_LESSON_NO = 10


def today() -> date:
    """Hôm nay (tách ra để test cố định được ngày)."""
    return date.today()


FIELD_PREFIX = "lesson:"  # tên trường động của một cột tiết: "lesson:2026-10-05:2"

_ISO = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_DMY = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2}|\d{4}))?(?!\d)")
_LESSON = re.compile(r"(?:tiet|t)\s*\.?\s*(\d{1,2})(?!\d)")

_SHORT = {
    AttendanceStatus.ABSENT_EXCUSED: "Vắng CP",
    AttendanceStatus.ABSENT_UNEXCUSED: "Vắng KP",
    AttendanceStatus.LATE: "Muộn",
}


@dataclass(frozen=True)
class LessonColumn:
    header: str
    position: int
    day: date
    lesson_no: int

    @property
    def field(self) -> str:
        return f"{FIELD_PREFIX}{self.day.isoformat()}:{self.lesson_no}"

    @property
    def label(self) -> str:
        return f"{self.day:%d/%m} T{self.lesson_no}"


@dataclass(frozen=True)
class HeaderProblem:
    header: str
    message: str


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _guess_year(day: int, month: int, first: date, last: date) -> date | None:
    for year in (first.year, last.year):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if first <= candidate <= last:
            return candidate
    try:
        return date(first.year, month, day)
    except ValueError:
        return None


def parse_lesson_header(header: str, first: date, last: date) -> tuple[date, int] | str | None:
    """(ngày, tiết) của một tiêu đề cột; chuỗi lỗi nếu có ngày mà hỏng; None nếu không phải cột
    tiết."""
    text = _fold(header)
    day: date | None = None
    rest = text
    if match := _ISO.search(text):
        year, month, number = (int(part) for part in match.groups())
        try:
            day = date(year, month, number)
        except ValueError:
            return f"Ngày trong tiêu đề '{header}' không có thật."
        rest = text[: match.start()] + " " + text[match.end() :]
    elif match := _DMY.search(text):
        number, month = int(match.group(1)), int(match.group(2))
        raw_year = match.group(3)
        try:
            if raw_year:
                year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
                day = date(year, month, number)
            else:
                day = _guess_year(number, month, first, last)
        except ValueError:
            day = None
        if day is None:
            return f"Ngày trong tiêu đề '{header}' không có thật."
        rest = text[: match.start()] + " " + text[match.end() :]
    lesson = _LESSON.search(rest)
    if day is None:
        return None  # không có ngày: không phải cột tiết (ví dụ STT, Ghi chú)
    if lesson is None:
        return f"Cột '{header}' có ngày nhưng thiếu tiết thứ mấy (ví dụ '{day:%d/%m} T2')."
    return day, int(lesson.group(1))


def lesson_columns(
    headers: Sequence[str], used: set[str], first: date, last: date
) -> tuple[list[LessonColumn], list[HeaderProblem]]:
    """Các cột tiết trong tiêu đề (bỏ các cột đã dùng cho Mã HS, Họ và tên) và các lỗi tiêu đề."""
    columns: list[LessonColumn] = []
    problems: list[HeaderProblem] = []
    for position, header in enumerate(headers):
        if not header or header in used:
            continue
        parsed = parse_lesson_header(header, first, last)
        if parsed is None:
            continue
        if isinstance(parsed, str):
            problems.append(HeaderProblem(header, parsed))
            continue
        columns.append(LessonColumn(header, position, parsed[0], parsed[1]))
    return columns, problems


@dataclass(frozen=True)
class ExistingLesson:
    subject_id: int
    subject_name: str
    marks: dict[int, AttendanceStatus]  # class_student_id -> trạng thái (chỉ em vắng / muộn)


def existing_lessons(session: Session, class_id: int) -> dict[tuple[date, int], ExistingLesson]:
    lessons = session.execute(
        select(Lesson.id, Lesson.date, Lesson.lesson_no, Lesson.subject_id, Subject.name)
        .join(Subject, Subject.id == Lesson.subject_id)
        .where(Lesson.class_id == class_id)
    ).all()
    marks: dict[int, dict[int, AttendanceStatus]] = defaultdict(dict)
    for lesson_id, class_student_id, status in session.execute(
        select(LessonAbsence.lesson_id, LessonAbsence.class_student_id, LessonAbsence.status)
        .join(Lesson, Lesson.id == LessonAbsence.lesson_id)
        .where(Lesson.class_id == class_id)
    ):
        marks[lesson_id][class_student_id] = status
    return {
        (day, number): ExistingLesson(subject_id, name, marks[lesson_id])
        for lesson_id, day, number, subject_id, name in lessons
    }


def _parse_cell(text: str) -> AttendanceStatus:
    if not text.strip():
        return AttendanceStatus.PRESENT
    status = parse_attendance_status(text)
    if status is AttendanceStatus.SCHOOL_DUTY:
        raise CellError(
            "Vắng do nhà trường cử đi do giáo viên chủ nhiệm xác nhận; ở tiết học hãy ghi P "
            "(vắng có phép)."
        )
    return status


def _column_problems(
    columns: Sequence[LessonColumn],
    header_problems: Sequence[HeaderProblem],
    *,
    subject_id: int,
    existing: Mapping[tuple[date, int], ExistingLesson],
    first: date,
    last: date,
    today: date,
) -> list[HeaderProblem]:
    problems = list(header_problems)
    seen: dict[tuple[date, int], str] = {}
    for column in columns:
        key = (column.day, column.lesson_no)
        other = existing.get(key)
        if not 1 <= column.lesson_no <= MAX_LESSON_NO:
            problems.append(HeaderProblem(column.header, "Tiết phải từ 1 đến 10."))
        elif not first <= column.day <= last:
            problems.append(HeaderProblem(column.header, "Ngày nằm ngoài năm học của lớp."))
        elif column.day > today:
            problems.append(HeaderProblem(column.header, "Ngày chưa tới: không điểm danh trước."))
        elif key in seen:
            problems.append(HeaderProblem(column.header, f"Trùng tiết với cột '{seen[key]}'."))
        elif other is not None and other.subject_id != subject_id:
            problems.append(
                HeaderProblem(
                    column.header,
                    f"Tiết này của lớp đã được điểm danh cho môn {other.subject_name}.",
                )
            )
        seen.setdefault(key, column.header)
    return problems


def validate_lessons(
    table: RawTable,
    mapping: Mapping[str, str | None],
    columns: Sequence[LessonColumn],
    header_problems: Sequence[HeaderProblem],
    *,
    students: Mapping[str, StudentRef],
    subject_id: int,
    existing: Mapping[tuple[date, int], ExistingLesson],
    first: date,
    last: date,
    today: date,
) -> list[RowResult]:
    index = column_index(table.headers, mapping)
    problems = _column_problems(
        columns,
        header_problems,
        subject_id=subject_id,
        existing=existing,
        first=first,
        last=last,
        today=today,
    )
    seen: dict[str, int] = {}
    results: list[RowResult] = []
    for number, row in enumerate(table.rows):
        result = _new_result(row, index)
        if number == 0:
            # Lỗi của tiêu đề cột: báo một lần ở dòng đầu (đủ để chặn xác nhận).
            for problem in problems:
                result.error(problem.header, problem.message)
        student = _identify(row, table, index, students, result)
        if student is not None:
            _check_duplicate(
                result,
                seen,
                result.student_code.upper(),
                _header(table.headers, index, "student_code", "Mã học sinh"),
                "Mã học sinh",
            )
        for column in columns:
            text = row.cells[column.position] if column.position < len(row.cells) else ""
            try:
                status = _parse_cell(text)
            except CellError as error:
                result.error(column.header, str(error))
                continue
            result.values[column.field] = _SHORT.get(status)
            if student is None:
                continue
            key = (column.day, column.lesson_no)
            lesson = existing.get(key)
            record = {
                "date": column.day.isoformat(),
                "lesson_no": column.lesson_no,
                "class_student_id": student.class_student_id,
                "status": status.value,
            }
            if lesson is None:
                result.new_records += 1
                result.records.append(record)
                continue
            old = lesson.marks.get(student.class_student_id, AttendanceStatus.PRESENT)
            if old is status:
                result.unchanged_records += 1
            else:
                result.changed_records += 1
                result.existing[column.field] = _SHORT.get(old)
                result.records.append(record)
        results.append(result.finish())
    return results


class LessonSlotTaken(Exception):
    """Lúc xác nhận, tiết đã bị môn khác điểm danh (sau khi xem trước)."""


def write_lessons(session: Session, job: ImportJob) -> tuple[int, int]:
    """Ghi các ô của job vào sổ theo tiết; trả (số ô tạo mới, số ô đổi)."""
    assert job.subject_id is not None
    grouped: dict[tuple[date, int], list[dict[str, Any]]] = defaultdict(list)
    for record in job.rows:
        grouped[(date.fromisoformat(record["date"]), int(record["lesson_no"]))].append(record)
    created = updated = 0
    for (day, number), records in grouped.items():
        lesson = session.scalar(
            select(Lesson).where(
                Lesson.class_id == job.class_id, Lesson.date == day, Lesson.lesson_no == number
            )
        )
        if lesson is not None and lesson.subject_id != job.subject_id:
            raise LessonSlotTaken
        if lesson is None:
            lesson = Lesson(
                class_id=job.class_id,
                subject_id=job.subject_id,
                date=day,
                lesson_no=number,
                recorded_by=job.user_id,
            )
            session.add(lesson)
            session.flush()
            created += len(records)
        else:
            lesson.recorded_by = job.user_id
            updated += len(records)
        ids = [int(r["class_student_id"]) for r in records]
        session.execute(
            delete(LessonAbsence).where(
                LessonAbsence.lesson_id == lesson.id, LessonAbsence.class_student_id.in_(ids)
            )
        )
        for record in records:
            status = AttendanceStatus(record["status"])
            if status is not AttendanceStatus.PRESENT:
                session.add(
                    LessonAbsence(
                        lesson_id=lesson.id,
                        class_student_id=int(record["class_student_id"]),
                        status=status,
                    )
                )
    session.flush()
    return created, updated
