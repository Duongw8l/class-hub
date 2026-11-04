"""multi school year: nam hien hanh va bao cao theo nam hoc

Revision ID: e5f9c2d7a1b3
Revises: d4e8b1c6f2a9
Create Date: 2026-11-04 14:00:00.000000

Nhieu nam hoc (D-113):
- school_years.is_current: dung mot nam hien hanh (chi muc duy nhat mot phan). Nam co ngay bat dau
  muon nhat duoc dat lam hien hanh khi nang cap.
- reports.school_year_id (khoa ngoai): cung mot hoc sinh / cung khoi co bao cao rieng moi nam, nen
  khoa duy nhat cua bao cao them school_year_id. Dien lai tu lop cua bao cao; bao cao khoi (khong co
  lop) gan vao nam hien hanh.

Ha cap: bo cac bao cao khong thuoc nam hien hanh (khoa cu khong phan biet nam, se trung).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f9c2d7a1b3"
down_revision: str | Sequence[str] | None = "d4e8b1c6f2a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = ["type", "scope", "target_id", "semester"]


def _report_indexes(prefix: list[str]) -> None:
    op.create_index(
        "uq_reports_key",
        "reports",
        [*prefix, *KEY],
        unique=True,
        postgresql_where=sa.text("subject_id IS NULL"),
    )
    op.create_index(
        "uq_reports_key_subject",
        "reports",
        [*prefix, *KEY, "subject_id"],
        unique=True,
        postgresql_where=sa.text("subject_id IS NOT NULL"),
    )


def _drop_report_indexes() -> None:
    op.drop_index("uq_reports_key_subject", table_name="reports")
    op.drop_index("uq_reports_key", table_name="reports")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "school_years",
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(
        "UPDATE school_years SET is_current = true WHERE id = "
        "(SELECT id FROM school_years ORDER BY start_date DESC, id DESC LIMIT 1)"
    )
    op.create_index(
        "uq_school_years_current",
        "school_years",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.add_column("reports", sa.Column("school_year_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE reports r SET school_year_id = c.school_year_id "
        "FROM classes c WHERE c.id = r.class_id"
    )
    op.execute(
        "UPDATE reports SET school_year_id = (SELECT id FROM school_years WHERE is_current) "
        "WHERE school_year_id IS NULL"
    )
    op.alter_column("reports", "school_year_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_reports_school_year_id_school_years"),
        "reports",
        "school_years",
        ["school_year_id"],
        ["id"],
    )
    _drop_report_indexes()
    _report_indexes(["school_year_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DELETE FROM reports WHERE school_year_id IS DISTINCT FROM "
        "(SELECT id FROM school_years WHERE is_current)"
    )
    _drop_report_indexes()
    _report_indexes([])
    op.drop_constraint(
        op.f("fk_reports_school_year_id_school_years"), "reports", type_="foreignkey"
    )
    op.drop_column("reports", "school_year_id")
    op.drop_index("uq_school_years_current", table_name="school_years")
    op.drop_column("school_years", "is_current")
