"""must change password: bat doi mat khau sau khi dang nhap bang mat khau tam

Revision ID: f6a1d3e8b2c4
Revises: e5f9c2d7a1b3
Create Date: 2026-11-04 16:00:00.000000

D-114: users.must_change_password. Bat khi Admin tao tai khoan, dat lai mat khau hoac nhap tu tep
(mat khau tam); tat khi nguoi dung tu doi mat khau. Tai khoan san co giu false.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a1d3e8b2c4"
down_revision: str | Sequence[str] | None = "e5f9c2d7a1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
