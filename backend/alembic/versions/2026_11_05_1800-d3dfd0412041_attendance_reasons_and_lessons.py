"""attendance reasons and lessons: ly do vang, vang do truong cu di, so diem danh theo tiet

Revision ID: d3dfd0412041
Revises: c4e9a1f7b3d2
Create Date: 2026-11-05 18:00:00.000000

D-120: attendance them reason, note va trang thai school_duty (khong tinh buoi nghi); bang
attendance_changes (lich su diem danh ngay nhap / sua tay cua GVCN); bang lessons va
lesson_absences (GVBM diem danh theo tiet). CHECK cua audit_logs.action them 4 hanh dong.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3dfd0412041"
down_revision: str | Sequence[str] | None = "c4e9a1f7b3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREV_STATUSES = ("present", "absent_excused", "absent_unexcused", "late")
NEW_STATUSES = (*PREV_STATUSES, "school_duty")

# Danh sach action toi het migration c4e9a1f7b3d2.
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
    "view_class_conduct",
    "edit_conduct",
)
NEW_ACTIONS = ("view_attendance", "edit_attendance", "view_lessons", "edit_lesson")


def _replace_check(table: str, column: str, values: Sequence[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    name = op.f(f"ck_{table}_{column}")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, f"{column} IN ({listed})")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("lesson_no", sa.SmallInteger(), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("lesson_no BETWEEN 1 AND 10", name=op.f("ck_lessons_lesson_no")),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            name=op.f("fk_lessons_class_id_classes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_lessons_recorded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_lessons_subject_id_subjects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
        sa.UniqueConstraint("class_id", "date", "lesson_no", name="uq_lessons_class_date_no"),
    )
    op.create_index(
        "ix_lessons_class_subject_date", "lessons", ["class_id", "subject_id", "date"], unique=False
    )
    op.create_table(
        "attendance_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_student_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "old_status",
            sa.Enum(
                "present",
                "absent_excused",
                "absent_unexcused",
                "late",
                "school_duty",
                name="old_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "new_status",
            sa.Enum(
                "present",
                "absent_excused",
                "absent_unexcused",
                "late",
                "school_duty",
                name="new_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "old_reason",
            sa.Enum(
                "sick",
                "family",
                "competition",
                "school_activity",
                "other",
                name="old_reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "new_reason",
            sa.Enum(
                "sick",
                "family",
                "competition",
                "school_activity",
                "other",
                name="new_reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
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
            ["changed_by"], ["users.id"], name=op.f("fk_attendance_changes_changed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["class_student_id"],
            ["class_students.id"],
            name=op.f("fk_attendance_changes_class_student_id_class_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_changes")),
    )
    op.create_index(
        "ix_attendance_changes_cs_date",
        "attendance_changes",
        ["class_student_id", "date"],
        unique=False,
    )
    op.create_table(
        "lesson_absences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("class_student_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "present",
                "absent_excused",
                "absent_unexcused",
                "late",
                "school_duty",
                name="status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.Enum(
                "sick",
                "family",
                "competition",
                "school_activity",
                "other",
                name="reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "status IN ('absent_excused', 'absent_unexcused', 'late')",
            name=op.f("ck_lesson_absences_lesson_status"),
        ),
        sa.ForeignKeyConstraint(
            ["class_student_id"],
            ["class_students.id"],
            name=op.f("fk_lesson_absences_class_student_id_class_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_lesson_absences_lesson_id_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_absences")),
        sa.UniqueConstraint("lesson_id", "class_student_id", name="uq_lesson_absences_lesson_cs"),
    )
    op.add_column(
        "attendance",
        sa.Column(
            "reason",
            sa.Enum(
                "sick",
                "family",
                "competition",
                "school_activity",
                "other",
                name="reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    op.add_column("attendance", sa.Column("note", sa.String(length=255), nullable=True))
    _replace_check("attendance", "status", NEW_STATUSES)
    _replace_check("audit_logs", "action", (*PREV_ACTIONS, *NEW_ACTIONS))


def downgrade() -> None:
    """Downgrade schema."""
    audit_logs = sa.table("audit_logs", sa.column("action", sa.String))
    op.execute(audit_logs.delete().where(audit_logs.c.action.in_(NEW_ACTIONS)))
    _replace_check("audit_logs", "action", PREV_ACTIONS)
    # Vang do truong cu di khong co o phien ban cu: doi thanh nghi co phep (gan nhat ve y nghia).
    op.execute("UPDATE attendance SET status = 'absent_excused' WHERE status = 'school_duty'")
    _replace_check("attendance", "status", PREV_STATUSES)
    op.drop_column("attendance", "note")
    op.drop_column("attendance", "reason")
    op.drop_table("lesson_absences")
    op.drop_index("ix_attendance_changes_cs_date", table_name="attendance_changes")
    op.drop_table("attendance_changes")
    op.drop_index("ix_lessons_class_subject_date", table_name="lessons")
    op.drop_table("lessons")
