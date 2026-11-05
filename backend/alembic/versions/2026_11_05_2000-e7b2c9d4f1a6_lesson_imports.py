"""lesson imports: nhap so diem danh theo tiet tu tep dang luoi

Revision ID: e7b2c9d4f1a6
Revises: d3dfd0412041
Create Date: 2026-11-05 20:00:00.000000

D-121: CHECK cua import_jobs.kind va import_mappings.kind them 'lessons'.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b2c9d4f1a6"
down_revision: str | Sequence[str] | None = "d3dfd0412041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREV_KINDS = ("assessments", "attendance", "conduct", "roster")
NEW_KINDS = (*PREV_KINDS, "lessons")
TABLES = ("import_jobs", "import_mappings")


def _replace(table: str, kinds: Sequence[str]) -> None:
    values = ", ".join(f"'{kind}'" for kind in kinds)
    name = op.f(f"ck_{table}_kind")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, f"kind IN ({values})")


def upgrade() -> None:
    for table in TABLES:
        _replace(table, NEW_KINDS)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DELETE FROM {table} WHERE kind = 'lessons'")
        _replace(table, PREV_KINDS)
