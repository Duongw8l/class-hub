"""Ba endpoint số liệu: dashboard lớp, bảng điểm môn, tổng quan khối.

Mọi endpoint gọi authorize() TRƯỚC khi đọc dữ liệu (nguyên tắc 4). Các con số do service.py và các
hàm thuần trong analytics/ tính; endpoint chỉ kiểm quyền, gọi, ghi nhật ký và trả kết quả.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.analytics import repository as repo
from app.analytics import service
from app.analytics.config import load_config
from app.analytics.schemas import (
    DashboardOut,
    GradeOverviewOut,
    MySupportOut,
    Period,
    StudentProfileFullOut,
    StudentProfileSubjectsOut,
    SubjectScoresOut,
    SubjectSupportOut,
)
from app.auth.audit import record_access
from app.auth.deps import CurrentUser
from app.classes.years import SchoolYearQuery, resolve_year, resolve_year_id
from app.core.authorize import authorize
from app.core.db import DbSession
from app.core.enums import AuditAction, UserRole
from app.warning import repository as warning_repo
from app.warning import service as warning_service

router = APIRouter(tags=["analytics"])

PeriodQuery = Annotated[
    Period, Query(description="Kỳ xem: 1 (học kỳ I), 2 (học kỳ II) hoặc year (cả năm).")
]


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


@router.get(
    "/classes/{class_id}/dashboard",
    response_model=DashboardOut,
    summary="Dashboard lớp (GVCN của lớp và BGH)",
)
def class_dashboard(
    class_id: int, user: CurrentUser, session: DbSession, semester: PeriodQuery = "1"
) -> DashboardOut:
    access = authorize(session, user, class_id=class_id)
    access.require_all_subjects()  # dashboard có mọi môn: GVBM không xem được
    class_info = repo.get_class(session, class_id)
    if class_info is None:
        raise _not_found("Không có lớp này.")

    dashboard = service.build_dashboard(
        session,
        class_info,
        semester,
        load_config(session),
        warning_service.counts_out(warning_repo.current_counts(session, class_id=class_id)),
    )
    record_access(
        session,
        user,
        AuditAction.VIEW_CLASS_DASHBOARD,
        class_id=class_id,
        details={"semester": semester, "student_count": dashboard.student_count},
    )
    return dashboard


@router.get(
    "/classes/{class_id}/subjects/{subject_id}/scores",
    response_model=SubjectScoresOut,
    summary="Bảng điểm một môn của lớp (GVBM đúng môn, GVCN, BGH)",
)
def subject_scores(
    class_id: int,
    subject_id: int,
    user: CurrentUser,
    session: DbSession,
    semester: Annotated[int, Query(ge=1, le=2, description="Học kỳ 1 hoặc 2.")] = 1,
) -> SubjectScoresOut:
    authorize(session, user, class_id=class_id, subject_id=subject_id)
    class_info = repo.get_class(session, class_id)
    if class_info is None:
        raise _not_found("Không có lớp này.")
    subject = next((s for s in repo.class_subjects(session, class_id) if s.id == subject_id), None)
    if subject is None:
        raise _not_found("Lớp này không học môn này.")

    scores = service.build_subject_scores(
        session, class_info, subject, semester, load_config(session)
    )
    record_access(
        session,
        user,
        AuditAction.VIEW_SUBJECT_SCORES,
        class_id=class_id,
        details={
            "subject_id": subject_id,
            "semester": semester,
            "student_count": scores.student_count,
        },
    )
    return scores


SemesterOrAuto = Annotated[
    int | None,
    Query(
        ge=1,
        le=2,
        description="Học kỳ 1 hoặc 2; bỏ trống: học kỳ II nếu môn đã có điểm, không thì học kỳ I.",
    ),
]


@router.get(
    "/classes/{class_id}/subjects/{subject_id}/support",
    response_model=SubjectSupportOut,
    summary="Học sinh cần hỗ trợ trong một môn và thống kê kế hoạch (GVBM đúng môn, GVCN, BGH)",
)
def subject_support(
    class_id: int,
    subject_id: int,
    user: CurrentUser,
    session: DbSession,
    semester: SemesterOrAuto = None,
) -> SubjectSupportOut:
    authorize(session, user, class_id=class_id, subject_id=subject_id)
    class_info = repo.get_class(session, class_id)
    if class_info is None:
        raise _not_found("Không có lớp này.")
    subject = next((s for s in repo.class_subjects(session, class_id) if s.id == subject_id), None)
    if subject is None:
        raise _not_found("Lớp này không học môn này.")

    result = service.build_subject_support(
        session, class_info, subject, semester, load_config(session)
    )
    record_access(
        session,
        user,
        AuditAction.VIEW_SUBJECT_SCORES,
        class_id=class_id,
        details={
            "view": "support",
            "subject_id": subject_id,
            "semester": result.semester,
            "student_count": len(result.students),
        },
    )
    return result


@router.get(
    "/me/support",
    response_model=MySupportOut,
    summary="Học sinh cần hỗ trợ ở mọi lớp–môn tôi đang dạy (giáo viên)",
)
def my_support(
    user: CurrentUser,
    session: DbSession,
    semester: SemesterOrAuto = None,
    school_year_id: SchoolYearQuery = None,
) -> MySupportOut:
    """Phạm vi lấy từ bảng phân công của chính người gọi; mỗi lớp–môn vẫn qua authorize()."""
    year_id = resolve_year_id(session, school_year_id)
    if user.role is not UserRole.TEACHER or year_id is None:
        return MySupportOut(school_year_id=year_id, items=[])
    config = load_config(session)
    items = []
    for class_info, subject in repo.teaching_of(session, user.id, school_year_id=year_id):
        authorize(session, user, class_id=class_info.id, subject_id=subject.id)
        item = service.build_subject_support(session, class_info, subject, semester, config)
        items.append(item)
        record_access(
            session,
            user,
            AuditAction.VIEW_SUBJECT_SCORES,
            class_id=class_info.id,
            details={
                "view": "support",
                "subject_id": subject.id,
                "semester": item.semester,
                "student_count": len(item.students),
            },
            commit=False,
        )
    session.commit()  # nhật ký của mọi lớp–môn ghi cùng lúc, trước khi trả dữ liệu
    return MySupportOut(school_year_id=year_id, items=items)


@router.get(
    "/classes/{class_id}/students/{student_id}/profile",
    response_model=StudentProfileFullOut | StudentProfileSubjectsOut,
    summary="Hồ sơ học sinh (GVCN và BGH đầy đủ; GVBM chỉ các môn mình dạy)",
)
def student_profile(
    class_id: int,
    student_id: int,
    user: CurrentUser,
    session: DbSession,
    semester: PeriodQuery = "1",
) -> StudentProfileFullOut | StudentProfileSubjectsOut:
    access = authorize(session, user, class_id=class_id)
    class_info = repo.get_class(session, class_id)
    if class_info is None:
        raise _not_found("Không có lớp này.")

    profile = service.build_student_profile(
        session,
        class_info,
        student_id,
        semester,
        load_config(session),
        subject_ids=access.subject_ids,
        alert_lookup=lambda class_student_id: warning_service.profile_alert(
            session, class_student_id
        ),
    )
    if profile is None:
        raise _not_found("Không có học sinh này trong lớp.")
    record_access(
        session,
        user,
        AuditAction.VIEW_STUDENT_PROFILE,
        class_id=class_id,
        details={"student_id": student_id, "semester": semester, "scope": profile.scope},
    )
    return profile


@router.get(
    "/grades/{level}/overview",
    response_model=GradeOverviewOut,
    summary="So sánh các lớp trong một khối (chỉ BGH)",
)
def grade_overview(
    level: int,
    user: CurrentUser,
    session: DbSession,
    semester: PeriodQuery = "1",
    school_year_id: SchoolYearQuery = None,
) -> GradeOverviewOut:
    authorize(session, user, grade_level=level)
    year = resolve_year(session, school_year_id)
    classes = repo.classes_in_grade(session, level, school_year_id=year.id)
    if not classes:
        raise _not_found("Không có khối này.")
    # Chỉ số liệu gộp theo lớp, không có tên học sinh nên không ghi nhật ký truy cập hồ sơ.
    return service.build_grade_overview(session, level, classes, semester, load_config(session))
