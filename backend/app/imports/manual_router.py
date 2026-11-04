"""GET / PUT điểm của một học sinh trong một môn (sửa hoặc nhập tay, D-115).

GET qua authorize() (GVBM đúng môn, GVCN, BGH); PUT qua authorize_write() (chỉ GVBM được phân công
lớp–môn), cả hai TRƯỚC khi đọc dữ liệu (nguyên tắc 4). Lỗi quyền → 403 do handler chung.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.auth.deps import CurrentUser
from app.core.db import DbSession
from app.imports import hooks, manual
from app.imports.manual_schemas import StudentScoresIn, StudentScoresOut

router = APIRouter(tags=["imports"])

PATH = "/classes/{class_id}/subjects/{subject_id}/students/{student_id}/scores"


@router.get(
    PATH,
    response_model=StudentScoresOut,
    summary="Điểm một học kỳ và lịch sử sửa điểm của một học sinh (GVBM đúng môn, GVCN, BGH)",
)
def student_scores(
    class_id: int,
    subject_id: int,
    student_id: int,
    user: CurrentUser,
    session: DbSession,
    semester: Annotated[int, Query(ge=1, le=2, description="Học kỳ 1 hoặc 2.")] = 1,
) -> StudentScoresOut:
    try:
        return manual.get_student_scores(session, user, class_id, subject_id, student_id, semester)
    except manual.NotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message) from None


@router.put(
    PATH,
    response_model=StudentScoresOut,
    summary="Sửa hoặc nhập tay điểm của một học sinh (chỉ GVBM được phân công lớp–môn)",
)
def save_student_scores(
    class_id: int,
    subject_id: int,
    student_id: int,
    body: StudentScoresIn,
    user: CurrentUser,
    session: DbSession,
) -> StudentScoresOut:
    try:
        manual.save_student_scores(session, user, class_id, subject_id, student_id, body)
    except manual.NotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message) from None
    except manual.InvalidEntries as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from None
    except manual.NothingChanged:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Không có điểm nào thay đổi."
        ) from None
    hooks.on_data_changed(class_id)  # cảnh báo sớm của lớp, sau khi đã commit
    return manual.scores_after_save(session, user, class_id, subject_id, student_id, body.semester)
