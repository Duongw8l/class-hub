"""Xem và sửa / nhập tay rèn luyện của một lớp (D-119).

GVCN chấm rèn luyện cả lớp theo đợt (cuối mỗi học kỳ) nên có trang riêng: mỗi em một dòng, đủ ba kỳ
(học kỳ I, học kỳ II, cả năm) và nhận xét. Mức mới thay hẳn mức cũ; mỗi kỳ đổi mức hoặc nhận xét ghi
một dòng `conduct_changes` (cũ → mới, lý do, người sửa) cùng transaction với việc ghi và nhật ký.

Quyền: xem dùng authorize() + require_all_subjects() (GVCN của lớp và BGH, như dashboard lớp; GVBM
không xem rèn luyện, D-066); sửa dùng authorize_write() không có môn (chỉ GVCN của lớp), như nhập
rèn luyện từ tệp. Không xoá được một kết quả đã có.

"Cả năm theo học kỳ II" chỉ chép mức học kỳ II của em đã có vào kỳ cả năm khi kỳ này còn trống, đúng
giá trị mà Analytics đang tự suy ra (`analytics/conduct.py`); giáo viên bấm thì mới ghi.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import repository as analytics_repo
from app.analytics.schemas import ClassRefOut
from app.auth.audit import record_access
from app.auth.models import User
from app.classes.academic import ConductResult
from app.core.authorize import AuthorizationError, authorize, authorize_write
from app.core.enums import AuditAction, ConductChangeReason, ConductLevel, ConductPeriod
from app.core.labels import label_vi
from app.imports.conduct_schemas import (
    ClassConductOut,
    ConductChangeOut,
    ConductEntryOut,
    ConductRowOut,
    StudentConductIn,
    StudentConductOut,
)
from app.imports.models import ConductChange

PERIODS = (ConductPeriod.HK1, ConductPeriod.HK2, ConductPeriod.YEAR)
YEAR_FROM_HK2_NOTE = "Cả năm lấy theo học kỳ II"


class NotFound(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NothingChanged(Exception):
    """Mọi giá trị gửi lên đều trùng kết quả đang có."""


@dataclass(frozen=True)
class _Student:
    class_student_id: int
    student_id: int
    student_code: str
    full_name: str


def _class_ref(session: Session, class_id: int) -> ClassRefOut:
    info = analytics_repo.get_class(session, class_id)
    if info is None:
        raise NotFound("Không có lớp này.")
    return ClassRefOut(id=info.id, name=info.name, grade_level=info.grade_level)


def _authorize_view(session: Session, user: User, class_id: int) -> None:
    authorize(session, user, class_id=class_id).require_all_subjects()


def _can_edit(session: Session, user: User, class_id: int) -> bool:
    try:
        authorize_write(session, user, class_id=class_id)
    except AuthorizationError:
        return False
    return True


def _students(session: Session, class_id: int) -> list[_Student]:
    return [
        _Student(s.class_student_id, s.student_id, s.student_code, s.full_name)
        for s in analytics_repo.class_students(session, class_id)
    ]


def _student(session: Session, class_id: int, student_id: int) -> _Student:
    found = next((s for s in _students(session, class_id) if s.student_id == student_id), None)
    if found is None:
        raise NotFound("Học sinh này không thuộc lớp.")
    return found


def _results(
    session: Session, class_student_ids: list[int]
) -> dict[int, dict[ConductPeriod, ConductResult]]:
    rows = session.scalars(
        select(ConductResult).where(ConductResult.class_student_id.in_(class_student_ids))
    )
    by_student: dict[int, dict[ConductPeriod, ConductResult]] = defaultdict(dict)
    for row in rows:
        by_student[row.class_student_id][row.period] = row
    return by_student


def _entries(records: dict[ConductPeriod, ConductResult]) -> list[ConductEntryOut]:
    return [
        ConductEntryOut(
            period=period,
            level=records[period].level if period in records else None,
            comment=records[period].comment if period in records else None,
        )
        for period in PERIODS
    ]


# --- Xem ----------------------------------------------------------------------------------------


def class_conduct(session: Session, user: User, class_id: int) -> ClassConductOut:
    _authorize_view(session, user, class_id)
    class_ref = _class_ref(session, class_id)
    students = _students(session, class_id)
    ids = [s.class_student_id for s in students]
    results = _results(session, ids)
    changes = dict(
        session.execute(
            select(ConductChange.class_student_id, func.count())
            .where(ConductChange.class_student_id.in_(ids))
            .group_by(ConductChange.class_student_id)
        ).all()
    )
    counts: dict[ConductPeriod, dict[str, int]] = {}
    for period in PERIODS:
        tally = Counter(
            results[s.class_student_id][period].level.value
            if period in results[s.class_student_id]
            else "missing"
            for s in students
        )
        counts[period] = {
            key: tally.get(key, 0) for key in (*(lv.value for lv in ConductLevel), "missing")
        }
    out = ClassConductOut(
        class_info=class_ref,
        can_edit=_can_edit(session, user, class_id),
        counts=counts,
        year_fillable=sum(
            1
            for s in students
            if ConductPeriod.HK2 in results[s.class_student_id]
            and ConductPeriod.YEAR not in results[s.class_student_id]
        ),
        rows=[
            ConductRowOut(
                student_id=s.student_id,
                student_code=s.student_code,
                full_name=s.full_name,
                entries=_entries(results[s.class_student_id]),
                change_count=changes.get(s.class_student_id, 0),
            )
            for s in students
        ],
    )
    record_access(
        session,
        user,
        AuditAction.VIEW_CLASS_CONDUCT,
        class_id=class_id,
        details={"student_count": len(students)},
    )
    return out


def _student_out(
    session: Session, user: User, class_id: int, student: _Student
) -> StudentConductOut:
    records = _results(session, [student.class_student_id])[student.class_student_id]
    history = session.execute(
        select(ConductChange, User.full_name)
        .join(User, User.id == ConductChange.changed_by)
        .where(ConductChange.class_student_id == student.class_student_id)
        .order_by(ConductChange.changed_at.desc(), ConductChange.id.desc())
    ).all()
    return StudentConductOut(
        student_id=student.student_id,
        student_code=student.student_code,
        full_name=student.full_name,
        entries=_entries(records),
        can_edit=_can_edit(session, user, class_id),
        history=[
            ConductChangeOut(
                period=change.period,
                old_level=change.old_level,
                new_level=change.new_level,
                old_comment=change.old_comment,
                new_comment=change.new_comment,
                reason=change.reason,
                reason_label=label_vi(change.reason),
                note=change.note,
                changed_by=name,
                changed_at=change.changed_at,
            )
            for change, name in history
        ],
    )


def student_conduct(
    session: Session, user: User, class_id: int, student_id: int
) -> StudentConductOut:
    _authorize_view(session, user, class_id)
    _class_ref(session, class_id)
    student = _student(session, class_id, student_id)
    out = _student_out(session, user, class_id, student)
    record_access(
        session,
        user,
        AuditAction.VIEW_CLASS_CONDUCT,
        class_id=class_id,
        details={"student_id": student_id},
    )
    return out


# --- Sửa ----------------------------------------------------------------------------------------


def _record_change(
    session: Session,
    user: User,
    class_student_id: int,
    period: ConductPeriod,
    row: ConductResult | None,
    level: ConductLevel,
    comment: str | None,
    reason: ConductChangeReason,
    note: str | None,
) -> None:
    session.add(
        ConductChange(
            class_student_id=class_student_id,
            period=period,
            old_level=row.level if row else None,
            new_level=level,
            old_comment=row.comment if row else None,
            new_comment=comment,
            reason=reason,
            note=note,
            changed_by=user.id,
        )
    )
    if row is None:
        session.add(
            ConductResult(
                class_student_id=class_student_id, period=period, level=level, comment=comment
            )
        )
    else:
        row.level = level
        row.comment = comment


def save_student_conduct(
    session: Session, user: User, class_id: int, student_id: int, data: StudentConductIn
) -> int:
    """Ghi các kỳ đổi mức hoặc nhận xét, trả số kỳ đã đổi. Không đổi gì thì NothingChanged."""
    authorize_write(session, user, class_id=class_id)  # chỉ GVCN của lớp
    _class_ref(session, class_id)
    student = _student(session, class_id, student_id)
    records = _results(session, [student.class_student_id])[student.class_student_id]

    changed: list[str] = []
    for entry in data.entries:
        row = records.get(entry.period)
        if row is not None and row.level is entry.level and row.comment == entry.comment:
            continue
        _record_change(
            session,
            user,
            student.class_student_id,
            entry.period,
            row,
            entry.level,
            entry.comment,
            data.reason,
            data.note,
        )
        changed.append(entry.period.value)
    if not changed:
        session.rollback()
        raise NothingChanged
    record_access(
        session,
        user,
        AuditAction.EDIT_CONDUCT,
        class_id=class_id,
        details={"student_id": student_id, "periods": changed, "reason": data.reason.value},
        commit=False,
    )
    session.commit()
    return len(changed)


def conduct_after_save(
    session: Session, user: User, class_id: int, student_id: int
) -> StudentConductOut:
    """Trạng thái mới sau khi lưu (không ghi thêm nhật ký xem: người sửa vừa ghi edit_conduct)."""
    return _student_out(session, user, class_id, _student(session, class_id, student_id))


def fill_year_from_hk2(session: Session, user: User, class_id: int) -> int:
    """Ghi cả năm = học kỳ II cho các em đã có học kỳ II mà chưa có cả năm. Trả số em đã ghi."""
    authorize_write(session, user, class_id=class_id)
    _class_ref(session, class_id)
    students = _students(session, class_id)
    results = _results(session, [s.class_student_id for s in students])
    filled = 0
    for student in students:
        records = results[student.class_student_id]
        second = records.get(ConductPeriod.HK2)
        if second is None or ConductPeriod.YEAR in records:
            continue
        _record_change(
            session,
            user,
            student.class_student_id,
            ConductPeriod.YEAR,
            None,
            second.level,
            None,
            ConductChangeReason.SUPPLEMENT,
            YEAR_FROM_HK2_NOTE,
        )
        filled += 1
    if filled == 0:
        session.rollback()
        return 0
    record_access(
        session,
        user,
        AuditAction.EDIT_CONDUCT,
        class_id=class_id,
        details={"bulk": "year_from_hk2", "changed": filled},
        commit=False,
    )
    session.commit()
    return filled
