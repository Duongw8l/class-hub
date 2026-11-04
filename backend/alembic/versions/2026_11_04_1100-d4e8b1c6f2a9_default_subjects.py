"""default subjects: nap san 17 mon GDPT 2018 cap THPT

Revision ID: d4e8b1c6f2a9
Revises: b8e5c1a2d3f4
Create Date: 2026-11-04 11:00:00.000000

Vai tro "Giao vien <mon>" (D-112) can danh sach mon co san ma khong phai chay seed. Nap 17 mon
theo Chuong trinh GDPT 2018 (8 bat buoc + 9 lua chon), cung so lieu voi data/seed/curriculum.py
(chep cung vao day: migration khong import ma ngoai backend). ON CONFLICT (name) DO NOTHING nen
chay tren DB da co mon (da seed) khong doi gi. Seed van TRUNCATE va nap lai bang subjects.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e8b1c6f2a9"
down_revision: str | Sequence[str] | None = "b8e5c1a2d3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (ten, cach danh gia, so tiet/nam, tu chon)
SUBJECTS: tuple[tuple[str, str, int, bool], ...] = (
    ("Ngữ văn", "score", 105, False),
    ("Toán", "score", 105, False),
    ("Tiếng Anh", "score", 105, False),
    ("Lịch sử", "score", 52, False),
    ("Giáo dục thể chất", "comment", 70, False),
    ("Giáo dục quốc phòng và an ninh", "score", 35, False),
    ("Hoạt động trải nghiệm, hướng nghiệp", "comment", 105, False),
    ("Nội dung giáo dục địa phương", "comment", 35, False),
    ("Địa lí", "score", 70, True),
    ("Giáo dục kinh tế và pháp luật", "score", 70, True),
    ("Vật lí", "score", 70, True),
    ("Hóa học", "score", 70, True),
    ("Sinh học", "score", 70, True),
    ("Công nghệ", "score", 70, True),
    ("Tin học", "score", 70, True),
    ("Âm nhạc", "comment", 70, True),
    ("Mĩ thuật", "comment", 70, True),
)


def upgrade() -> None:
    """Upgrade schema."""
    insert = sa.text(
        "INSERT INTO subjects (name, assessment_type, periods_per_year, is_elective) "
        "VALUES (:name, :kind, :periods, :elective) ON CONFLICT (name) DO NOTHING"
    )
    for name, kind, periods, elective in SUBJECTS:
        op.execute(insert.bindparams(name=name, kind=kind, periods=periods, elective=elective))


def downgrade() -> None:
    """Downgrade schema. Chi xoa mon con chua duoc dung o dau ca (khong lam mo coi du lieu)."""
    op.execute(
        sa.text(
            "DELETE FROM subjects s WHERE s.name = ANY(:names) "
            "AND NOT EXISTS (SELECT 1 FROM teaching_assignments t WHERE t.subject_id = s.id) "
            "AND NOT EXISTS (SELECT 1 FROM assessments a WHERE a.subject_id = s.id) "
            "AND NOT EXISTS (SELECT 1 FROM exam_registrations e WHERE e.subject_id = s.id) "
            "AND NOT EXISTS (SELECT 1 FROM users u WHERE u.specialty_subject_id = s.id)"
        ).bindparams(names=[name for name, *_ in SUBJECTS])
    )
