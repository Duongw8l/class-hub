"""Sinh bộ dữ liệu điểm GIẢ LẬP cho 30 lớp (khối 10, 11, 12 × 10 lớp), học kỳ I và II.

Toàn bộ là dữ liệu giả (nguyên tắc 7): họ tên và số điện thoại từ bộ sinh của seed (đầu số 0000
không tồn tại). Mã học sinh dạng HS26KKLLSS (26 = năm học 2026-2027, KK khối, LL lớp, SS số thứ
tự), không trùng mã seed (HS1102001…) hay tệp mẫu 11A9 (HS1109001…).

Kết quả trong `data/samples/diem-30-lop/`:
- `danh-sach-hoc-sinh/<lớp>.xlsx`: 40 học sinh mỗi lớp, Admin nhập vào lớp trước.
- `diem/<lớp>/<môn>-hk<1|2>.xlsx`: mỗi tệp một lớp, một môn, một học kỳ, đúng định dạng trang
  "Nhập điểm" (chỉ sheet đầu được đọc). Môn điểm số: Mã HS, Họ và tên, ĐĐGtx 1…n, ĐĐGgk, ĐĐGck,
  ĐTB (hệ thống bỏ qua cột ĐTB, tự tính lại). Môn đánh giá bằng nhận xét: cột "Nhận xét"
  (Đạt / Chưa đạt).
- `tong-hop.xlsx`: các lớp, tổ hợp môn, số tệp, và danh sách học sinh yếu cài sẵn.

Môn của lớp: 8 môn bắt buộc + 4 môn lựa chọn theo tổ hợp của seed (`class_subjects`). Số đầu điểm
thường xuyên theo số tiết/năm và ĐTB tính bằng `app.analytics` với cấu hình đọc từ bảng `settings`
(nguyên tắc 2), nên cần DB đã migrate.

Phân bố điểm: mỗi học sinh có "năng lực" ngẫu nhiên (phân phối chuẩn) như seed. Mỗi lớp cài sẵn 3
học sinh yếu (điểm trung bình khoảng 3,5–4,5) và 1 học sinh chỉ yếu môn Toán, để thấy cảnh báo sớm.

Chạy từ thư mục gốc repo:  PYTHONPATH=backend:. python data/samples/build_diem_30_lop.py
"""

import io
import random
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.analytics.config import AnalyticsConfig, load_config
from app.analytics.scores import semester_average_from_scores
from app.core.db import get_engine
from app.core.enums import AssessmentType
from data.seed.curriculum import ELECTIVE_COMBOS, SubjectSpec, class_subjects
from data.seed.people import random_full_name, random_phone

OUTPUT = Path(__file__).with_name("diem-30-lop")
GRADES = (10, 11, 12)
CLASSES_PER_GRADE = 10
CLASS_SIZE = 40
YEAR_NAME = "2026-2027"
YEAR_CODE = "26"
RANDOM_SEED = 30102026
WEAK_PER_CLASS = 3  # học sinh yếu mọi môn
WEAK_SUBJECT = "Toán"  # thêm 1 học sinh chỉ yếu môn này
BIRTH_YEAR = {10: 2011, 11: 2010, 12: 2009}

FONT = "Arial"
TITLE_FONT = Font(name=FONT, bold=True, size=12)
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF")
BODY_FONT = Font(name=FONT)
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


@dataclass
class Student:
    code: str
    name: str
    born: date
    guardian: str
    phone: str
    ability: float
    weak_note: str = ""  # khác rỗng: học sinh yếu cài sẵn
    weak_subject: str | None = None


@dataclass
class SchoolClass:
    grade: int
    index: int
    students: list[Student] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.grade}A{self.index}"

    @property
    def subjects(self) -> tuple[SubjectSpec, ...]:
        return class_subjects(self.index)


def slug(text: str) -> str:
    """ "Giáo dục thể chất" → "giao-duc-the-chat" (tên tệp không dấu)."""
    folded = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    words = "".join(ch if ch.isalnum() else " " for ch in plain).split()
    return "-".join(words)


