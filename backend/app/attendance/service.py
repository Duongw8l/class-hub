"""Điểm danh ngày của GVCN, sổ điểm danh theo tiết của GVBM và đối chiếu hai bên (D-120).

Quyền (nguyên tắc 4, gọi TRƯỚC khi đọc dữ liệu):
- Điểm danh ngày: xem qua authorize() + require_all_subjects() (GVCN của lớp, BGH; GVBM không xem
  chuyên cần, D-066); ghi qua authorize_write() không có môn (chỉ GVCN của lớp). Chỉ GVCN ghi được
  "vắng do nhà trường cử đi".
- Theo tiết: xem qua authorize(class_id, subject_id) (GVBM đúng lớp–môn, GVCN, BGH); ghi qua
  authorize_write(class_id, subject_id) (chỉ GVBM được phân công).

Số buổi nghỉ chính thức (mức 45 buổi, cảnh báo sớm) vẫn chỉ đếm từ điểm danh ngày (`attendance`);
sổ theo tiết là sổ theo dõi tham gia tiết học của môn, dùng để đối chiếu.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.analytics import repository as analytics_repo
from app.analytics.attendance import absence_level, attendance_summary
from app.analytics.config import load_config
from app.analytics.schemas import ClassRefOut
from app.attendance.schemas import (
    AbsenceLimitsOut,
    AttendanceChangeOut,
    AttendanceRowOut,
    ClassAttendanceOut,
    DayAttendanceIn,
    DayAttendanceOut,
    DayCellOut,
    DayEntryOut,
    LessonDetailOut,
    LessonEntryOut,
    LessonIn,
    LessonOut,
    MismatchOut,
    StudentLessonSummaryOut,
    SubjectLessonsOut,
    YearAbsenceOut,
)
from app.auth.audit import record_access
from app.auth.models import User
from app.classes.academic import Attendance, Lesson, LessonAbsence
from app.classes.models import Subject
from app.core.authorize import AuthorizationError, authorize, authorize_write
from app.core.enums import ABSENT_STATUSES, AttendanceStatus, AuditAction
from app.imports.models import AttendanceChange

SHORT_STATUS = {
    AttendanceStatus.ABSENT_EXCUSED: "vắng có phép",
    AttendanceStatus.ABSENT_UNEXCUSED: "vắng không phép",
    AttendanceStatus.LATE: "muộn",
}


class NotFound(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Invalid(Exception):
    """Yêu cầu hợp lệ về hình dạng nhưng không hợp với dữ liệu (ngày ngoài năm học…)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SlotTaken(Exception):
    """Tiết này của lớp đã được môn khác điểm danh."""

    def __init__(self, subject_name: str) -> None:
        super().__init__(subject_name)
        self.message = (
            f"Tiết này của lớp đã được điểm danh cho môn {subject_name}. Hãy kiểm tra lại ngày và "
            "tiết thứ mấy."
        )


class NothingChanged(Exception):
    pass


@dataclass(frozen=True)
class _Student:
    class_student_id: int
    student_id: int
    student_code: str
    full_name: str


# --- Dùng chung ---------------------------------------------------------------------------------


def _class_ref(session: Session, class_id: int) -> ClassRefOut:
    info = analytics_repo.get_class(session, class_id)
    if info is None:
        raise NotFound("Không có lớp này.")
    return ClassRefOut(id=info.id, name=info.name, grade_level=info.grade_level)


def _students(session: Session, class_id: int) -> list[_Student]:
    return [
        _Student(s.class_student_id, s.student_id, s.student_code, s.full_name)
        for s in analytics_repo.class_students(session, class_id)
    ]


def _by_student_id(students: list[_Student], student_id: int) -> _Student:
    found = next((s for s in students if s.student_id == student_id), None)
    if found is None:
        raise Invalid("Có học sinh không thuộc lớp này.")
    return found


def _year_range(session: Session, class_id: int) -> tuple[date, date]:
    return analytics_repo.school_year_range(session, class_id)


