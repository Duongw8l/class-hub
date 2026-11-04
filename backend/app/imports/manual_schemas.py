"""Schema sửa / nhập tay điểm của một học sinh (D-115)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.analytics.schemas import Score
from app.core.enums import AssessmentKind, CommentResult, ScoreChangeReason

# 0 đến 10, tối đa 1 chữ số thập phân (như nhập từ tệp: không tự làm tròn).
ScoreIn = Annotated[Decimal, Field(ge=0, le=10, decimal_places=1)]


class ScoreEntryOut(BaseModel):
    kind: AssessmentKind
    seq: int
    score: Score | None
    comment_result: CommentResult | None


class ScoreChangeOut(BaseModel):
    semester: int
    kind: AssessmentKind
    seq: int
    old_score: Score | None
    new_score: Score | None
    old_comment_result: CommentResult | None
    new_comment_result: CommentResult | None
    reason: ScoreChangeReason
    reason_label: str
    note: str | None
    changed_by: str  # họ tên người sửa
    changed_at: datetime


class StudentScoresOut(BaseModel):
    """Các đầu điểm hiện có của một học sinh, một môn, một học kỳ, và lịch sử sửa của môn đó."""

    student_id: int
    student_code: str
    full_name: str
    subject_id: int
    subject_name: str
    is_comment_subject: bool
    semester: int
    # Số ô điểm thường xuyên hiển thị: số đầu điểm bắt buộc, hoặc nhiều hơn nếu đã có.
    tx_slots: int
    entries: list[ScoreEntryOut]
    can_edit: bool  # người xem có quyền sửa (GVBM được phân công lớp–môn)
    history: list[ScoreChangeOut]  # cả hai học kỳ, mới nhất trước


class ScoreEntryIn(BaseModel):
    kind: AssessmentKind
    seq: int = Field(ge=1, le=20)
    score: ScoreIn | None = None
    comment_result: CommentResult | None = None

    @model_validator(mode="after")
    def _exactly_one_value(self) -> "ScoreEntryIn":
        if (self.score is None) == (self.comment_result is None):
            raise ValueError("Mỗi đầu điểm cần đúng một giá trị: điểm số hoặc Đạt / Chưa đạt.")
        if self.kind is not AssessmentKind.TX and self.seq != 1:
            raise ValueError("Điểm giữa kỳ và cuối kỳ chỉ có một đầu điểm.")
        return self


class StudentScoresIn(BaseModel):
    semester: int = Field(ge=1, le=2)
    entries: list[ScoreEntryIn] = Field(min_length=1, max_length=30)
    reason: ScoreChangeReason
    note: str | None = Field(default=None, max_length=255)

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _note_for_other(self) -> "StudentScoresIn":
        if self.reason is ScoreChangeReason.OTHER and not self.note:
            raise ValueError('Lý do "Khác" cần ghi chú.')
        keys = [(e.kind, e.seq) for e in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("Một đầu điểm được gửi hai lần.")
        return self
