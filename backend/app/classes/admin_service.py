"""Quản trị năm học, lớp, GVCN, phân công giảng dạy, gỡ học sinh khỏi lớp (Admin, D-098, D-099).

Nhiều năm học, một năm hiện hành (D-113, thay cho "một năm học" của D-098); lớp, GVCN, phân công
tính theo năm. Mọi hàm ném `AdminNotFound` (404), `AdminConflict` (409) hoặc
`AdminInvalid` (422) kèm thông điệp tiếng Việt để router đổi thẳng thành HTTP. Không hàm nào trả
tên hay mã học sinh.
"""

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.auth.audit import record_access
from app.auth.models import User
from app.classes.academic import Assessment, Attendance, ConductResult, ExamRegistration
from app.classes.admin_schemas import (
    AdminClassOut,
    AssignmentRow,
    ClassAssignmentsOut,
    ClassCreateIn,
    ClassUpdateIn,
    SchoolOut,
    SchoolYearCreatedOut,
    SchoolYearCreateIn,
    SchoolYearIn,
    SchoolYearOut,
    SubjectOut,
    TeacherOut,
    TeacherRef,
)
from app.classes.models import (
    ClassStudent,
    SchoolClass,
    SchoolYear,
    Student,
    Subject,
    TeachingAssignment,
)
from app.classes.years import current_year, list_years, resolve_year_id
from app.core.enums import AuditAction, UserRole
from app.imports.models import ImportJob
from app.warning.models import RiskAlert


