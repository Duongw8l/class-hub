"""Sinh tệp kết quả rèn luyện GIẢ LẬP cho 30 lớp của bộ `diem-30-lop/` (học kỳ I, II và cả năm).

Toàn bộ là dữ liệu giả (nguyên tắc 7). Học sinh lấy đúng từ bộ sinh `build_diem_30_lop.make_classes`
(cùng hạt giống), nên mã và họ tên khớp DB sau khi đã nạp bộ điểm 30 lớp.

Kết quả trong `data/samples/ren-luyen-30-lop/`:
- `<lớp>/ren-luyen-hk1.xlsx`, `ren-luyen-hk2.xlsx`, `ren-luyen-ca-nam.xlsx`: đúng định dạng trang
  "Nhập dữ liệu → Rèn luyện" của GVCN. Cột: STT, Mã HS, Họ và tên, Xếp loại rèn luyện (Tốt / Khá /
  Đạt / Chưa đạt), Nhận xét.
- `tong-hop.xlsx`: số học sinh theo mức của từng lớp và từng kỳ.

Phân bố: mức rèn luyện gắn nhẹ với "năng lực" của học sinh trong bộ điểm (em học yếu dễ có mức thấp
hơn, nhưng không phải luôn luôn) cộng nhiễu ngẫu nhiên. Học kỳ II nhìn chung tiến bộ nhẹ so với học
kỳ I. Cả năm lấy theo học kỳ II (cùng cách hệ thống tự suy ra khi chưa nhập cả năm, D-053), trừ khi
học kỳ II thấp hơn học kỳ I hai mức trở lên thì cả năm chỉ thấp hơn học kỳ I một mức.

Chạy trong container backend (cần data/samples đã chép vào /data/samples):
    PYTHONPATH=/app:/ python /data/samples/build_ren_luyen_30_lop.py
"""

import random
import shutil
import sys
from collections import Counter
from pathlib import Path

from openpyxl import Workbook

from data.samples.build_diem_30_lop import (
    RANDOM_SEED,
    YEAR_NAME,
    SchoolClass,
    Student,
    make_classes,
    save,
    style_table,
    title_rows,
)

OUTPUT = Path(__file__).with_name("ren-luyen-30-lop")
LEVELS = ("Tốt", "Khá", "Đạt", "Chưa đạt")  # từ cao xuống thấp
PERIODS = {"hk1": "HỌC KỲ I", "hk2": "HỌC KỲ II", "year": "CẢ NĂM"}
FILE_NAMES = {"hk1": "ren-luyen-hk1", "hk2": "ren-luyen-hk2", "year": "ren-luyen-ca-nam"}

# Ngưỡng của điểm rèn luyện ẩn (càng cao càng tốt): Tốt, Khá, Đạt; dưới cùng là Chưa đạt.
CUTS = (0.35, -0.75, -2.05)

COMMENTS = {
    "Tốt": (
        "Chấp hành tốt nội quy, tích cực tham gia hoạt động của lớp.",
        "Lễ phép, hoà nhã với bạn bè, có ý thức tự giác cao.",
        "Gương mẫu, nhiệt tình giúp đỡ bạn trong học tập.",
    ),
    "Khá": (
        "Chấp hành nội quy, cần chủ động hơn trong hoạt động tập thể.",
        "Ngoan, đôi khi còn thiếu tập trung trong giờ học.",
        "Có ý thức rèn luyện, cần đúng giờ hơn.",
    ),
    "Đạt": (
        "Còn vi phạm nội quy vài lần, cần cố gắng hơn.",
        "Cần chú ý hơn tới nề nếp và nhiệm vụ được giao.",
    ),
    "Chưa đạt": ("Vi phạm nội quy nhiều lần, cần gia đình phối hợp nhắc nhở.",),
}


def level_of(score: float) -> int:
    """Chỉ số mức trong LEVELS (0 = Tốt)."""
    return next((i for i, cut in enumerate(CUTS) if score >= cut), len(CUTS))


