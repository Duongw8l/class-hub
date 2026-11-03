"""Quản lý tài khoản của Admin (D-096, D-097): chỉ Admin, qua `AdminUser` (401 rồi 403 trước tiên).

Admin không xem dữ liệu học sinh (D-039): các endpoint này chỉ đụng bảng `users`.
"""

import json
import uuid
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.auth import admin_service as service
from app.auth import user_import
from app.auth.admin_schemas import (
    AdminUserOut,
    CreatedUserOut,
    PasswordResetOut,
    UserCreateIn,
    UserImportConfirmOut,
    UserImportPreviewOut,
    UserUpdateIn,
)
from app.auth.deps import AdminUser
from app.core.db import DbSession
from app.core.enums import UserRole
from app.imports.parsing import MAX_UPLOAD_BYTES, ImportFileError

router = APIRouter(prefix="/admin/users", tags=["admin"])

NOT_FOUND = "Không có tài khoản này."


def _parse_mapping(raw: str | None) -> dict[str, str | None] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='Ánh xạ cột phải là JSON dạng {"trường": "tên cột"}.',
        ) from None
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and (v is None or isinstance(v, str)) for k, v in value.items()
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='Ánh xạ cột phải là JSON dạng {"trường": "tên cột"}.',
        )
    return value


@router.get("", response_model=list[AdminUserOut], summary="Danh sách tài khoản (chỉ Admin)")
def list_users(
    admin: AdminUser,
    session: DbSession,
    role: Annotated[UserRole | None, Query(description="Lọc theo vai trò")] = None,
    active: Annotated[
        bool | None, Query(description="true: đang hoạt động; false: bị khoá")
    ] = None,
    q: Annotated[str | None, Query(max_length=100, description="Tìm theo tên hoặc email")] = None,
) -> list[AdminUserOut]:
    return service.list_users(session, role=role, active=active, query=q)


@router.post(
    "",
    response_model=CreatedUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo tài khoản, trả mật khẩu tạm một lần (chỉ Admin)",
)
def create_user(admin: AdminUser, session: DbSession, body: UserCreateIn) -> CreatedUserOut:
    try:
        return service.create_user(session, admin, body)
    except service.EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email này đã có tài khoản.") from None


@router.patch(
    "/{user_id}",
    response_model=AdminUserOut,
    summary="Sửa tên, email, vai trò, khoá hoặc mở khoá tài khoản (chỉ Admin)",
)
def update_user(
    user_id: int, admin: AdminUser, session: DbSession, body: UserUpdateIn
) -> AdminUserOut:
    try:
        return service.update_user(session, admin, user_id, body)
    except service.UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND) from None
    except service.EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email này đã có tài khoản.") from None
    except service.SelfProtected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Không thể khoá hoặc hạ quyền chính tài khoản đang đăng nhập.",
        ) from None
    except service.HasAssignments:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Giáo viên này đang chủ nhiệm hoặc được phân công giảng dạy. "
                "Hãy gỡ chủ nhiệm và phân công trước khi đổi vai trò."
            ),
        ) from None


@router.post(
    "/{user_id}/reset-password",
    response_model=PasswordResetOut,
    summary="Đặt lại mật khẩu, trả mật khẩu tạm một lần (chỉ Admin)",
)
def reset_password(user_id: int, admin: AdminUser, session: DbSession) -> PasswordResetOut:
    try:
        return service.reset_password(session, admin, user_id)
    except service.UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND) from None


@router.post(
    "/import",
    response_model=UserImportPreviewOut,
    summary="Tải tệp giáo viên và xem trước (chưa tạo tài khoản; chỉ Admin)",
)
def import_users_preview(
    admin: AdminUser,
    session: DbSession,
    file: Annotated[UploadFile, File(description="Tệp .xlsx hoặc .csv")],
    mapping: Annotated[str | None, Form(description='JSON {"trường": "tên cột"}')] = None,
    header_row: Annotated[int | None, Form(ge=1, le=50, description="Dòng tiêu đề")] = None,
) -> UserImportPreviewOut:
    # AdminUser đã chặn 401/403 TRƯỚC khi tới đây, nên chỉ Admin mới đọc được nội dung tệp.
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return user_import.create_preview(
            session,
            admin,
            filename=PurePath(file.filename or "tep").name,  # chỉ tên tệp, bỏ mọi đường dẫn
            data=data,
            mapping=_parse_mapping(mapping),
            header_row=header_row,
        )
    except ImportFileError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.post(
    "/import/{job_id}/confirm",
    response_model=UserImportConfirmOut,
    summary="Xác nhận bản xem trước: tạo tài khoản và trả mật khẩu tạm một lần (chỉ Admin)",
)
def import_users_confirm(
    job_id: uuid.UUID, admin: AdminUser, session: DbSession
) -> UserImportConfirmOut:
    try:
        return user_import.confirm_job(session, admin, job_id)
    except user_import.UserImportJobNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Không có bản xem trước này."
        ) from None
    except user_import.UserImportJobExpired:
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="Bản xem trước đã hết hạn (24 giờ). Hãy tải lại tệp.",
        ) from None
    except user_import.UserImportJobInvalid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Tệp còn dòng lỗi nên không thể xác nhận. Hãy sửa tệp rồi tải lại.",
        ) from None
    except user_import.UserImportConflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Một email trong tệp vừa được tạo tài khoản. Hãy tải lại tệp.",
        ) from None