def _months(first: date, last: date) -> list[str]:
    months: list[str] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _month_bounds(month: str) -> tuple[date, date]:
    year, number = (int(part) for part in month.split("-"))
    start = date(year, number, 1)
    end = date(year + 1, 1, 1) if number == 12 else date(year, number + 1, 1)
    return start, end


def _pick_month(months: list[str], month: str | None, today: date) -> str:
    if month is not None:
        if month not in months:
            raise Invalid("Tháng này không thuộc năm học của lớp.")
        return month
    current = f"{today.year:04d}-{today.month:02d}"
    if current in months:
        return current
    return months[-1] if current > months[-1] else months[0]


def _check_day(session: Session, class_id: int, day: date, today: date) -> None:
    first, last = _year_range(session, class_id)
    if not first <= day <= last:
        raise Invalid("Ngày này nằm ngoài năm học của lớp.")
    if day > today:
        raise Invalid("Không điểm danh trước cho ngày chưa tới.")


def _can(fn: object) -> bool:
    try:
        fn()  # type: ignore[operator]
    except AuthorizationError:
        return False
    return True


def _limits(session: Session) -> AbsenceLimitsOut:
    config = load_config(session)
    return AbsenceLimitsOut(
        notice=config.absent_warning_notice,
        high=config.absent_warning_high,
        maximum=config.max_absent_sessions,
    )


# --- Điểm danh ngày ------------------------------------------------------------------------------


def _authorize_day_view(session: Session, user: User, class_id: int) -> None:
    authorize(session, user, class_id=class_id).require_all_subjects()


def _lesson_rows(
    session: Session, class_id: int, start: date, end: date
) -> list[tuple[int, date, int, str, int, AttendanceStatus | None]]:
    """Mọi tiết đã điểm danh trong [start, end) kèm em vắng / muộn: (lesson_id, ngày, tiết, tên môn,
    class_student_id hoặc 0 khi tiết không ai vắng, trạng thái)."""
    rows = session.execute(
        select(
            Lesson.id,
            Lesson.date,
            Lesson.lesson_no,
            Subject.name,
            LessonAbsence.class_student_id,
            LessonAbsence.status,
        )
        .join(Subject, Subject.id == Lesson.subject_id)
        .outerjoin(LessonAbsence, LessonAbsence.lesson_id == Lesson.id)
        .where(Lesson.class_id == class_id, Lesson.date >= start, Lesson.date < end)
        .order_by(Lesson.date, Lesson.lesson_no)
    ).all()
    return [(r[0], r[1], r[2], r[3], r[4] or 0, r[5]) for r in rows]


def _mismatches(
    students: list[_Student],
    day_status: dict[tuple[int, date], AttendanceStatus],
    lessons: list[tuple[int, date, int, str, int, AttendanceStatus | None]],
) -> list[MismatchOut]:
    lesson_info: dict[int, tuple[date, int, str]] = {}
    marked: dict[int, dict[int, AttendanceStatus]] = defaultdict(dict)
    for lesson_id, day, number, subject, class_student_id, status in lessons:
        lesson_info[lesson_id] = (day, number, subject)
        if class_student_id and status is not None:
            marked[lesson_id][class_student_id] = status

    result: list[MismatchOut] = []
    for lesson_id, (day, number, subject) in lesson_info.items():
        for student in students:
            in_lesson = marked[lesson_id].get(student.class_student_id, AttendanceStatus.PRESENT)
            on_day = day_status.get((student.class_student_id, day))
            lesson_absent = in_lesson in ABSENT_STATUSES
            day_absent = on_day in ABSENT_STATUSES
            # Cử đi: ngày ghi "cử đi" mà tiết ghi vắng là khớp (em đi thi); không báo.
            if lesson_absent and on_day in (None, AttendanceStatus.PRESENT, AttendanceStatus.LATE):
                kind = "lesson_absent_day_present"
            elif day_absent and in_lesson is AttendanceStatus.PRESENT:
                kind = "day_absent_lesson_present"
            else:
                continue
            result.append(
                MismatchOut(
                    kind=kind,
                    student_id=student.student_id,
                    student_code=student.student_code,
                    full_name=student.full_name,
                    date=day,
                    subject_name=subject,
                    lesson_no=number,
                    lesson_status=in_lesson,
                    day_status=on_day,
                )
            )
    result.sort(key=lambda m: (m.date, m.lesson_no, m.student_code))
    return result


