"""Schema điểm danh ngày, điểm danh theo tiết và đối chiếu (D-120)."""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.analytics.attendance import AbsenceLevel
from app.analytics.schemas import ClassRefOut
from app.core.enums import AbsenceReason, AttendanceStatus

MAX_NOTE_CHARS = 255
LESSON_STATUSES = (
    AttendanceStatus.ABSENT_EXCUSED,
    AttendanceStatus.ABSENT_UNEXCUSED,
    AttendanceStatus.LATE,
)


def _strip(value: str | None) -> str | None:
    return value.strip() or None if value is not None else None


class AbsenceLimitsOut(BaseModel):
    notice: int  # nhắc từ mức này (30)
    high: int  # cảnh báo cao từ mức này (40)
    maximum: int  # quá mức này thì không đủ điều kiện lên lớp (45)


class YearAbsenceOut(BaseModel):
    """Cả năm học của một em. `absent_total` = có phép + không phép (Thông tư 22); vắng do nhà
    trường cử đi đếm riêng, không cộng vào."""

    excused: int
    unexcused: int
    late: int
    school_duty: int
    absent_total: int
    level: AbsenceLevel | None


# --- Điểm danh ngày (GVCN) -----------------------------------------------------------------------


class DayCellOut(BaseModel):
    date: date
    status: AttendanceStatus
    reason: AbsenceReason | None
    note: str | None


class AttendanceRowOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    cells: list[DayCellOut]  # các ngày của tháng đang xem đã có điểm danh
    year: YearAbsenceOut


class MismatchOut(BaseModel):
    """Điểm danh tiết và điểm danh ngày không khớp, để GVCN xác minh."""

    kind: Literal["lesson_absent_day_present", "day_absent_lesson_present"]
    student_id: int
    student_code: str
    full_name: str
    date: date
    subject_name: str
    lesson_no: int
    lesson_status: AttendanceStatus  # trạng thái ở tiết (present khi em không bị đánh dấu)
    day_status: AttendanceStatus | None  # None: ngày đó chưa điểm danh


class ClassAttendanceOut(BaseModel):
    class_info: ClassRefOut
    month: str  # YYYY-MM đang xem
    months: list[str]  # các tháng của năm học
    days: list[date]  # các ngày trong tháng đã có điểm danh
    limits: AbsenceLimitsOut
    can_edit: bool  # chỉ GVCN của lớp
    counts: dict[AbsenceLevel, int]  # số em ở từng mức (cả năm)
    rows: list[AttendanceRowOut]
    mismatches: list[MismatchOut]  # trong tháng đang xem


class DayEntryOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    status: AttendanceStatus | None  # None: chưa điểm danh ngày này
    reason: AbsenceReason | None
    note: str | None
    # Các tiết GVBM đã đánh dấu vắng / muộn trong ngày, để GVCN tham khảo khi điểm danh.
    lesson_marks: list[str]


class AttendanceChangeOut(BaseModel):
    student_id: int
    full_name: str
    old_status: AttendanceStatus | None
    new_status: AttendanceStatus
    old_reason: AbsenceReason | None
    new_reason: AbsenceReason | None
    note: str | None
    changed_by: str
    changed_at: datetime


class DayAttendanceOut(BaseModel):
    class_info: ClassRefOut
    date: date
    can_edit: bool
    entries: list[DayEntryOut]
    history: list[AttendanceChangeOut]  # các lần sửa tay của ngày này, mới nhất trước


class DayEntryIn(BaseModel):
    student_id: int
    status: AttendanceStatus
    reason: AbsenceReason | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_CHARS)

    @field_validator("note")
    @classmethod
    def _strip_note(cls, value: str | None) -> str | None:
        return _strip(value)

    @model_validator(mode="after")
    def _reason_only_when_away(self) -> Self:
        if self.status is AttendanceStatus.PRESENT and (self.reason or self.note):
            raise ValueError("Học sinh có mặt thì không ghi lý do vắng.")
        if self.reason is AbsenceReason.OTHER and not self.note:
            raise ValueError('Lý do "Khác" cần ghi chú.')
        return self


class DayAttendanceIn(BaseModel):
    entries: list[DayEntryIn] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [entry.student_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Một học sinh được gửi hai lần.")
        return self


class SaveResultOut(BaseModel):
    changed: int


# --- Điểm danh theo tiết (GVBM) ------------------------------------------------------------------


class LessonOut(BaseModel):
    date: date
    lesson_no: int
    excused: int
    unexcused: int
    late: int
    recorded_by: str
    updated_at: datetime


class StudentLessonSummaryOut(BaseModel):
    """Cả năm học, trong môn này: số tiết đã điểm danh và số tiết em vắng / muộn."""

    student_id: int
    student_code: str
    full_name: str
    excused: int
    unexcused: int
    late: int


class SubjectLessonsOut(BaseModel):
    class_info: ClassRefOut
    subject_id: int
    subject_name: str
    can_edit: bool  # GVBM được phân công lớp–môn
    month: str
    months: list[str]
    lesson_count: int  # số tiết đã điểm danh cả năm
    lessons: list[LessonOut]  # trong tháng đang xem, mới nhất trước
    students: list[StudentLessonSummaryOut]


class LessonEntryOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    status: AttendanceStatus  # present khi em không bị đánh dấu
    reason: AbsenceReason | None
    note: str | None


class LessonDetailOut(BaseModel):
    class_info: ClassRefOut
    subject_id: int
    subject_name: str
    date: date
    lesson_no: int
    exists: bool  # tiết này đã được điểm danh chưa
    # Môn khác đã điểm danh đúng tiết này của lớp (không ghi đè được).
    taken_by: str | None
    can_edit: bool
    entries: list[LessonEntryOut]


class LessonEntryIn(BaseModel):
    student_id: int
    status: AttendanceStatus
    reason: AbsenceReason | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_CHARS)

    @field_validator("note")
    @classmethod
    def _strip_note(cls, value: str | None) -> str | None:
        return _strip(value)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.status not in LESSON_STATUSES:
            raise ValueError(
                "Ở tiết học chỉ ghi vắng có phép, vắng không phép hoặc muộn; "
                "vắng do nhà trường cử đi do giáo viên chủ nhiệm xác nhận."
            )
        if self.reason is AbsenceReason.OTHER and not self.note:
            raise ValueError('Lý do "Khác" cần ghi chú.')
        return self


class LessonIn(BaseModel):
    # Chỉ các em vắng / muộn; em không có trong danh sách là có mặt. Danh sách rỗng: cả lớp có mặt.
    entries: list[LessonEntryIn] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [entry.student_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Một học sinh được gửi hai lần.")
        return self


class DeletedOut(BaseModel):
    deleted: bool