def make_classes(rng: random.Random) -> list[SchoolClass]:
    classes: list[SchoolClass] = []
    for grade in GRADES:
        for index in range(1, CLASSES_PER_GRADE + 1):
            school_class = SchoolClass(grade, index)
            weak = set(rng.sample(range(CLASS_SIZE), WEAK_PER_CLASS + 1))
            weak_subject_pos = min(weak)
            for number in range(1, CLASS_SIZE + 1):
                ability = max(-2.5, min(2.5, rng.gauss(0.0, 1.0)))
                student = Student(
                    code=f"HS{YEAR_CODE}{grade}{index:02d}{number:02d}",
                    name=random_full_name(rng),
                    born=date(BIRTH_YEAR[grade], 1, 1) + timedelta(days=rng.randrange(365)),
                    guardian=random_full_name(rng),
                    phone=random_phone(rng),
                    ability=ability,
                )
                position = number - 1
                if position == weak_subject_pos:
                    student.ability = max(student.ability, 0.0)
                    student.weak_subject = WEAK_SUBJECT
                    student.weak_note = f"Yếu môn {WEAK_SUBJECT}"
                elif position in weak:
                    student.ability = rng.uniform(-2.6, -2.2)
                    student.weak_note = "Yếu nhiều môn"
                school_class.students.append(student)
            school_class.students.sort(key=lambda s: s.code)
            classes.append(school_class)
    return classes


def clamp_score(value: float) -> Decimal:
    tenths = max(0, min(100, round(value * 10)))
    return Decimal(tenths) / 10


@dataclass
class SubjectResult:
    tx: list[Decimal]
    gk: Decimal
    ck: Decimal
    average: Decimal | None


def score_results(
    rng: random.Random, student: Student, subject: SubjectSpec, tx_count: int
) -> dict[int, SubjectResult]:
    level = 6.9 + 1.1 * student.ability
    if student.weak_subject == subject.name:
        level = rng.uniform(2.8, 3.4)
    subject_mean = level + rng.gauss(0.0, 0.35)
    results: dict[int, SubjectResult] = {}
    for semester in (1, 2):
        mean = subject_mean + (rng.gauss(0.0, 0.25) if semester == 2 else 0.0)

        def draw(mean: float = mean) -> Decimal:
            return clamp_score(mean + rng.gauss(0.0, 0.8))

        tx = [draw() for _ in range(tx_count)]
        results[semester] = SubjectResult(tx, draw(), draw(), None)
    return results


def comment_results(rng: random.Random, student: Student) -> dict[int, str]:
    fail_chance = 0.25 if student.weak_note == "Yếu nhiều môn" else 0.02
    return {s: ("Chưa đạt" if rng.random() < fail_chance else "Đạt") for s in (1, 2)}


# --- Ghi Excel ---------------------------------------------------------------------------------


