"""user import jobs: nhập nhiều tài khoản giáo viên từ một tệp (chỉ Admin)

Revision ID: a7d2f3c9e1b4
Revises: 664e18a9fcd3
Create Date: 2026-11-03 12:40:00.000000

Chức năng nhập giáo viên từ tệp (ngoài 15 bảng của DESIGN mục 5):
- Bảng user_import_jobs: bản xem trước toàn trường của Admin (không gắn với một lớp), lưu bản ghi
  đã chuẩn hoá (họ tên, email, vai trò); KHÔNG lưu mật khẩu. UUID làm khoá chính.
- CHECK của audit_logs.action thêm import_users (cách làm như các migration trước; qua op.f).
  Độ dài lớn nhất vẫn là 20 ký tự.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d2f3c9e1b4"
down_revision: str | Sequence[str] | None = "664e18a9fcd3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Danh sách action tới hết migration trước (664e18a9fcd3).
PREV_ACTIONS = (
    "view_class_students",
    "view_student_profile",
    "view_class_dashboard",
    "view_subject_scores",
    "import_confirm",
    "view_class_alerts",
    "view_school_alerts",
    "update_alert",
    "upload_regulation",
    "update_regulation",
    "create_user",
    "update_user",
    "reset_user_password",
    "change_password",
    "update_school_year",
    "create_class",
    "update_class",
    "delete_class",
    "set_assignment",
    "remove_assignment",
    "remove_class_student",
    "generate_report",
    "edit_report",
    "approve_report",
    "export_report",
    "view_class_reports",
)
NEW_ACTIONS = ("import_users",)


def _replace_action_check(actions: Sequence[str]) -> None:
    values = ", ".join(f"'{action}'" for action in actions)
    op.drop_constraint(op.f("ck_audit_logs_action"), "audit_logs", type_="check")
    op.create_check_constraint(op.f("ck_audit_logs_action"), "audit_logs", f"action IN ({values})")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "previewed",
                "confirmed",
                name="status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="previewed",
            nullable=False,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["users.id"], name=op.f("fk_user_import_jobs_admin_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_import_jobs")),
    )
    op.create_index("ix_user_import_jobs_admin_id", "user_import_jobs", ["admin_id"], unique=False)
    op.create_index(
        "ix_user_import_jobs_expires_at", "user_import_jobs", ["expires_at"], unique=False
    )
    _replace_action_check((*PREV_ACTIONS, *NEW_ACTIONS))


def downgrade() -> None:
    """Downgrade schema. Xoá các dòng nhật ký dùng hành động mới để khôi phục được CHECK cũ."""
    audit_logs = sa.table("audit_logs", sa.column("action", sa.String))
    op.execute(audit_logs.delete().where(audit_logs.c.action.in_(NEW_ACTIONS)))
    _replace_action_check(PREV_ACTIONS)
    op.drop_index("ix_user_import_jobs_expires_at", table_name="user_import_jobs")
    op.drop_index("ix_user_import_jobs_admin_id", table_name="user_import_jobs")
    op.drop_table("user_import_jobs")