def student_levels(student: Student) -> dict[str, int]:
    rng = random.Random(f"{RANDOM_SEED}-{student.code}-ren-luyen")
    first = 0.6 * student.ability + rng.gauss(0.45, 0.65)
    second = first + rng.gauss(0.12, 0.4)  # học kỳ II tiến bộ nhẹ
    hk1, hk2 = level_of(first), level_of(second)
    year = hk2 if hk2 - hk1 < 2 else hk1 + 1
    return {"hk1": hk1, "hk2": hk2, "year": year}


def comment_for(student: Student, period: str, level: str) -> str:
    rng = random.Random(f"{RANDOM_SEED}-{student.code}-nhan-xet-{period}")
    return rng.choice(COMMENTS[level])


def write_file(school_class: SchoolClass, period: str, levels: dict[str, dict[str, int]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Rèn luyện"
    header_row = title_rows(
        sheet,
        [
            "DỮ LIỆU GIẢ LẬP - KHÔNG PHẢI HỌC SINH THẬT",
            f"KẾT QUẢ RÈN LUYỆN {PERIODS[period]} - LỚP {school_class.name} - NĂM HỌC {YEAR_NAME}",
        ],
    )
    headers = ["STT", "Mã HS", "Họ và tên", "Xếp loại rèn luyện", "Nhận xét"]
    for col, text in enumerate(headers, start=1):
        sheet.cell(header_row, col, text)
    for number, student in enumerate(school_class.students, start=1):
        level = LEVELS[levels[student.code][period]]
        values = [number, student.code, student.name, level, comment_for(student, period, level)]
        for col, value in enumerate(values, start=1):
            sheet.cell(header_row + number, col, value)
    style_table(sheet, header_row, header_row + len(school_class.students), len(headers))
    for col, width in zip("ABCDE", (6, 14, 28, 18, 60), strict=True):
        sheet.column_dimensions[col].width = width
    sheet.freeze_panes = sheet.cell(header_row + 1, 1)
    save(workbook, OUTPUT / school_class.name / f"{FILE_NAMES[period]}.xlsx")


def write_summary(rows: list[tuple[str, str, Counter[str]]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Tổng hợp"
    header_row = title_rows(
        sheet,
        [
            "DỮ LIỆU GIẢ LẬP - KHÔNG PHẢI HỌC SINH THẬT",
            f"TỔNG HỢP KẾT QUẢ RÈN LUYỆN 30 LỚP - NĂM HỌC {YEAR_NAME}",
        ],
    )
    headers = ["Lớp", "Kỳ", *LEVELS]
    for col, text in enumerate(headers, start=1):
        sheet.cell(header_row, col, text)
    for number, (name, period, counts) in enumerate(rows, start=1):
        values = [name, PERIODS[period].capitalize(), *(counts[level] for level in LEVELS)]
        for col, value in enumerate(values, start=1):
            sheet.cell(header_row + number, col, value)
    style_table(sheet, header_row, header_row + len(rows), len(headers))
    sheet.column_dimensions["B"].width = 12
    save(workbook, OUTPUT / "tong-hop.xlsx")


def build() -> tuple[list[SchoolClass], dict[str, Counter[str]]]:
    classes = make_classes(random.Random(RANDOM_SEED))
    totals: dict[str, Counter[str]] = {period: Counter() for period in PERIODS}
    rows: list[tuple[str, str, Counter[str]]] = []
    for school_class in classes:
        levels = {s.code: student_levels(s) for s in school_class.students}
        for period in PERIODS:
            write_file(school_class, period, levels)
            counts = Counter(LEVELS[item[period]] for item in levels.values())
            totals[period].update(counts)
            rows.append((school_class.name, period, counts))
    write_summary(rows)
    return classes, totals


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    classes, totals = build()
    print(f"Đã ghi {OUTPUT}: {len(classes)} lớp × {len(PERIODS)} kỳ.")
    for period, counts in totals.items():
        print(f"  {PERIODS[period]}: " + ", ".join(f"{lv} {counts[lv]}" for lv in LEVELS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
