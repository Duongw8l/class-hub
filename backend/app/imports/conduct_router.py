"""Rèn luyện của lớp chủ nhiệm: xem cả lớp, xem / sửa từng em, cả năm theo học kỳ II (D-119).

Xem qua authorize() + require_all_subjects() (GVCN của lớp và BGH); sửa qua authorize_write() (chỉ
GVCN của lớp), cả hai TRƯỚC khi đọc dữ liệu (nguyên tắc 4). Lỗi quyền → 403 do handler chung.
"""

from fastapi import APIRouter, HTTPException, status

from app.auth.deps import CurrentUser
from app.core.db import DbSession
from app.imports import conduct_manual as manual
from app.imports import hooks
from app.imports.conduct_schemas import (
    ClassConductOut,
    StudentConductIn,
    StudentConductOut,
    YearFillOut,
)

router = APIRouter(tags=["imports"])

STUDENT_PATH = "/classes/{class_id}/conduct/students/{student_id}"


def _not_found(error: manual.NotFound) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message)


@router.get(
    "/classes/{class_id}/conduct",
    response_model=ClassConductOut,
    summary="Rèn luyện cả lớp, ba kỳ (GVCN của lớp và BGH)",
)
def class_conduct(class_id: int, user: CurrentUser, session: DbSession) -> ClassConductOut:
    try:
        return manual.class_conduct(session, user, class_id)
    except manual.NotFound as error:
        raise _not_found(error) from None


@router.get(
    STUDENT_PATH,
    response_model=StudentConductOut,
    summary="Rèn luyện và lịch sử sửa của một học sinh (GVCN của lớp và BGH)",
)
def student_conduct(
    class_id: int, student_id: int, user: CurrentUser, session: DbSession
) -> StudentConductOut:
    try:
        return manual.student_conduct(session, user, class_id, student_id)
    except manual.NotFound as error:
        raise _not_found(error) from None


@router.put(
    STUDENT_PATH,
    response_model=StudentConductOut,
    summary="Sửa hoặc nhập tay rèn luyện của một học sinh (chỉ GVCN của lớp)",
)
def save_student_conduct(
    class_id: int,
    student_id: int,
    body: StudentConductIn,
    user: CurrentUser,
    session: DbSession,
) -> StudentConductOut:
    try:
        manual.save_student_conduct(session, user, class_id, student_id, body)
    except manual.NotFound as error:
        raise _not_found(error) from None
    except manual.NothingChanged:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Không có kỳ nào thay đổi."
        ) from None
    hooks.on_data_changed(class_id)  # cảnh báo sớm của lớp, sau khi đã commit
    return manual.conduct_after_save(session, user, class_id, student_id)


@router.post(
    "/classes/{class_id}/conduct/year-from-hk2",
    response_model=YearFillOut,
    summary="Ghi rèn luyện cả năm theo học kỳ II cho các em còn trống (chỉ GVCN của lớp)",
)
def year_from_hk2(class_id: int, user: CurrentUser, session: DbSession) -> YearFillOut:
    try:
        filled = manual.fill_year_from_hk2(session, user, class_id)
    except manual.NotFound as error:
        raise _not_found(error) from None
    if filled:
        hooks.on_data_changed(class_id)
    return YearFillOut(filled=filled)
