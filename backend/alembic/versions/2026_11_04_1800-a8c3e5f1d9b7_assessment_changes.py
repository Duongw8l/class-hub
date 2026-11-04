"""assessment changes: lich su sua / nhap tay diem

Revision ID: a8c3e5f1d9b7
Revises: f6a1d3e8b2c4
Create Date: 2026-11-04 18:00:00.000000

D-115: GVBM sua hoac nhap tay diem cua tung hoc sinh. Bang assessment_changes luu diem cu -> moi,
ly do, nguoi sua (chi them). CHECK cua audit_logs.action them edit_scores.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8c3e5f1d9b7"
down_revision: str | Sequence[str] | None = "f6a1d3e8b2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Danh sach action toi het migration a7d2f3c9e1b4 (cac migration sau do khong doi danh sach).
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
)
NEW_ACTIONS = ("edit_scores",)


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _replace_action_check(actions: Sequence[str]) -> None:
    values = ", ".join(f"'{action}'" for action in actions)
    op.drop_constraint(op.f("ck_audit_logs_action"), "audit_logs", type_="check")
    op.create_check_constraint(op.f("ck_audit_logs_action"), "audit_logs", f"action IN ({values})")


def upgrade() -> None:
    op.create_table(
        "assessment_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_student_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("semester", sa.SmallInteger(), nullable=False),
        sa.Column("kind", _enum("kind", "tx", "gk", "ck"), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("old_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("new_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("old_comment_result", _enum("old_comment_result", "pass", "fail"), nullable=True),
        sa.Column("new_comment_result", _enum("new_comment_result", "pass", "fail"), nullable=True),
        sa.Column(
            "reason", _enum("reason", "retest", "makeup", "correction", "other"), nullable=False
        ),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("semester IN (1, 2)", name=op.f("ck_assessment_changes_semester")),
        sa.ForeignKeyConstraint(
            ["class_student_id"],
            ["class_students.id"],
            name=op.f("fk_assessment_changes_class_student_id_class_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_assessment_changes_subject_id_subjects")
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], name=op.f("fk_assessment_changes_changed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_changes")),
    )
    op.create_index(
        "ix_assessment_changes_cs_subject",
        "assessment_changes",
        ["class_student_id", "subject_id"],
    )
    _replace_action_check((*PREV_ACTIONS, *NEW_ACTIONS))


def downgrade() -> None:
    audit_logs = sa.table("audit_logs", sa.column("action", sa.String))
    op.execute(audit_logs.delete().where(audit_logs.c.action.in_(NEW_ACTIONS)))
    _replace_action_check(PREV_ACTIONS)
    op.drop_index("ix_assessment_changes_cs_subject", table_name="assessment_changes")
    op.drop_table("assessment_changes")
