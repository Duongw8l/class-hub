"""Schema xem và sửa / nhập tay rèn luyện của lớp chủ nhiệm (D-119)."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.analytics.schemas import ClassRefOut
from app.core.enums import ConductChangeReason, ConductLevel, ConductPeriod

MAX_COMMENT_CHARS = 500


class ConductEntryOut(BaseModel):
    period: ConductPeriod
    level: ConductLevel | None  # None: chưa có
    comment: str | None


class ConductRowOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    entries: list[ConductEntryOut]  # luôn đủ ba kỳ, theo thứ tự hk1, hk2, year
    change_count: int  # số lần đã sửa tay


class ClassConductOut(BaseModel):
    class_info: ClassRefOut
    can_edit: bool  # chỉ GVCN của lớp
    # Theo kỳ: số học sinh ở từng mức, khoá "missing" là chưa có.
    counts: dict[ConductPeriod, dict[str, int]]
    year_fillable: int  # số em đã có học kỳ II mà chưa có cả năm
    rows: list[ConductRowOut]


class ConductChangeOut(BaseModel):
    period: ConductPeriod
    old_level: ConductLevel | None
    new_level: ConductLevel
    old_comment: str | None
    new_comment: str | None
    reason: ConductChangeReason
    reason_label: str
    note: str | None
    changed_by: str  # họ tên người sửa
    changed_at: datetime


class StudentConductOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    entries: list[ConductEntryOut]
    can_edit: bool
    history: list[ConductChangeOut]  # mới nhất trước


class ConductEntryIn(BaseModel):
    period: ConductPeriod
    level: ConductLevel
    # Nhận xét mới; chuỗi rỗng hoặc None là xoá nhận xét.
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)

    @field_validator("comment")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class StudentConductIn(BaseModel):
    entries: list[ConductEntryIn] = Field(min_length=1, max_length=3)
    reason: ConductChangeReason
    note: str | None = Field(default=None, max_length=255)

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _check(self) -> "StudentConductIn":
        if self.reason is ConductChangeReason.OTHER and not self.note:
            raise ValueError('Lý do "Khác" cần ghi chú.')
        periods = [entry.period for entry in self.entries]
        if len(periods) != len(set(periods)):
            raise ValueError("Một kỳ được gửi hai lần.")
        return self


class YearFillOut(BaseModel):
    filled: int  # số em vừa được ghi cả năm theo học kỳ II
