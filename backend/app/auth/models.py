"""Model người dùng và nhật ký truy cập. GVBM / GVCN không phải cột: suy ra từ
teaching_assignments và classes.homeroom_teacher_id (xem docs/DESIGN.md mục 2)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, IntPk, enum_type
from app.core.enums import AuditAction, ImportStatus, UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Email không phân biệt hoa thường.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[IntPk]
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole, "role"))
    # Tài khoản bị khoá không đăng nhập được và token cũ nhận 401 ngay (D-096); không xoá tài khoản
    # vì điểm, nhật ký, phân công còn tham chiếu tới người dùng.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Đang dùng mật khẩu tạm do Admin cấp (tạo, đặt lại, nhập từ tệp): phải tự đặt mật khẩu mới
    # trước khi dùng các chức năng khác (D-114). Tắt khi người dùng đổi mật khẩu.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )
    # Nhãn nhận diện, KHÔNG cấp quyền (quyền dạy vẫn suy từ teaching_assignments): bộ môn (chuyên
    # môn) và ghi chú tự do, giúp phân biệt hai giáo viên trùng tên. Cả hai đều tuỳ chọn.
    specialty_subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"))
    note: Mapped[str | None] = mapped_column(String(255))


class AuditLog(Base):
    """Nhật ký mỗi lần ai đó mở dữ liệu học sinh (DESIGN mục 10). Chỉ thêm, không sửa.

    `class_id` là số nguyên thường, không có khoá ngoại, để nhật ký còn lại khi lớp bị xoá.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_class_id", "class_id"),
    )

    id: Mapped[IntPk]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[AuditAction] = mapped_column(enum_type(AuditAction, "action"))
    class_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[Any] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserImportJob(Base):
    """Bản xem trước nhập nhiều tài khoản giáo viên từ một tệp (chỉ Admin).

    Phạm vi toàn trường (khác import_jobs gắn với một lớp): chỉ Admin tạo. Job lưu các bản ghi
    hợp lệ đã chuẩn hoá (họ tên, email, vai trò) để xác nhận; KHÔNG bao giờ lưu mật khẩu. Sau khi
    xác nhận, `rows` được xoá rỗng.
    """

    __tablename__ = "user_import_jobs"
    __table_args__ = (
        Index("ix_user_import_jobs_admin_id", "admin_id"),
        Index("ix_user_import_jobs_expires_at", "expires_at"),
    )

    # UUID ngẫu nhiên: job_id nằm trong URL nên không được đoán ra.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ImportStatus] = mapped_column(
        enum_type(ImportStatus, "status"), server_default=ImportStatus.PREVIEWED.value
    )
    file_name: Mapped[str] = mapped_column(String(255))
    summary: Mapped[Any] = mapped_column(JSONB)  # các số đếm của bản xem trước (và kết quả ghi)
    rows: Mapped[Any] = mapped_column(JSONB)  # các bản ghi cần tạo, đã chuẩn hoá; rỗng sau xác nhận
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