def style_table(sheet: Any, header_row: int, last_row: int, last_col: int) -> None:
    for col in range(1, last_col + 1):
        cell = sheet.cell(header_row, col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    for row in range(header_row + 1, last_row + 1):
        for col in range(1, last_col + 1):
            cell = sheet.cell(row, col)
            cell.font = BODY_FONT
            cell.border = BORDER
            if col != 3:
                cell.alignment = Alignment(horizontal="center")


def save(workbook: Workbook, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    workbook.save(buffer)
    path.write_bytes(buffer.getvalue())


def title_rows(sheet: Any, lines: list[str]) -> int:
    """Viết các dòng tiêu đề lớn + một dòng trống; trả số dòng của dòng tiêu đề cột."""
    for number, text in enumerate(lines, start=1):
        sheet.cell(number, 1, text).font = TITLE_FONT
    return len(lines) + 2


def write_roster(school_class: SchoolClass) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Danh sách lớp"
    header_row = title_rows(
        sheet,
        [
            "DỮ LIỆU GIẢ LẬP - KHÔNG PHẢI HỌC SINH THẬT",
            f"DANH SÁCH HỌC SINH LỚP {school_class.name} - NĂM HỌC {YEAR_NAME}",
        ],
    )
    headers = ["STT", "Mã HS", "Họ và tên", "Ngày sinh", "Họ tên phụ huynh", "Số điện thoại"]
    for col, text in enumerate(headers, start=1):
        sheet.cell(header_row, col, text)
    for number, student in enumerate(school_class.students, start=1):
        row = header_row + number
        values = [
            number,
            student.code,
            student.name,
            student.born.strftime("%d/%m/%Y"),
            student.guardian,
            student.phone,
        ]
        for col, value in enumerate(values, start=1):
            sheet.cell(row, col, value)
    style_table(sheet, header_row, header_row + len(school_class.students), len(headers))
    for col, width in zip("ABCDEF", (6, 14, 28, 13, 28, 15), strict=True):
        sheet.column_dimensions[col].width = width
    sheet.freeze_panes = sheet.cell(header_row + 1, 1)
    save(workbook, OUTPUT / "danh-sach-hoc-sinh" / f"{school_class.name}.xlsx")


def write_score_file(
    school_class: SchoolClass,
    subject: SubjectSpec,
    semester: int,
    rows: list[tuple[Student, SubjectResult | str]],
    tx_count: int,
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Bảng điểm"
    header_row = title_rows(
        sheet,
        [
            "DỮ LIỆU GIẢ LẬP - KHÔNG PHẢI ĐIỂM THẬT",
            f"BẢNG ĐIỂM MÔN {subject.name.upper()} - LỚP {school_class.name} - HỌC KỲ "
            f"{'I' if semester == 1 else 'II'} - NĂM HỌC {YEAR_NAME}",
        ],
    )
    is_comment = subject.assessment_type is AssessmentType.COMMENT
    headers = ["STT", "Mã HS", "Họ và tên"]
    if is_comment:
        headers.append("Nhận xét")
    else:
        headers += [*(f"ĐĐGtx {i}" for i in range(1, tx_count + 1)), "ĐĐGgk", "ĐĐGck", "ĐTB"]
    for col, text in enumerate(headers, start=1):
        sheet.cell(header_row, col, text)
    for number, (student, result) in enumerate(rows, start=1):
        row = header_row + number
        values: list[Any] = [number, student.code, student.name]
        if isinstance(result, str):
            values.append(result)
        else:
            values += [float(v) for v in (*result.tx, result.gk, result.ck)]
            values.append(float(result.average) if result.average is not None else None)
        for col, value in enumerate(values, start=1):
            cell = sheet.cell(row, col, value)
            if isinstance(value, float):
                cell.number_format = "0.0"
    style_table(sheet, header_row, header_row + len(rows), len(headers))
    sheet.column_dimensions["A"].width = 6
    sheet.column_dimensions["B"].width = 14
    sheet.column_dimensions["C"].width = 28
    for col in range(4, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(col)].width = 11
    sheet.freeze_panes = sheet.cell(header_row + 1, 4)
    name = f"{slug(subject.name)}-hk{semester}.xlsx"
    save(workbook, OUTPUT / "diem" / school_class.name / name)


# --- Sinh --------------------------------------------------------------------------------------


@dataclass
class WeakRow:
    school_class: str
    student: Student
    low_subjects: list[str]
    failed_comment: list[str]


def build(config: AnalyticsConfig) -> tuple[int, list[WeakRow], list[SchoolClass]]:
    rng = random.Random(RANDOM_SEED)
    classes = make_classes(rng)
    file_count = 0
    weak_rows: list[WeakRow] = []
    fail_threshold = config.score_threshold_pass  # 5,0: ngưỡng "đạt" của ĐTB môn
    for school_class in classes:
        write_roster(school_class)
        low: dict[str, list[str]] = {s.code: [] for s in school_class.students}
        failed: dict[str, list[str]] = {s.code: [] for s in school_class.students}
        for subject in school_class.subjects:
            tx_count = config.required_regular(subject.periods_per_year)
            by_semester: dict[int, list[tuple[Student, SubjectResult | str]]] = {1: [], 2: []}
            for student in school_class.students:
                student_rng = random.Random(f"{RANDOM_SEED}-{student.code}-{subject.name}")
                if subject.assessment_type is AssessmentType.COMMENT:
                    comments = comment_results(student_rng, student)
                    for semester, text in comments.items():
                        by_semester[semester].append((student, text))
                        if text == "Chưa đạt":
                            failed[student.code].append(f"{subject.name} HK{semester}")
                    continue
                results = score_results(student_rng, student, subject, tx_count)
                for semester, result in results.items():
                    result.average = semester_average_from_scores(
                        result.tx, result.gk, result.ck, config
                    )
                    by_semester[semester].append((student, result))
                    if result.average is not None and result.average < fail_threshold:
                        low[student.code].append(
                            f"{subject.name} HK{semester} ({str(result.average).replace('.', ',')})"
                        )
            for semester in (1, 2):
                write_score_file(school_class, subject, semester, by_semester[semester], tx_count)
                file_count += 1
        for student in school_class.students:
            if student.weak_note:
                weak_rows.append(
                    WeakRow(school_class.name, student, low[student.code], failed[student.code])
                )
    return file_count, weak_rows, classes


def write_summary(file_count: int, weak_rows: list[WeakRow], classes: list[SchoolClass]) -> None:
    workbook = Workbook()
    guide = workbook.active
    assert guide is not None
    guide.title = "Hướng dẫn"
    lines = [
        "BỘ ĐIỂM GIẢ LẬP 30 LỚP (KHỐI 10, 11, 12 × 10 LỚP) - NĂM HỌC " + YEAR_NAME,
        "Toàn bộ là dữ liệu giả lập, không phải học sinh hay điểm thật.",
        "",
        "Thứ tự nhập:",
        "1. Admin → Năm học & lớp: tạo các lớp 10A1…10A10, 11A1…11A10, 12A1…12A10 (nếu chưa có).",
        "2. Admin → mở từng lớp → Nhập danh sách học sinh: tệp danh-sach-hoc-sinh/<lớp>.xlsx.",
        "3. Admin phân công giáo viên bộ môn cho từng lớp–môn (Admin và BGH không nhập điểm được).",
        "4. Giáo viên bộ môn đăng nhập → lớp → Nhập điểm: chọn môn, học kỳ, tải tệp "
        "diem/<lớp>/<môn>-hk<1|2>.xlsx.",
        "",
        "Mỗi tệp điểm: một lớp, một môn, một học kỳ (hệ thống chỉ đọc sheet đầu tiên).",
        "Cột ĐTB trong tệp chỉ để xem; hệ thống tự tính lại ĐTB.",
        "Môn Giáo dục thể chất, Hoạt động trải nghiệm, Giáo dục địa phương, Âm nhạc, Mĩ thuật "
        "đánh giá bằng nhận xét (Đạt / Chưa đạt).",
        f"Tổng số tệp điểm: {file_count}. Mỗi lớp {CLASS_SIZE} học sinh.",
        "",
        f"Mỗi lớp có {WEAK_PER_CLASS} học sinh yếu nhiều môn và 1 học sinh chỉ yếu môn "
        f'{WEAK_SUBJECT}: xem sheet "Học sinh yếu".',
        "Sinh lại: PYTHONPATH=backend:. python data/samples/build_diem_30_lop.py",
    ]
    for number, text in enumerate(lines, start=1):
        guide.cell(number, 1, text).font = TITLE_FONT if number == 1 else BODY_FONT
    guide.column_dimensions["A"].width = 120

    sheet = workbook.create_sheet("Lớp và môn")
    headers = ["Lớp", "Khối", "Số HS", "Tổ hợp lựa chọn", "Các môn (12)", "Số tệp điểm"]
    for col, text in enumerate(headers, start=1):
        sheet.cell(1, col, text)
    for row, school_class in enumerate(classes, start=2):
        combo = ELECTIVE_COMBOS[(school_class.index - 1) % len(ELECTIVE_COMBOS)]
        values = [
            school_class.name,
            school_class.grade,
            len(school_class.students),
            ", ".join(combo),
            ", ".join(s.name for s in school_class.subjects),
            len(school_class.subjects) * 2,
        ]
        for col, value in enumerate(values, start=1):
            sheet.cell(row, col, value)
    style_table(sheet, 1, len(classes) + 1, len(headers))
    for col, width in zip("ABCDEF", (8, 7, 8, 55, 120, 12), strict=True):
        sheet.column_dimensions[col].width = width
    sheet.freeze_panes = "B2"

    weak = workbook.create_sheet("Học sinh yếu")
    headers = ["Lớp", "Mã HS", "Họ và tên", "Kiểu", "ĐTB môn dưới 5,0", "Nhận xét Chưa đạt"]
    for col, text in enumerate(headers, start=1):
        weak.cell(1, col, text)
    for row, item in enumerate(weak_rows, start=2):
        values = [
            item.school_class,
            item.student.code,
            item.student.name,
            item.student.weak_note,
            "; ".join(item.low_subjects) or "—",
            "; ".join(item.failed_comment) or "—",
        ]
        for col, value in enumerate(values, start=1):
            weak.cell(row, col, value)
    style_table(weak, 1, len(weak_rows) + 1, len(headers))
    for row in range(2, len(weak_rows) + 2):
        for col in range(5, 7):
            weak.cell(row, col).alignment = Alignment(wrap_text=True, vertical="top")
    for col, width in zip("ABCDEF", (8, 14, 26, 16, 90, 40), strict=True):
        weak.column_dimensions[col].width = width
    weak.freeze_panes = "A2"
    save(workbook, OUTPUT / "tong-hop.xlsx")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    with Session(get_engine()) as session:
        config = load_config(session)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    file_count, weak_rows, classes = build(config)
    write_summary(file_count, weak_rows, classes)
    print(f"Đã ghi {OUTPUT}: {len(classes)} lớp, {file_count} tệp điểm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
