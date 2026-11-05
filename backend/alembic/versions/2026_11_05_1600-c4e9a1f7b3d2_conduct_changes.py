"""conduct changes: lich su sua / nhap tay ren luyen

Revision ID: c4e9a1f7b3d2
Revises: b2d7f4a9c6e1
Create Date: 2026-11-05 16:00:00.000000

D-119: GVCN sua hoac nhap tay ren luyen cua tung hoc sinh. Bang conduct_changes luu muc va nhan
xet cu -> moi, ly do, nguoi sua (chi them). CHECK cua audit_logs.action them view_class_conduct,
edit_conduct.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e9a1f7b3d2"
down_revision: str | Sequence[str] | None = "b2d7f4a9c6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Danh sach action toi het migration a8c3e5f1d9b7 (b2d7f4a9c6e1 khong doi danh sach).
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
    "import_users",
    "edit_scores",
)
NEW_ACTIONS = ("view_class_conduct", "edit_conduct")
LEVELS = ("good", "fair", "pass", "fail")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _replace_action_check(actions: Sequence[str]) -> None:
    values = ", ".join(f"'{action}'" for action in actions)
    op.drop_constraint(op.f("ck_audit_logs_action"), "audit_logs", type_="check")
    op.create_check_constraint(op.f("ck_audit_logs_action"), "audit_logs", f"action IN ({values})")


def upgrade() -> None:
    op.create_table(
        "conduct_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_student_id", sa.Integer(), nullable=False),
        sa.Column("period", _enum("period", "hk1", "hk2", "year"), nullable=False),
        sa.Column("old_level", _enum("old_level", *LEVELS), nullable=True),
        sa.Column("new_level", _enum("new_level", *LEVELS), nullable=False),
        sa.Column("old_comment", sa.Text(), nullable=True),
        sa.Column("new_comment", sa.Text(), nullable=True),
        sa.Column(
            "reason",
            _enum("reason", "review", "correction", "supplement", "other"),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["class_student_id"],
            ["class_students.id"],
            name=op.f("fk_conduct_changes_class_student_id_class_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], name=op.f("fk_conduct_changes_changed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conduct_changes")),
    )
    op.create_index("ix_conduct_changes_cs", "conduct_changes", ["class_student_id"])
    _replace_action_check((*PREV_ACTIONS, *NEW_ACTIONS))


def downgrade() -> None:
    audit_logs = sa.table("audit_logs", sa.column("action", sa.String))
    op.execute(audit_logs.delete().where(audit_logs.c.action.in_(NEW_ACTIONS)))
    _replace_action_check(PREV_ACTIONS)
    op.drop_index("ix_conduct_changes_cs", table_name="conduct_changes")
    op.drop_table("conduct_changes")