def class_attendance(
    session: Session, user: User, class_id: int, month: str | None, today: date
) -> ClassAttendanceOut:
    _authorize_day_view(session, user, class_id)
    class_ref = _class_ref(session, class_id)
    first, last = _year_range(session, class_id)
    months = _months(first, last)
    chosen = _pick_month(months, month, today)
    start, end = _month_bounds(chosen)
    students = _students(session, class_id)
    ids = [s.class_student_id for s in students]
    limits = _limits(session)

    records = session.scalars(select(Attendance).where(Attendance.class_student_id.in_(ids))).all()
    by_student: dict[int, list[Attendance]] = defaultdict(list)
    for record in records:
        by_student[record.class_student_id].append(record)

    rows: list[AttendanceRowOut] = []
    counts = {"over": 0, "high": 0, "notice": 0}
    for student in students:
        mine = by_student[student.class_student_id]
        summary = attendance_summary((r.date, r.status) for r in mine)
        level = absence_level(
            summary.absent_total,
            notice=limits.notice,
            high=limits.high,
            maximum=limits.maximum,
        )
        if level is not None:
            counts[level] += 1
        rows.append(
            AttendanceRowOut(
                student_id=student.student_id,
                student_code=student.student_code,
                full_name=student.full_name,
                cells=[
                    DayCellOut(date=r.date, status=r.status, reason=r.reason, note=r.note)
                    for r in sorted(mine, key=lambda r: r.date)
                    if start <= r.date < end
                ],
                year=YearAbsenceOut(
                    excused=summary.excused,
                    unexcused=summary.unexcused,
                    late=summary.late,
                    school_duty=summary.school_duty,
                    absent_total=summary.absent_total,
                    level=level,
                ),
            )
        )
    days = sorted({r.date for r in records if start <= r.date < end})
    day_status = {(r.class_student_id, r.date): r.status for r in records if start <= r.date < end}
    out = ClassAttendanceOut(
        class_info=class_ref,
        month=chosen,
        months=months,
        days=days,
        limits=limits,
        can_edit=_can(lambda: authorize_write(session, user, class_id=class_id)),
        counts=counts,
        rows=rows,
        mismatches=_mismatches(students, day_status, _lesson_rows(session, class_id, start, end)),
    )
    record_access(
        session,
        user,
        AuditAction.VIEW_ATTENDANCE,
        class_id=class_id,
        details={"month": chosen, "student_count": len(students)},
    )
    return out


