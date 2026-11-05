"""teaching plan report: loai ban nhap goi y dieu chinh ke hoach day hoc

Revision ID: b2d7f4a9c6e1
Revises: a8c3e5f1d9b7
Create Date: 2026-11-05 13:00:00.000000

D-118: GVBM nho AI goi y dieu chinh ke hoach day hoc cua mot lop-mon (ban nhap, giao vien duyet).
CHECK cua reports.type va report_jobs.type them teaching_plan (13 ky tu, cot dang dai 15).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d7f4a9c6e1"
down_revision: str | Sequence[str] | None = "a8c3e5f1d9b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREV_TYPES = ("subject_comment", "school_record", "contact_slip", "report")
NEW_TYPES = (*PREV_TYPES, "teaching_plan")


def _replace(table: str, types: Sequence[str]) -> None:
    values = ", ".join(f"'{value}'" for value in types)
    name = op.f(f"ck_{table}_type")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, f"type IN ({values})")


def upgrade() -> None:
    _replace("reports", NEW_TYPES)
    _replace("report_jobs", NEW_TYPES)


def downgrade() -> None:
    op.execute("DELETE FROM reports WHERE type = 'teaching_plan'")
    op.execute("DELETE FROM report_jobs WHERE type = 'teaching_plan'")
    _replace("reports", PREV_TYPES)
    _replace("report_jobs", PREV_TYPES)
