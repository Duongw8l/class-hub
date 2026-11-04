"""Dependency xác thực của FastAPI: lấy người dùng hiện tại từ header Authorization: Bearer."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import User
from app.auth.tokens import InvalidTokenError, decode_access_token
from app.core.authorize import authorize_admin
from app.core.db import DbSession

# auto_error=False để tự trả 401 (HTTPBearer mặc định trả mã khác khi thiếu header).
_bearer = HTTPBearer(auto_error=False, description="Dán access token lấy từ POST /auth/login.")


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Cần đăng nhập.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_authenticated_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Người đăng nhập, KỂ CẢ khi còn đang dùng mật khẩu tạm. Chỉ dùng cho các endpoint cần để đặt
    mật khẩu mới (đổi mật khẩu, thông tin của chính mình); mọi endpoint khác dùng CurrentUser."""
    if credentials is None:
        raise _unauthenticated()
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _unauthenticated() from None
    # Nạp lại mỗi request: đổi vai trò, khoá hay xoá tài khoản có hiệu lực ngay (D-041, D-096).
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthenticated()
    return user


AuthenticatedUser = Annotated[User, Depends(get_authenticated_user)]


def get_current_user(user: AuthenticatedUser) -> User:
    # Mật khẩu tạm do Admin biết: chưa đặt mật khẩu riêng thì chưa được dùng dữ liệu (D-114).
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn đang dùng mật khẩu tạm. Hãy đặt mật khẩu mới trước khi tiếp tục.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _require_admin(user: CurrentUser) -> User:
    authorize_admin(user)
    return user


# Mọi endpoint /admin/*: 401 (chưa đăng nhập) rồi 403 (không phải Admin), cả hai chạy TRƯỚC khi đọc
# tệp tải lên hay kiểm hình dạng yêu cầu.
AdminUser = Annotated[User, Depends(_require_admin)]
