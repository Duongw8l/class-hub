"""API điểm danh ngày (GVCN), điểm danh theo tiết (GVBM) và đối chiếu (D-120).

Mọi hàm của service gọi authorize() / authorize_write() TRƯỚC khi đọc dữ liệu (nguyên tắc 4); lỗi
quyền → 403 do handler chung.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.attendance import service
from app.attendance.schemas import (
    ClassAttendanceOut,
    DayAttendanceIn,
    DayAttendanceOut,
    DeletedOut,
    LessonDetailOut,
    LessonIn,
    SubjectLessonsOut,
)
from app.auth.deps import CurrentUser
from app.core.db import DbSession
from app.imports import hooks

router = APIRouter(tags=["attendance"])

MonthQuery = Annotated[
    str | None,
    Query(pattern=r"^\d{4}-\d{2}$", description="Tháng YYYY-MM; bỏ trống: tháng hiện tại"),
]
LessonNo = Annotated[int, Path(ge=1, le=10, description="Tiết thứ mấy trong ngày (1 đến 10)")]
LESSON_PATH = "/classes/{class_id}/subjects/{subject_id}/lessons/{day}/{lesson_no}"


def _today() -> date:
    return date.today()


def _http(error: Exception) -> HTTPException:
    if isinstance(error, service.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message)
    if isinstance(error, service.SlotTaken):
        return HTTPException(status.HTTP_409_CONFLICT, detail=error.message)
    if isinstance(error, service.Invalid):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message)
    raise error


# --- Điểm danh ngày ------------------------------------------------------------------------------


@router.get(
    "/classes/{class_id}/attendance",
    response_model=ClassAttendanceOut,
    summary="Điểm danh ngày của lớp theo tháng, tổng cả năm và đối chiếu với tiết (GVCN, BGH)",
)
def class_attendance(
    class_id: int, user: CurrentUser, session: DbSession, month: MonthQuery = None
) -> ClassAttendanceOut:
    try:
        return service.class_attendance(session, user, class_id, month, _today())
    except (service.NotFound, service.Invalid) as error:
        raise _http(error) from None


@router.get(
    "/classes/{class_id}/attendance/days/{day}",
    response_model=DayAttendanceOut,
    summary="Điểm danh một ngày của cả lớp, kèm các tiết GVBM đã đánh dấu (GVCN, BGH)",
)
def day_attendance(
    class_id: int, day: date, user: CurrentUser, session: DbSession
) -> DayAttendanceOut:
    try:
        return service.day_attendance(session, user, class_id, day)
    except service.NotFound as error:
        raise _http(error) from None


@router.put(
    "/classes/{class_id}/attendance/days/{day}",
    response_model=DayAttendanceOut,
    summary="Điểm danh hoặc sửa điểm danh một ngày (chỉ GVCN của lớp)",
)
def save_day(
    class_id: int, day: date, body: DayAttendanceIn, user: CurrentUser, session: DbSession
) -> DayAttendanceOut:
    try:
        service.save_day(session, user, class_id, day, body, _today())
    except (service.NotFound, service.Invalid) as error:
        raise _http(error) from None
    except service.NothingChanged:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Không có học sinh nào thay đổi."
        ) from None
    hooks.on_data_changed(class_id)  # cảnh báo sớm (số buổi nghỉ) của lớp, sau khi đã commit
    return service.day_after_save(session, user, class_id, day)


# --- Điểm danh theo tiết -------------------------------------------------------------------------


@router.get(
    "/classes/{class_id}/subjects/{subject_id}/lessons",
    response_model=SubjectLessonsOut,
    summary="Các tiết đã điểm danh của một lớp–môn và số tiết vắng từng em (GVBM, GVCN, BGH)",
)
def subject_lessons(
    class_id: int,
    subject_id: int,
    user: CurrentUser,
    session: DbSession,
    month: MonthQuery = None,
) -> SubjectLessonsOut:
    try:
        return service.subject_lessons(session, user, class_id, subject_id, month, _today())
    except (service.NotFound, service.Invalid) as error:
        raise _http(error) from None


@router.get(
    LESSON_PATH,
    response_model=LessonDetailOut,
    summary="Điểm danh một tiết (mặc định cả lớp có mặt nếu chưa điểm danh)",
)
def lesson_detail(
    class_id: int,
    subject_id: int,
    day: date,
    lesson_no: LessonNo,
    user: CurrentUser,
    session: DbSession,
) -> LessonDetailOut:
    try:
        return service.lesson_detail(session, user, class_id, subject_id, day, lesson_no)
    except service.NotFound as error:
        raise _http(error) from None


@router.put(
    LESSON_PATH,
    response_model=LessonDetailOut,
    summary="Điểm danh một tiết: danh sách em vắng / muộn (chỉ GVBM được phân công)",
)
def save_lesson(
    class_id: int,
    subject_id: int,
    day: date,
    lesson_no: LessonNo,
    body: LessonIn,
    user: CurrentUser,
    session: DbSession,
) -> LessonDetailOut:
    try:
        return service.save_lesson(
            session, user, class_id, subject_id, day, lesson_no, body, _today()
        )
    except (service.NotFound, service.Invalid, service.SlotTaken) as error:
        raise _http(error) from None


@router.delete(
    LESSON_PATH,
    response_model=DeletedOut,
    summary="Xoá một tiết điểm danh nhầm (chỉ GVBM được phân công)",
)
def delete_lesson(
    class_id: int,
    subject_id: int,
    day: date,
    lesson_no: LessonNo,
    user: CurrentUser,
    session: DbSession,
) -> DeletedOut:
    try:
        service.delete_lesson(session, user, class_id, subject_id, day, lesson_no)
    except service.NotFound as error:
        raise _http(error) from None
    return DeletedOut(deleted=True)
