"""Sổ điểm, điểm danh, rèn luyện và đăng ký thi: dữ liệu học vụ gắn với một học sinh trong một lớp.

Bảng con của class_students dùng ON DELETE CASCADE: xoá một lượt xếp lớp thì xoá luôn dữ liệu của
nó. Điểm lưu bằng NUMERIC (Decimal), không dùng float: có học sinh biên đúng 3,5 và 5,0.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, IntPk, enum_type
from app.core.enums import (
    AbsenceReason,
    AssessmentKind,
    AttendanceStatus,
    CommentResult,
    ConductLevel,
    ConductPeriod,
)


class Assessment(Base):
    """Một đầu điểm (hoặc một nhận xét Đạt / Chưa đạt) của học sinh trong một học kỳ.

    Môn tính điểm: kind tx (seq 1..n), gk (seq 1), ck (seq 1), có `score`.
    Môn nhận xét: mỗi học kỳ một dòng kind ck, seq 1, `score` NULL, có `comment_result` (D-035).
    """

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("semester IN (1, 2)", name="semester"),
        CheckConstraint("seq >= 1", name="seq_positive"),
        CheckConstraint("kind = 'tx' OR seq = 1", name="seq_one_unless_tx"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 10)", name="score_range"),
        # Đúng một trong hai: điểm số hoặc nhận xét.
        CheckConstraint("(score IS NULL) <> (comment_result IS NULL)", name="score_xor_comment"),
        UniqueConstraint(
            "class_student_id",
            "subject_id",
            "semester",
            "kind",
            "seq",
            name="uq_assessments_cs_subject_sem_kind_seq",
        ),
        Index("ix_assessments_subject_semester", "subject_id", "semester"),
    )

    id: Mapped[IntPk]
    class_student_id: Mapped[int] = mapped_column(
        ForeignKey("class_students.id", ondelete="CASCADE")
    )
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    semester: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[AssessmentKind] = mapped_column(enum_type(AssessmentKind, "kind"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    comment_result: Mapped[CommentResult | None] = mapped_column(
        enum_type(CommentResult, "comment_result")
    )


class Attendance(Base):
    """Một dòng cho mỗi ngày học của mỗi học sinh. Dòng nghỉ (có phép / không phép) tính là
    1 buổi nghỉ (D-028)."""

    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("class_student_id", "date", name="uq_attendance_cs_date"),
        Index("ix_attendance_date", "date"),
    )

    id: Mapped[IntPk]
    class_student_id: Mapped[int] = mapped_column(
        ForeignKey("class_students.id", ondelete="CASCADE")
    )
    date: Mapped[date] = mapped_column(Date)
    status: Mapped[AttendanceStatus] = mapped_column(enum_type(AttendanceStatus, "status"))
    # Lý do vắng và ghi chú (D-120); để trống với "có mặt" hoặc khi nhập từ tệp.
    reason: Mapped[AbsenceReason | None] = mapped_column(enum_type(AbsenceReason, "reason"))
    note: Mapped[str | None] = mapped_column(String(255))


class ConductResult(Base):
    __tablename__ = "conduct_results"
    __table_args__ = (
        UniqueConstraint("class_student_id", "period", name="uq_conduct_results_cs_period"),
    )

    id: Mapped[IntPk]
    class_student_id: Mapped[int] = mapped_column(
        ForeignKey("class_students.id", ondelete="CASCADE")
    )
    period: Mapped[ConductPeriod] = mapped_column(enum_type(ConductPeriod, "period"))
    level: Mapped[ConductLevel] = mapped_column(enum_type(ConductLevel, "level"))
    comment: Mapped[str | None] = mapped_column(Text)


class ExamRegistration(Base):
    """Môn đăng ký thi tốt nghiệp (khối 12)."""

    __tablename__ = "exam_registrations"
    __table_args__ = (
        UniqueConstraint("class_student_id", "subject_id", name="uq_exam_registrations_cs_subject"),
    )

    id: Mapped[IntPk]
    class_student_id: Mapped[int] = mapped_column(
        ForeignKey("class_students.id", ondelete="CASCADE")
    )
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))


class Lesson(Base):
    """Một tiết học đã được giáo viên bộ môn điểm danh (D-120): lớp, môn, ngày, tiết thứ mấy.

    Sổ theo tiết riêng, không thay điểm danh ngày của GVCN (số buổi nghỉ chính thức vẫn từ bảng
    `attendance`). Mỗi lớp mỗi ngày mỗi tiết chỉ một môn. Chỉ lưu em vắng / muộn
    (`lesson_absences`); em không có dòng là có mặt.
    """

    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("class_id", "date", "lesson_no", name="uq_lessons_class_date_no"),
        CheckConstraint("lesson_no BETWEEN 1 AND 10", name="lesson_no"),
        Index("ix_lessons_class_subject_date", "class_id", "subject_id", "date"),
    )

    id: Mapped[IntPk]
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    date: Mapped[date] = mapped_column(Date)
    lesson_no: Mapped[int] = mapped_column(SmallInteger)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LessonAbsence(Base):
    """Một học sinh vắng hoặc đi muộn trong một tiết (D-120)."""

    __tablename__ = "lesson_absences"
    __table_args__ = (
        UniqueConstraint("lesson_id", "class_student_id", name="uq_lesson_absences_lesson_cs"),
        # Giáo viên bộ môn chỉ ghi vắng có phép / không phép / muộn; "cử đi" do GVCN xác nhận.
        CheckConstraint(
            "status IN ('absent_excused', 'absent_unexcused', 'late')", name="lesson_status"
        ),
    )

    id: Mapped[IntPk]
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    class_student_id: Mapped[int] = mapped_column(
        ForeignKey("class_students.id", ondelete="CASCADE")
    )
    status: Mapped[AttendanceStatus] = mapped_column(enum_type(AttendanceStatus, "status"))
    reason: Mapped[AbsenceReason | None] = mapped_column(enum_type(AbsenceReason, "reason"))
    note: Mapped[str | None] = mapped_column(String(255))
