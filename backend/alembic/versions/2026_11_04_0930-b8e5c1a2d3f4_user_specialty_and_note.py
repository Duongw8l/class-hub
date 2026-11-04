"""user specialty and note: nhan dien giao vien trung ten

Revision ID: b8e5c1a2d3f4
Revises: a7d2f3c9e1b4
Create Date: 2026-11-04 09:30:00.000000

Them hai cot nhan dien (khong cap quyen) vao bang users:
- specialty_subject_id: bo mon (chuyen mon) cua giao vien, khoa ngoai toi subjects.id, cho phep
  NULL. Quyen day van suy ra tu teaching_assignments; cot nay chi la nhan de phan biet GV trung ten.
- note: ghi chu tu do (toi da 255 ky tu), cho phep NULL.

(Chu thich khong dau: Alembic doc file theo cp1252 tren Windows nen tranh ky tu co dau, D-xxx.)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e5c1a2d3f4"
down_revision: str | Sequence[str] | None = "a7d2f3c9e1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("specialty_subject_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("note", sa.String(length=255), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_specialty_subject_id_subjects"),
        "users",
        "subjects",
        ["specialty_subject_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_users_specialty_subject_id_subjects"), "users", type_="foreignkey")
    op.drop_column("users", "note")
    op.drop_column("users", "specialty_subject_id")