def _day_out(
    session: Session, user: User, class_id: int, class_ref: ClassRefOut, day: date
) -> DayAttendanceOut:
    students = _students(session, class_id)
    ids = [s.class_student_id for s in students]
    records = {
        r.class_student_id: r
        for r in session.scalars(
            select(Attendance).where(Attendance.class_student_id.in_(ids), Attendance.date == day)
        )
    }
    marks: dict[int, list[str]] = defaultdict(list)
    for _lesson, _day, number, subject, class_student_id, status in _lesson_rows(
        session, class_id, day, date.fromordinal(day.toordinal() + 1)
    ):
        if class_student_id and status is not None:
            marks[class_student_id].append(f"Tiết {number} {subject}: {SHORT_STATUS[status]}")
    names = {s.class_student_id: (s.student_id, s.full_name) for s in students}
    history = session.execute(
        select(AttendanceChange, User.full_name)
        .join(User, User.id == AttendanceChange.changed_by)
        .where(AttendanceChange.class_student_id.in_(ids), AttendanceChange.date == day)
        .order_by(AttendanceChange.changed_at.desc(), AttendanceChange.id.desc())
    ).all()
    return DayAttendanceOut(
        class_info=class_ref,
        date=day,
        can_edit=_can(lambda: authorize_write(session, user, class_id=class_id)),
        entries=[
            DayEntryOut(
                student_id=s.student_id,
                student_code=s.student_code,
                full_name=s.full_name,
                status=records[s.class_student_id].status
                if s.class_student_id in records
                else None,
                reason=records[s.class_student_id].reason
                if s.class_student_id in records
                else None,
                note=records[s.class_student_id].note if s.class_student_id in records else None,
                lesson_marks=marks[s.class_student_id],
            )
            for s in students
        ],
        history=[
            AttendanceChangeOut(
                student_id=names[change.class_student_id][0],
                full_name=names[change.class_student_id][1],
                old_status=change.old_status,
                new_status=change.new_status,
                old_reason=change.old_reason,
                new_reason=change.new_reason,
                note=change.note,
                changed_by=name,
                changed_at=change.changed_at,
            )
            for change, name in history
            if change.class_student_id in names
        ],
    )


def day_attendance(session: Session, user: User, class_id: int, day: date) -> DayAttendanceOut:
    _authorize_day_view(session, user, class_id)
    class_ref = _class_ref(session, class_id)
    out = _day_out(session, user, class_id, class_ref, day)
    record_access(
        session, user, AuditAction.VIEW_ATTENDANCE, class_id=class_id, details={"date": str(day)}
    )
    return out


def save_day(
    session: Session, user: User, class_id: int, day: date, data: DayAttendanceIn, today: date
) -> int:
    """Ghi điểm danh một ngày (cả lớp hoặc vài em); trả số em đổi. Không đổi gì: NothingChanged."""
    authorize_write(session, user, class_id=class_id)  # chỉ GVCN của lớp
    _class_ref(session, class_id)
    _check_day(session, class_id, day, today)
    students = _students(session, class_id)
    targets = [(_by_student_id(students, e.student_id), e) for e in data.entries]
    existing = {
        r.class_student_id: r
        for r in session.scalars(
            select(Attendance).where(
                Attendance.class_student_id.in_([s.class_student_id for s, _ in targets]),
                Attendance.date == day,
            )
        )
    }
    changed = 0
    for student, entry in targets:
        row = existing.get(student.class_student_id)
        if (
            row is not None
            and row.status is entry.status
            and row.reason == entry.reason
            and row.note == entry.note
        ):
            continue
        session.add(
            AttendanceChange(
                class_student_id=student.class_student_id,
                date=day,
                old_status=row.status if row else None,
                new_status=entry.status,
                old_reason=row.reason if row else None,
                new_reason=entry.reason,
                note=entry.note,
                changed_by=user.id,
            )
        )
        if row is None:
            session.add(
                Attendance(
                    class_student_id=student.class_student_id,
                    date=day,
                    status=entry.status,
                    reason=entry.reason,
                    note=entry.note,
                )
            )
        else:
            row.status, row.reason, row.note = entry.status, entry.reason, entry.note
        changed += 1
    if changed == 0:
        session.rollback()
        raise NothingChanged
    record_access(
        session,
        user,
        AuditAction.EDIT_ATTENDANCE,
        class_id=class_id,
        details={"date": str(day), "changed": changed},
        commit=False,
    )
    session.commit()
    return changed


def day_after_save(session: Session, user: User, class_id: int, day: date) -> DayAttendanceOut:
    return _day_out(session, user, class_id, _class_ref(session, class_id), day)


# --- Điểm danh theo tiết -------------------------------------------------------------------------


def _subject_name(session: Session, class_id: int, subject_id: int) -> str:
    subject = next(
        (s for s in analytics_repo.class_subjects(session, class_id) if s.id == subject_id), None
    )
    if subject is None:
        raise NotFound("Lớp này không học môn này.")
    return subject.name


