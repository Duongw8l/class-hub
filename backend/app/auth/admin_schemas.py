"""Schema của API quản lý tài khoản (Admin) và đổi mật khẩu. Không schema nào có password_hash."""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.core.enums import ImportStatus, UserRole
from app.core.security import MAX_PASSWORD_BYTES

# Kiểm hình dạng đơn giản, không thêm thư viện email-validator: một @ và có dấu chấm ở tên miền.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=255, pattern=EMAIL_PATTERN)
]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

MIN_PASSWORD_LENGTH = 8


class AdminUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    role_label: str
    is_active: bool
    homeroom_class: str | None  # tên lớp đang chủ nhiệm
    assignment_count: int  # số cặp lớp-môn được phân công


class UserCreateIn(BaseModel):
    email: Email
    full_name: FullName
    role: UserRole


class UserUpdateIn(BaseModel):
    """Chỉ các trường có gửi lên mới đổi (`model_fields_set`)."""

    email: Email | None = None
    full_name: FullName | None = None
    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _no_null_values(self) -> Self:
        # null nghĩa là "không đổi" chứ không phải xoá giá trị; gửi null tường minh là nhầm lẫn.
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"'{name}' không được để trống.")
        if not self.model_fields_set:
            raise ValueError("Không có trường nào để đổi.")
        return self


class CreatedUserOut(BaseModel):
    user: AdminUserOut
    # Bản rõ chỉ có trong phản hồi này; không lưu ở đâu khác và không ghi nhật ký.
    temporary_password: str


class PasswordResetOut(BaseModel):
    temporary_password: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _within_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Mật khẩu mới dài quá {MAX_PASSWORD_BYTES} byte.")
        return value


class MessageOut(BaseModel):
    detail: str


# --- Nhập giáo viên từ tệp (chỉ Admin) ----------------------------------------------------------


class UserImportMessageOut(BaseModel):
    column: str | None  # tên cột trong tệp (hoặc tên trường nếu chưa ánh xạ)
    message: str


class UserImportRowOut(BaseModel):
    line: int  # số dòng trong tệp
    full_name: str | None
    email: str | None
    role: UserRole | None  # None khi vai trò trống/không hợp lệ
    role_label: str | None
    status: Literal["ok", "warning", "error"]
    action: Literal["new"] | None  # chỉ tạo tài khoản mới; None khi dòng lỗi
    messages: list[UserImportMessageOut]


class UserImportFieldOut(BaseModel):
    name: str
    label: str
    required: bool
    column: str | None  # cột của tệp đang được ánh xạ vào trường này


class UserImportSummaryOut(BaseModel):
    total_rows: int
    error_rows: int
    warning_rows: int
    new_rows: int  # số tài khoản sẽ được tạo
    has_changes: bool


class UserImportPreviewOut(BaseModel):
    # None khi thiếu cột bắt buộc: chưa có bản xem trước để xác nhận. Có dòng lỗi thì vẫn có
    # job_id nhưng can_confirm là False và xác nhận bị từ chối.
    job_id: uuid.UUID | None
    file_name: str
    header_line: int
    detected_columns: list[str]
    fields: list[UserImportFieldOut]
    missing_required: list[str]
    ignored_columns: list[str]
    notes: list[str]
    summary: UserImportSummaryOut
    can_confirm: bool
    expires_at: datetime | None
    rows: list[UserImportRowOut]
    truncated: bool  # True: chỉ liệt kê một phần dòng (luôn gồm mọi dòng lỗi và cảnh báo)


class CreatedCredentialOut(BaseModel):
    full_name: str
    email: str
    role: UserRole
    role_label: str
    # Bản rõ chỉ có trong phản hồi này; không lưu ở đâu khác và không ghi nhật ký.
    temporary_password: str


class UserImportConfirmOut(BaseModel):
    job_id: uuid.UUID
    status: ImportStatus
    created: int
    already_confirmed: bool
    # Danh sách tài khoản vừa tạo kèm mật khẩu tạm (rỗng khi xác nhận lại job đã xong).
    credentials: list[CreatedCredentialOut]