class AdminError(Exception):
    """Lỗi nghiệp vụ có sẵn thông điệp tiếng Việt cho người dùng."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AdminNotFound(AdminError):
    """404."""


class AdminConflict(AdminError):
    """409: trạng thái hiện tại không cho phép."""


class AdminInvalid(AdminError):
    """422: giá trị gửi lên không hợp lệ."""


# --- Năm học và danh sách lớp --------------------------------------------------


def _year_out(year: SchoolYear) -> SchoolYearOut:
    return SchoolYearOut(
        id=year.id,
        name=year.name,
        start_date=year.start_date,
        end_date=year.end_date,
        is_current=year.is_current,
    )


def _get_year(session: Session, year_id: int) -> SchoolYear:
    year = session.get(SchoolYear, year_id)
    if year is None:
        raise AdminNotFound("Không có năm học này.")
    return year


def _class_rows(
    session: Session, class_id: int | None = None, *, school_year_id: int | None = None
) -> list[AdminClassOut]:
    students = (
        select(func.count())
        .select_from(ClassStudent)
        .where(ClassStudent.class_id == SchoolClass.id)
        .scalar_subquery()
    )
    subjects = (
        select(func.count())
        .select_from(TeachingAssignment)
        .where(TeachingAssignment.class_id == SchoolClass.id)
        .scalar_subquery()
    )
    statement = (
        select(SchoolClass, User.full_name, students, subjects)
        .outerjoin(User, User.id == SchoolClass.homeroom_teacher_id)
        .order_by(SchoolClass.grade_level, SchoolClass.name)
    )
    if class_id is not None:
        statement = statement.where(SchoolClass.id == class_id)
    if school_year_id is not None:
        statement = statement.where(SchoolClass.school_year_id == school_year_id)
    return [
        AdminClassOut(
            id=row[0].id,
            name=row[0].name,
            grade_level=row[0].grade_level,
            homeroom_teacher=(
                None
                if row[0].homeroom_teacher_id is None
                else TeacherRef(id=row[0].homeroom_teacher_id, full_name=row[1])
            ),
            student_count=row[2],
            assigned_subject_count=row[3],
        )
        for row in session.execute(statement)
    ]


def get_school(session: Session, school_year_id: int | None = None) -> SchoolOut:
    """Năm học đang xem (mặc định năm hiện hành) và các lớp của năm đó, kèm danh sách mọi năm."""
    year_id = resolve_year_id(session, school_year_id)
    year = None if year_id is None else session.get(SchoolYear, year_id)
    return SchoolOut(
        school_year=None if year is None else _year_out(year),
        years=[_year_out(y) for y in list_years(session)],
        classes=[] if year is None else _class_rows(session, school_year_id=year.id),
        subject_count=session.scalar(select(func.count()).select_from(Subject)) or 0,
    )


def list_subjects(session: Session) -> list[SubjectOut]:
    """17 môn GDPT 2018 có sẵn (D-112), cho ô "Vai trò: Giáo viên <môn>". Sắp theo id."""
    rows = session.execute(
        select(Subject.id, Subject.name, Subject.is_elective).order_by(Subject.id)
    )
    return [SubjectOut(id=r[0], name=r[1], is_elective=r[2]) for r in rows]


def list_teachers(session: Session, school_year_id: int | None = None) -> list[TeacherOut]:
    """Giáo viên đang hoạt động (cho ô chọn GVCN và người dạy). Tài khoản bị khoá không có mặt.

    `homeroom_class` là lớp chủ nhiệm trong năm học được chọn (mặc định năm hiện hành): mỗi năm một
    giáo viên chủ nhiệm một lớp (D-113). Trả kèm môn của giáo viên ("Giáo viên Toán") để ô chọn hiện
    cạnh tên và đưa GV đúng môn lên đầu khi phân công (D-112); chỉ là nhãn.
    """
    year_id = resolve_year_id(session, school_year_id)
    homeroom = (
        select(SchoolClass.name)
        .where(SchoolClass.homeroom_teacher_id == User.id, SchoolClass.school_year_id == year_id)
        .order_by(SchoolClass.name)
        .limit(1)
        .scalar_subquery()
    )
    specialty = (
        select(Subject.name).where(Subject.id == User.specialty_subject_id).scalar_subquery()
    )
    rows = session.execute(
        select(User.id, User.full_name, User.email, homeroom, User.specialty_subject_id, specialty)
        .where(User.role == UserRole.TEACHER, User.is_active.is_(True))
        .order_by(User.full_name, User.id)
    )
    return [
        TeacherOut(
            id=r[0],
            full_name=r[1],
            email=r[2],
            homeroom_class=r[3],
            specialty_subject_id=r[4],
            specialty=r[5],
        )
        for r in rows
    ]


def _check_year_name(session: Session, name: str, *, except_id: int | None) -> None:
    statement = select(SchoolYear.id).where(func.lower(SchoolYear.name) == name.lower())
    if except_id is not None:
        statement = statement.where(SchoolYear.id != except_id)
    if session.scalar(statement.limit(1)) is not None:
        raise AdminConflict(f"Đã có năm học tên {name}.")


def _check_overlap(session: Session, data: SchoolYearIn, *, except_id: int | None) -> None:
    """Hai năm học không được chồng ngày: điểm danh một ngày phải thuộc đúng một năm."""
    statement = select(SchoolYear.name).where(
        SchoolYear.start_date <= data.end_date, SchoolYear.end_date >= data.start_date
    )
    if except_id is not None:
        statement = statement.where(SchoolYear.id != except_id)
    other = session.scalar(statement.limit(1))
    if other is not None:
        raise AdminConflict(f"Khoảng ngày bị chồng lên năm học {other}.")


def _check_attendance_inside(session: Session, year: SchoolYear, data: SchoolYearIn) -> None:
    """Đổi ngày của một năm không được bỏ ra ngoài các ngày đã điểm danh của CHÍNH năm đó."""
    earliest, latest = session.execute(
        select(func.min(Attendance.date), func.max(Attendance.date))
        .join(ClassStudent, ClassStudent.id == Attendance.class_student_id)
        .join(SchoolClass, SchoolClass.id == ClassStudent.class_id)
        .where(SchoolClass.school_year_id == year.id)
    ).one()
    if earliest is not None and (earliest < data.start_date or latest > data.end_date):
        raise AdminConflict(
            "Đã có dữ liệu điểm danh nằm ngoài khoảng ngày mới. "
            "Hãy chọn khoảng ngày bao trùm các ngày đã điểm danh."
        )


def _make_current(session: Session, year: SchoolYear) -> None:
    # Bỏ cờ ở năm cũ trước (chỉ mục duy nhất một phần chỉ cho một dòng is_current), rồi mới đặt.
    session.execute(
        update(SchoolYear)
        .where(SchoolYear.is_current.is_(True), SchoolYear.id != year.id)
        .values(is_current=False)
    )
    session.flush()
    year.is_current = True
    session.flush()


def _edit_year(session: Session, admin: User, year: SchoolYear, data: SchoolYearIn) -> None:
    _check_year_name(session, data.name, except_id=year.id)
    _check_overlap(session, data, except_id=year.id)
    _check_attendance_inside(session, year, data)
    year.name = data.name
    year.start_date = data.start_date
    year.end_date = data.end_date
    session.flush()
    record_access(
        session,
        admin,
        AuditAction.UPDATE_SCHOOL_YEAR,
        class_id=None,
        details={"school_year_id": year.id, "created": False},
        commit=False,
    )
    session.commit()


def save_school_year(session: Session, admin: User, data: SchoolYearIn) -> SchoolYearOut:
    """Tạo năm học đầu tiên (thành năm hiện hành), hoặc sửa năm hiện hành.

    Giữ cho tương thích; tạo thêm năm thứ hai trở đi dùng `create_school_year` (D-113).
    """
    year = current_year(session)
    if year is None:
        return create_school_year(
            session, admin, SchoolYearCreateIn(**data.model_dump(), make_current=True)
        ).school_year
    _edit_year(session, admin, year, data)
    return _year_out(year)


def update_school_year(
    session: Session, admin: User, year_id: int, data: SchoolYearIn
) -> SchoolYearOut:
    """Sửa tên, ngày của một năm học bất kỳ (năm cũ vẫn sửa được, D-113)."""
    year = _get_year(session, year_id)
    _edit_year(session, admin, year, data)
    return _year_out(year)


def set_current_year(session: Session, admin: User, year_id: int) -> SchoolYearOut:
    """Đặt năm hiện hành: năm mọi người thấy mặc định khi mở hệ thống."""
    year = _get_year(session, year_id)
    _make_current(session, year)
    record_access(
        session,
        admin,
        AuditAction.UPDATE_SCHOOL_YEAR,
        class_id=None,
        details={"school_year_id": year.id, "made_current": True},
        commit=False,
    )
    session.commit()
    return _year_out(year)


def _promoted_name(name: str, grade_level: int) -> str:
    """Tên lớp năm sau của lớp này: 10A1 → 11A1, 11A3 → 12A3 (tên lớp luôn bắt đầu bằng số khối)."""
    prefix = str(grade_level)
    rest = name[len(prefix) :] if name.startswith(prefix) else name
    return f"{grade_level + 1}{rest}"


def _rollover(session: Session, source: SchoolYear, target: SchoolYear) -> tuple[int, int]:
    """Chép lớp từ `source` sang `target` và cho học sinh lên lớp. Trả (số lớp tạo, số HS lên lớp).

    - Mọi tên lớp của năm trước được tạo lại (lớp trống), cộng các lớp đích của học sinh lên lớp.
    - Học sinh lớp 10Ax → 11Ax, 11Ax → 12Ax. Khối 12 ra trường (không chép học sinh).
    - Không chép GVCN, phân công; điểm, điểm danh, rèn luyện vẫn nằm ở năm cũ.
    Học sinh lưu ban hay chuyển lớp: Admin gỡ khỏi lớp mới (chưa có dữ liệu nên gỡ được) rồi nhập
    vào đúng lớp.
    """
    classes = session.scalars(
        select(SchoolClass)
        .where(SchoolClass.school_year_id == source.id)
        .order_by(SchoolClass.grade_level, SchoolClass.name)
    ).all()
    wanted: dict[str, int] = {c.name: c.grade_level for c in classes}
    promotions: list[tuple[int, str]] = []
    for school_class in classes:
        if school_class.grade_level < 12:
            new_name = _promoted_name(school_class.name, school_class.grade_level)
            wanted.setdefault(new_name, school_class.grade_level + 1)
            promotions.append((school_class.id, new_name))

    created: dict[str, int] = {}
    for name, grade in sorted(wanted.items(), key=lambda item: (item[1], item[0])):
        new_class = SchoolClass(school_year_id=target.id, grade_level=grade, name=name)
        session.add(new_class)
        session.flush()
        created[name] = new_class.id

    rows: list[dict[str, int]] = []
    for source_id, new_name in promotions:
        for student_id in session.scalars(
            select(ClassStudent.student_id).where(ClassStudent.class_id == source_id)
        ):
            rows.append({"class_id": created[new_name], "student_id": student_id})
    if rows:
        session.execute(insert(ClassStudent), rows)
    return len(created), len(rows)


def create_school_year(
    session: Session, admin: User, data: SchoolYearCreateIn
) -> SchoolYearCreatedOut:
    """Tạo một năm học mới; có thể chép lớp và cho học sinh lên lớp từ năm liền trước (D-113).

    Năm đầu tiên của trường luôn thành năm hiện hành.
    """
    _check_year_name(session, data.name, except_id=None)
    _check_overlap(session, data, except_id=None)
    first = current_year(session) is None
    source = None
    if data.rollover:
        source = session.scalars(
            select(SchoolYear)
            .where(SchoolYear.end_date < data.start_date)
            .order_by(SchoolYear.start_date.desc())
            .limit(1)
        ).first()
        if source is None:
            raise AdminInvalid("Chưa có năm học nào trước năm này để chép lớp.")

    year = SchoolYear(name=data.name, start_date=data.start_date, end_date=data.end_date)
    session.add(year)
    session.flush()
    classes_created, promoted = (0, 0) if source is None else _rollover(session, source, year)
    if data.make_current or first:
        _make_current(session, year)
    record_access(
        session,
        admin,
        AuditAction.UPDATE_SCHOOL_YEAR,
        class_id=None,
        details={
            "school_year_id": year.id,
            "created": True,
            "rollover_from": None if source is None else source.id,
            "classes_created": classes_created,
            "students_promoted": promoted,
            "made_current": year.is_current,
        },
        commit=False,
    )
    session.commit()
    return SchoolYearCreatedOut(
        school_year=_year_out(year), classes_created=classes_created, students_promoted=promoted
    )


# --- Lớp và giáo viên chủ nhiệm --------------------------------------------------


def _active_teacher(session: Session, teacher_id: int) -> User:
    teacher = session.get(User, teacher_id)
    if teacher is None or teacher.role is not UserRole.TEACHER or not teacher.is_active:
        raise AdminInvalid("Chỉ chọn được giáo viên đang hoạt động.")
    return teacher


def _check_homeroom(
    session: Session, teacher_id: int, *, for_class: int | None, school_year_id: int
) -> None:
    """Mỗi giáo viên chủ nhiệm nhiều nhất một lớp trong MỘT năm học (năm khác không tính, D-113)."""
    _active_teacher(session, teacher_id)
    statement = select(SchoolClass.name).where(
        SchoolClass.homeroom_teacher_id == teacher_id,
        SchoolClass.school_year_id == school_year_id,
    )
    if for_class is not None:
        statement = statement.where(SchoolClass.id != for_class)
    other = session.scalar(statement.limit(1))
    if other is not None:
        raise AdminConflict(
            f"Giáo viên này đang chủ nhiệm lớp {other}. Mỗi giáo viên chỉ chủ nhiệm một lớp "
            "trong một năm học."
        )


def _check_class_name(
    session: Session, name: str, grade_level: int, *, except_id: int | None, school_year_id: int
) -> None:
    """Tên lớp không trùng trong cùng năm học (năm nào cũng có 10A1, D-113)."""
    if not name.startswith(str(grade_level)):
        raise AdminInvalid(
            f"Tên lớp khối {grade_level} phải bắt đầu bằng {grade_level} (ví dụ {grade_level}A1)."
        )
    statement = select(SchoolClass.id).where(
        func.lower(SchoolClass.name) == name.lower(),
        SchoolClass.school_year_id == school_year_id,
    )
    if except_id is not None:
        statement = statement.where(SchoolClass.id != except_id)
    if session.scalar(statement.limit(1)) is not None:
        raise AdminConflict(f"Đã có lớp tên {name}.")


def _get_class(session: Session, class_id: int) -> SchoolClass:
    school_class = session.get(SchoolClass, class_id)
    if school_class is None:
        raise AdminNotFound("Không có lớp này.")
    return school_class


def create_class(session: Session, admin: User, data: ClassCreateIn) -> AdminClassOut:
    """Tạo lớp trong năm học được chọn (mặc định năm hiện hành, D-113)."""
    if data.school_year_id is None:
        year = current_year(session)
        if year is None:
            raise AdminConflict("Hãy tạo năm học trước khi tạo lớp.")
    else:
        year = _get_year(session, data.school_year_id)
    _check_class_name(session, data.name, data.grade_level, except_id=None, school_year_id=year.id)
    if data.homeroom_teacher_id is not None:
        _check_homeroom(session, data.homeroom_teacher_id, for_class=None, school_year_id=year.id)
    school_class = SchoolClass(
        school_year_id=year.id,
        grade_level=data.grade_level,
        name=data.name,
        homeroom_teacher_id=data.homeroom_teacher_id,
    )
    session.add(school_class)
    session.flush()
    record_access(
        session,
        admin,
        AuditAction.CREATE_CLASS,
        class_id=school_class.id,
        details={"grade_level": data.grade_level, "homeroom_teacher_id": data.homeroom_teacher_id},
        commit=False,
    )
    session.commit()
    return _class_rows(session, school_class.id)[0]


def update_class(
    session: Session, admin: User, class_id: int, data: ClassUpdateIn
) -> AdminClassOut:
    school_class = _get_class(session, class_id)
    fields = data.model_fields_set
    details: dict[str, object] = {"fields": sorted(fields)}
    year_id = school_class.school_year_id
    if "name" in fields and data.name is not None:
        _check_class_name(
            session,
            data.name,
            school_class.grade_level,
            except_id=class_id,
            school_year_id=year_id,
        )
        school_class.name = data.name
    if "homeroom_teacher_id" in fields:
        if data.homeroom_teacher_id is not None:
            _check_homeroom(
                session, data.homeroom_teacher_id, for_class=class_id, school_year_id=year_id
            )
        details["homeroom_teacher_id"] = [
            school_class.homeroom_teacher_id,
            data.homeroom_teacher_id,
        ]
        school_class.homeroom_teacher_id = data.homeroom_teacher_id
    session.flush()
    record_access(
        session, admin, AuditAction.UPDATE_CLASS, class_id=class_id, details=details, commit=False
    )
    session.commit()
    return _class_rows(session, class_id)[0]


def delete_class(session: Session, admin: User, class_id: int) -> None:
    """Chỉ xoá lớp đã trống: không còn học sinh và không còn phân công."""
    school_class = _get_class(session, class_id)
    has_students = session.scalar(
        select(ClassStudent.id).where(ClassStudent.class_id == class_id).limit(1)
    )
    has_assignments = session.scalar(
        select(TeachingAssignment.id).where(TeachingAssignment.class_id == class_id).limit(1)
    )
    if has_students is not None or has_assignments is not None:
        raise AdminConflict(
            "Lớp còn học sinh hoặc còn phân công giảng dạy. Hãy gỡ hết trước khi xoá lớp."
        )
    # Bản xem trước nhập tệp chưa xác nhận của lớp này (nếu có) cũng bỏ đi.
    session.execute(delete(ImportJob).where(ImportJob.class_id == class_id))
    details = {"grade_level": school_class.grade_level}
    session.delete(school_class)
    session.flush()
    record_access(
        session, admin, AuditAction.DELETE_CLASS, class_id=class_id, details=details, commit=False
    )
    session.commit()


# --- Phân công giảng dạy --------------------------------------------------


def get_class_assignments(session: Session, class_id: int) -> ClassAssignmentsOut:
    school_class = _get_class(session, class_id)
    rows = session.execute(
        select(Subject, User.id, User.full_name)
        .outerjoin(
            TeachingAssignment,
            (TeachingAssignment.subject_id == Subject.id)
            & (TeachingAssignment.class_id == class_id),
        )
        .outerjoin(User, User.id == TeachingAssignment.teacher_id)
        .order_by(Subject.id)
    )
    return ClassAssignmentsOut(
        class_id=school_class.id,
        class_name=school_class.name,
        grade_level=school_class.grade_level,
        subjects=[
            AssignmentRow(
                subject_id=r[0].id,
                subject_name=r[0].name,
                is_elective=r[0].is_elective,
                assessment_type=r[0].assessment_type,
                teacher=None if r[1] is None else TeacherRef(id=r[1], full_name=r[2]),
            )
            for r in rows
        ],
    )


def set_assignment(
    session: Session, admin: User, class_id: int, subject_id: int, teacher_id: int
) -> ClassAssignmentsOut:
    """Gán giáo viên cho cặp lớp-môn, hoặc đổi giáo viên nếu đã có."""
    _get_class(session, class_id)
    if session.get(Subject, subject_id) is None:
        raise AdminNotFound("Không có môn này.")
    _active_teacher(session, teacher_id)
    existing = session.scalar(
        select(TeachingAssignment).where(
            TeachingAssignment.class_id == class_id, TeachingAssignment.subject_id == subject_id
        )
    )
    previous = None if existing is None else existing.teacher_id
    if existing is None:
        session.add(
            TeachingAssignment(class_id=class_id, subject_id=subject_id, teacher_id=teacher_id)
        )
    else:
        existing.teacher_id = teacher_id
    session.flush()
    record_access(
        session,
        admin,
        AuditAction.SET_ASSIGNMENT,
        class_id=class_id,
        details={"subject_id": subject_id, "teacher_id": [previous, teacher_id]},
        commit=False,
    )
    session.commit()
    return get_class_assignments(session, class_id)


def remove_assignment(
    session: Session, admin: User, class_id: int, subject_id: int
) -> ClassAssignmentsOut:
    """Gỡ phân công; từ chối nếu lớp đã có điểm môn đó (điểm sẽ mồ côi, không ai nhập tiếp được)."""
    _get_class(session, class_id)
    existing = session.scalar(
        select(TeachingAssignment).where(
            TeachingAssignment.class_id == class_id, TeachingAssignment.subject_id == subject_id
        )
    )
    if existing is None:
        raise AdminNotFound("Môn này chưa được phân công cho lớp.")
    has_scores = session.scalar(
        select(Assessment.id)
        .join(ClassStudent, ClassStudent.id == Assessment.class_student_id)
        .where(ClassStudent.class_id == class_id, Assessment.subject_id == subject_id)
        .limit(1)
    )
    if has_scores is not None:
        raise AdminConflict(
            "Lớp đã có điểm của môn này nên không gỡ phân công được. Hãy đổi sang giáo viên khác."
        )
    session.delete(existing)
    session.flush()
    record_access(
        session,
        admin,
        AuditAction.REMOVE_ASSIGNMENT,
        class_id=class_id,
        details={"subject_id": subject_id, "teacher_id": existing.teacher_id},
        commit=False,
    )
    session.commit()
    return get_class_assignments(session, class_id)


def copy_assignments(
    session: Session, admin: User, class_id: int, from_class_id: int
) -> tuple[int, ClassAssignmentsOut]:
    """Sao chép giáo viên cho các môn còn trống từ một lớp cùng khối. Không đè phân công có sẵn."""
    target = _get_class(session, class_id)
    if from_class_id == class_id:
        raise AdminInvalid("Hãy chọn lớp khác để sao chép.")
    source = session.get(SchoolClass, from_class_id)
    if source is None:
        raise AdminNotFound("Không có lớp nguồn này.")
    if source.grade_level != target.grade_level:
        raise AdminInvalid("Chỉ sao chép được từ lớp cùng khối.")
    if source.school_year_id != target.school_year_id:
        raise AdminInvalid("Chỉ sao chép được từ lớp cùng khối trong cùng năm học.")
    assigned = set(
        session.scalars(
            select(TeachingAssignment.subject_id).where(TeachingAssignment.class_id == class_id)
        )
    )
    copied = 0
    for source_row in session.scalars(
        select(TeachingAssignment)
        .where(TeachingAssignment.class_id == from_class_id)
        .order_by(TeachingAssignment.subject_id)
    ):
        if source_row.subject_id in assigned:
            continue
        # Giáo viên đã bị khoá hoặc đổi vai trò thì bỏ qua, không mang sang lớp mới.
        teacher = session.get(User, source_row.teacher_id)
        if teacher is None or teacher.role is not UserRole.TEACHER or not teacher.is_active:
            continue
        session.add(
            TeachingAssignment(
                class_id=class_id, subject_id=source_row.subject_id, teacher_id=teacher.id
            )
        )
        copied += 1
    session.flush()
    record_access(
        session,
        admin,
        AuditAction.SET_ASSIGNMENT,
        class_id=class_id,
        details={"copied": copied, "from_class_id": from_class_id},
        commit=False,
    )
    session.commit()
    return copied, get_class_assignments(session, class_id)


# --- Gỡ học sinh khỏi lớp --------------------------------------------------


def remove_student(session: Session, admin: User, class_id: int, student_code: str) -> None:
    """Gỡ một học sinh (theo mã Admin gõ vào) khỏi lớp, chỉ khi em chưa có dữ liệu nào.

    Không trả tên hay thông tin học sinh. Em không còn ở lớp nào thì xoá luôn hồ sơ học sinh.
    """
    _get_class(session, class_id)
    code = student_code.strip().upper()
    row = session.execute(
        select(ClassStudent.id, Student.id)
        .join(Student, Student.id == ClassStudent.student_id)
        .where(ClassStudent.class_id == class_id, func.upper(Student.student_code) == code)
    ).first()
    if row is None:
        raise AdminNotFound("Lớp này không có học sinh mã đó.")
    class_student_id, student_id = row
    for model in (Assessment, Attendance, ConductResult, ExamRegistration, RiskAlert):
        found = session.scalar(
            select(model.id).where(model.class_student_id == class_student_id).limit(1)
        )
        if found is not None:
            raise AdminConflict(
                "Em này đã có dữ liệu (điểm, điểm danh, rèn luyện hoặc cảnh báo) "
                "nên không gỡ khỏi lớp được."
            )
    session.execute(delete(ClassStudent).where(ClassStudent.id == class_student_id))
    still_enrolled = session.scalar(
        select(ClassStudent.id).where(ClassStudent.student_id == student_id).limit(1)
    )
    if still_enrolled is None:
        session.execute(delete(Student).where(Student.id == student_id))
    record_access(
        session,
        admin,
        AuditAction.REMOVE_CLASS_STUDENT,
        class_id=class_id,
        details={"student_id": student_id, "student_deleted": still_enrolled is None},
        commit=False,
    )
    session.commit()