def subject_lessons(
    session: Session, user: User, class_id: int, subject_id: int, month: str | None, today: date
) -> SubjectLessonsOut:
    authorize(session, user, class_id=class_id, subject_id=subject_id)
    class_ref = _class_ref(session, class_id)
    subject_name = _subject_name(session, class_id, subject_id)
    first, last = _year_range(session, class_id)
    months = _months(first, last)
    chosen = _pick_month(months, month, today)
    start, end = _month_bounds(chosen)

    lessons = session.execute(
        select(Lesson, User.full_name)
        .join(User, User.id == Lesson.recorded_by)
        .where(Lesson.class_id == class_id, Lesson.subject_id == subject_id)
        .order_by(Lesson.date.desc(), Lesson.lesson_no.desc())
    ).all()
    absences = session.execute(
        select(LessonAbsence.lesson_id, LessonAbsence.class_student_id, LessonAbsence.status)
        .join(Lesson, Lesson.id == LessonAbsence.lesson_id)
        .where(Lesson.class_id == class_id, Lesson.subject_id == subject_id)
    ).all()
    per_lesson: dict[int, dict[AttendanceStatus, int]] = defaultdict(lambda: defaultdict(int))
    per_student: dict[int, dict[AttendanceStatus, int]] = defaultdict(lambda: defaultdict(int))
    for lesson_id, class_student_id, status in absences:
        per_lesson[lesson_id][status] += 1
        per_student[class_student_id][status] += 1

    out = SubjectLessonsOut(
        class_info=class_ref,
        subject_id=subject_id,
        subject_name=subject_name,
        can_edit=_can(
            lambda: authorize_write(session, user, class_id=class_id, subject_id=subject_id)
        ),
        month=chosen,
        months=months,
        lesson_count=len(lessons),
        lessons=[
            LessonOut(
                date=lesson.date,
                lesson_no=lesson.lesson_no,
                excused=per_lesson[lesson.id][AttendanceStatus.ABSENT_EXCUSED],
                unexcused=per_lesson[lesson.id][AttendanceStatus.ABSENT_UNEXCUSED],
                late=per_lesson[lesson.id][AttendanceStatus.LATE],
                recorded_by=name,
                updated_at=lesson.updated_at,
            )
            for lesson, name in lessons
            if start <= lesson.date < end
        ],
        students=[
            StudentLessonSummaryOut(
                student_id=s.student_id,
                student_code=s.student_code,
                full_name=s.full_name,
                excused=per_student[s.class_student_id][AttendanceStatus.ABSENT_EXCUSED],
                unexcused=per_student[s.class_student_id][AttendanceStatus.ABSENT_UNEXCUSED],
                late=per_student[s.class_student_id][AttendanceStatus.LATE],
            )
            for s in _students(session, class_id)
        ],
    )
    record_access(
        session,
        user,
        AuditAction.VIEW_LESSONS,
        class_id=class_id,
        details={"subject_id": subject_id, "month": chosen},
    )
    return out


def _find_lesson(session: Session, class_id: int, day: date, number: int) -> Lesson | None:
    return session.scalar(
        select(Lesson).where(
            Lesson.class_id == class_id, Lesson.date == day, Lesson.lesson_no == number
        )
    )


