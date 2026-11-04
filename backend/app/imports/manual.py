"""Sửa / nhập tay điểm của một học sinh (D-115).

Giáo viên bộ môn được phân công sửa vài đầu điểm của một em (kiểm tra lại, kiểm tra bù, nhập sai)
mà không phải tải lại cả tệp. Điểm mới thay hẳn điểm cũ; mỗi đầu điểm đổi giá trị được ghi một dòng
`assessment_changes` (cũ → mới, lý do, người sửa) cùng transaction với việc ghi điểm và nhật ký.

Quyền: xem dùng authorize() (GVBM đúng môn, GVCN, BGH); sửa dùng authorize_write() (chỉ GVBM được
phân công lớp–môn), như nhập điểm từ tệp. ĐTB không lưu ở đâu: Analytics tính khi đọc (D-052).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import repository as analytics_repo
from app.analytics.config import load_config
from app.auth.audit import record_access
from app.auth.models import User
from app.classes.academic import Assessment
from app.classes.models import ClassStudent, Student
from app.core.authorize import AuthorizationError, authorize, authorize_write
from app.core.enums import AssessmentKind, AssessmentType, AuditAction
from app.core.labels import label_vi
from app.imports.manual_schemas import (
    ScoreChangeOut,
    ScoreEntryOut,
    StudentScoresIn,
    StudentScoresOut,
)
from app.imports.models import AssessmentChange


class NotFound(Exception):
    """Lớp không có, lớp không học môn này, hoặc học sinh không thuộc lớp."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidEntries(Exception):
    """Đầu điểm gửi lên không hợp với môn (sai loại, số thứ tự ngoài phạm vi)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NothingChanged(Exception):
    """Mọi giá trị gửi lên đều trùng điểm đang có."""


@dataclass(frozen=True)
class _Target:
    class_student_id: int
    student_id: int
    student_code: str
    full_name: str
    subject_id: int
    subject_name: str
    is_comment: bool
    tx_required: int


def _target(session: Session, class_id: int, subject_id: int, student_id: int) -> _Target:
    if analytics_repo.get_class(session, class_id) is None:
        raise NotFound("Không có lớp này.")
    subject = next(
        (s for s in analytics_repo.class_subjects(session, class_id) if s.id == subject_id), None
    )
    if subject is None:
        raise NotFound("Lớp này không học môn này.")
    row = session.execute(
        select(ClassStudent.id, Student.id, Student.student_code, Student.full_name)
        .join(Student, Student.id == ClassStudent.student_id)
        .where(ClassStudent.class_id == class_id, ClassStudent.student_id == student_id)
    ).one_or_none()
    if row is None:
        raise NotFound("Học sinh này không thuộc lớp.")
    return _Target(
        class_student_id=row[0],
        student_id=row[1],
        student_code=row[2],
        full_name=row[3],
        subject_id=subject.id,
        subject_name=subject.name,
        is_comment=subject.assessment_type is AssessmentType.COMMENT,
        tx_required=load_config(session).required_regular(subject.periods_per_year),
    )


def _current(session: Session, target: _Target, semester: int) -> dict[tuple[str, int], Assessment]:
    rows = session.scalars(
        select(Assessment).where(
            Assessment.class_student_id == target.class_student_id,
            Assessment.subject_id == target.subject_id,
            Assessment.semester == semester,
        )
    )
    return {(row.kind.value, row.seq): row for row in rows}


def _can_edit(session: Session, user: User, class_id: int, subject_id: int) -> bool:
    try:
        authorize_write(session, user, class_id=class_id, subject_id=subject_id)
    except AuthorizationError:
        return False
    return True


def _out(
    session: Session, user: User, class_id: int, target: _Target, semester: int
) -> StudentScoresOut:
    current = _current(session, target, semester)
    existing_tx = [seq for (kind, seq) in current if kind == AssessmentKind.TX.value]
    history = session.execute(
        select(AssessmentChange, User.full_name)
        .join(User, User.id == AssessmentChange.changed_by)
        .where(
            AssessmentChange.class_student_id == target.class_student_id,
            AssessmentChange.subject_id == target.subject_id,
        )
        .order_by(AssessmentChange.changed_at.desc(), AssessmentChange.id.desc())
    ).all()
    order = {AssessmentKind.TX: 0, AssessmentKind.GK: 1, AssessmentKind.CK: 2}
    return StudentScoresOut(
        student_id=target.student_id,
        student_code=target.student_code,
        full_name=target.full_name,
        subject_id=target.subject_id,
        subject_name=target.subject_name,
        is_comment_subject=target.is_comment,
        semester=semester,
        tx_slots=0 if target.is_comment else max([target.tx_required, *existing_tx]),
        entries=[
            ScoreEntryOut(
                kind=row.kind, seq=row.seq, score=row.score, comment_result=row.comment_result
            )
            for row in sorted(current.values(), key=lambda r: (order[r.kind], r.seq))
        ],
        can_edit=_can_edit(session, user, class_id, target.subject_id),
        history=[
            ScoreChangeOut(
                semester=change.semester,
                kind=change.kind,
                seq=change.seq,
                old_score=change.old_score,
                new_score=change.new_score,
                old_comment_result=change.old_comment_result,
                new_comment_result=change.new_comment_result,
                reason=change.reason,
                reason_label=label_vi(change.reason),
                note=change.note,
                changed_by=name,
                changed_at=change.changed_at,
            )
            for change, name in history
        ],
    )


def get_student_scores(
    session: Session, user: User, class_id: int, subject_id: int, student_id: int, semester: int
) -> StudentScoresOut:
    authorize(session, user, class_id=class_id, subject_id=subject_id)
    target = _target(session, class_id, subject_id, student_id)
    out = _out(session, user, class_id, target, semester)
    record_access(
        session,
        user,
        AuditAction.VIEW_SUBJECT_SCORES,
        class_id=class_id,
        details={"subject_id": subject_id, "semester": semester, "student_id": student_id},
    )
    return out


def _check_entries(target: _Target, data: StudentScoresIn, existing_tx: list[int]) -> None:
    tx_limit = max([target.tx_required, *existing_tx])
    for entry in data.entries:
        if target.is_comment:
            if entry.kind is not AssessmentKind.CK or entry.comment_result is None:
                raise InvalidEntries(
                    f"Môn {target.subject_name} đánh giá bằng nhận xét: chỉ nhập Đạt / Chưa đạt."
                )
            continue
        if entry.score is None:
            raise InvalidEntries(f"Môn {target.subject_name} cần điểm số, không phải nhận xét.")
        if entry.kind is AssessmentKind.TX and entry.seq > tx_limit:
            raise InvalidEntries(
                f"Môn {target.subject_name} có {tx_limit} đầu điểm thường xuyên mỗi học kỳ."
            )


def save_student_scores(
    session: Session,
    user: User,
    class_id: int,
    subject_id: int,
    student_id: int,
    data: StudentScoresIn,
) -> int:
    """Ghi các đầu điểm đổi giá trị, trả số đầu điểm đã đổi. Không đổi gì thì NothingChanged."""
    authorize_write(session, user, class_id=class_id, subject_id=subject_id)
    target = _target(session, class_id, subject_id, student_id)
    current = _current(session, target, data.semester)
    _check_entries(
        target, data, [seq for (kind, seq) in current if kind == AssessmentKind.TX.value]
    )

    changed = 0
    for entry in data.entries:
        row = current.get((entry.kind.value, entry.seq))
        old_score = row.score if row else None
        old_comment = row.comment_result if row else None
        if row is not None and old_score == entry.score and old_comment == entry.comment_result:
            continue
        if row is None:
            session.add(
                Assessment(
                    class_student_id=target.class_student_id,
                    subject_id=target.subject_id,
                    semester=data.semester,
                    kind=entry.kind,
                    seq=entry.seq,
                    score=entry.score,
                    comment_result=entry.comment_result,
                )
            )
        else:
            row.score = entry.score
            row.comment_result = entry.comment_result
        session.add(
            AssessmentChange(
                class_student_id=target.class_student_id,
                subject_id=target.subject_id,
                semester=data.semester,
                kind=entry.kind,
                seq=entry.seq,
                old_score=old_score,
                new_score=entry.score,
                old_comment_result=old_comment,
                new_comment_result=entry.comment_result,
                reason=data.reason,
                note=data.note,
                changed_by=user.id,
            )
        )
        changed += 1
    if changed == 0:
        session.rollback()
        raise NothingChanged
    record_access(
        session,
        user,
        AuditAction.EDIT_SCORES,
        class_id=class_id,
        details={
            "subject_id": subject_id,
            "student_id": student_id,
            "semester": data.semester,
            "changed": changed,
            "reason": data.reason.value,
        },
        commit=False,
    )
    session.commit()
    return changed


def scores_after_save(
    session: Session, user: User, class_id: int, subject_id: int, student_id: int, semester: int
) -> StudentScoresOut:
    """Trạng thái mới sau khi lưu (không ghi thêm nhật ký xem: người sửa vừa ghi edit_scores)."""
    target = _target(session, class_id, subject_id, student_id)
    return _out(session, user, class_id, target, semester)