def _lesson_out(
    session: Session, user: User, class_id: int, subject_id: int, day: date, number: int
) -> LessonDetailOut:
    class_ref = _class_ref(session, class_id)
    subject_name = _subject_name(session, class_id, subject_id)
    lesson = _find_lesson(session, class_id, day, number)
    taken_by = None
    marks: dict[int, LessonAbsence] = {}
    if lesson is not None and lesson.subject_id != subject_id:
        taken_by = session.scalar(select(Subject.name).where(Subject.id == lesson.subject_id))
    elif lesson is not None:
        marks = {
            a.class_student_id: a
            for a in session.scalars(
                select(LessonAbsence).where(LessonAbsence.lesson_id == lesson.id)
            )
        }
    return LessonDetailOut(
        class_info=class_ref,
        subject_id=subject_id,
        subject_name=subject_name,
        date=day,
        lesson_no=number,
        exists=lesson is not None and taken_by is None,
        taken_by=taken_by,
        can_edit=_can(
            lambda: authorize_write(session, user, class_id=class_id, subject_id=subject_id)
        ),
        entries=[
            LessonEntryOut(
                student_id=s.student_id,
                student_code=s.student_code,
                full_name=s.full_name,
                status=marks[s.class_student_id].status
                if s.class_student_id in marks
                else AttendanceStatus.PRESENT,
                reason=marks[s.class_student_id].reason if s.class_student_id in marks else None,
                note=marks[s.class_student_id].note if s.class_student_id in marks else None,
            )
            for s in _students(session, class_id)
        ],
    )


def lesson_detail(
    session: Session, user: User, class_id: int, subject_id: int, day: date, number: int
) -> LessonDetailOut:
    authorize(session, user, class_id=class_id, subject_id=subject_id)
    out = _lesson_out(session, user, class_id, subject_id, day, number)
    record_access(
        session,
        user,
        AuditAction.VIEW_LESSONS,
        class_id=class_id,
        details={"subject_id": subject_id, "date": str(day), "lesson_no": number},
    )
    return out


def save_lesson(
    session: Session,
    user: User,
    class_id: int,
    subject_id: int,
    day: date,
    number: int,
    data: LessonIn,
    today: date,
) -> LessonDetailOut:
    """Tạo hoặc ghi lại một tiết: danh sách em vắng / muộn thay hẳn danh sách cũ."""
    authorize_write(session, user, class_id=class_id, subject_id=subject_id)
    _class_ref(session, class_id)
    _subject_name(session, class_id, subject_id)
    _check_day(session, class_id, day, today)
    students = _students(session, class_id)
    targets = [(_by_student_id(students, e.student_id), e) for e in data.entries]

    lesson = _find_lesson(session, class_id, day, number)
    if lesson is not None and lesson.subject_id != subject_id:
        other = session.scalar(select(Subject.name).where(Subject.id == lesson.subject_id))
        raise SlotTaken(other or "khác")
    if lesson is None:
        lesson = Lesson(
            class_id=class_id,
            subject_id=subject_id,
            date=day,
            lesson_no=number,
            recorded_by=user.id,
        )
        session.add(lesson)
        session.flush()
    else:
        lesson.recorded_by = user.id
        lesson.updated_at = func.now()
        session.execute(delete(LessonAbsence).where(LessonAbsence.lesson_id == lesson.id))
    for student, entry in targets:
        session.add(
            LessonAbsence(
                lesson_id=lesson.id,
                class_student_id=student.class_student_id,
                status=entry.status,
                reason=entry.reason,
                note=entry.note,
            )
        )
    record_access(
        session,
        user,
        AuditAction.EDIT_LESSON,
        class_id=class_id,
        details={
            "subject_id": subject_id,
            "date": str(day),
            "lesson_no": number,
            "marked": len(targets),
        },
        commit=False,
    )
    session.commit()
    return _lesson_out(session, user, class_id, subject_id, day, number)


def delete_lesson(
    session: Session, user: User, class_id: int, subject_id: int, day: date, number: int
) -> None:
    """Xoá một tiết đã điểm danh nhầm (chỉ GVBM của đúng môn đó)."""
    authorize_write(session, user, class_id=class_id, subject_id=subject_id)
    lesson = _find_lesson(session, class_id, day, number)
    if lesson is None or lesson.subject_id != subject_id:
        raise NotFound("Môn này chưa điểm danh tiết này.")
    session.delete(lesson)
    record_access(
        session,
        user,
        AuditAction.EDIT_LESSON,
        class_id=class_id,
        details={"subject_id": subject_id, "date": str(day), "lesson_no": number, "deleted": True},
        commit=False,
    )
    session.commit()
