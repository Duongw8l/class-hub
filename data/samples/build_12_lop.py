"""Sinh `data/samples/12-lop.xlsx`: danh sách giáo viên đủ 17 môn cho trường 3 khối × 12 lớp.

Toàn bộ là dữ liệu GIẢ LẬP (nguyên tắc 7): họ tên sinh bằng bộ sinh của seed, email
`@thpt-demo.local`.

Cách chia (ghi lại trong sheet "Hướng dẫn" của tệp):
- 36 lớp: 10A1–10A12, 11A1–11A12, 12A1–12A12. Mỗi lớp 8 môn bắt buộc + 4 môn lựa chọn theo tổ hợp
  của seed (`ELECTIVE_COMBOS`, D-031), quay vòng nên mỗi tổ hợp có 4 lớp mỗi khối.
- Tiết/tuần của môn = tiết/năm ÷ 35 tuần. Một giáo viên dạy tối đa ⌊17 ÷ tiết/tuần⌋ lớp (định mức
  17 tiết/tuần), số giáo viên của môn = ⌈số lớp học môn ÷ số lớp tối đa⌉; các lớp chia đều và liền
  nhau theo thứ tự lớp nên giáo viên ít phải dạy rải nhiều khối.
- Mỗi lớp một GVCN, chọn trong các giáo viên đang dạy lớp đó, mỗi người chủ nhiệm tối đa một lớp.

Chạy từ thư mục gốc repo:  PYTHONPATH=backend:. python data/samples/build_12_lop.py
"""

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from data.seed.curriculum import ELECTIVE_COMBOS, SUBJECTS, SubjectSpec, class_subjects
from data.seed.people import random_full_name

OUTPUT = Path(__file__).with_name("12-lop.xlsx")
GRADES = (10, 11, 12)
CLASSES_PER_GRADE = 12
WEEKS_PER_YEAR = 35  # giả định, sửa được trong sheet Hướng dẫn
PERIOD_QUOTA = (
    17  # định mức tiết/tuần của giáo viên THPT — giả định, sửa được trong sheet Hướng dẫn
)
EMAIL_DOMAIN = "thpt-demo.local"
RANDOM_SEED = 1212

# Thứ tự ưu tiên chọn GVCN (giáo viên dạy nhiều tiết, gặp lớp thường xuyên).
HOMEROOM_PRIORITY = (
    "Ngữ văn", "Toán", "Tiếng Anh", "Lịch sử", "Vật lí", "Hóa học", "Sinh học", "Địa lí",
    "Giáo dục kinh tế và pháp luật", "Tin học", "Công nghệ",
)  # fmt: skip

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
SUBHEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
NOT_STUDIED_FILL = PatternFill("solid", fgColor="EDEDED")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
# Cột môn đầu và cuối trong sheet Phân công (C … S, theo thứ tự SUBJECTS).
SUBJECT_COLS = ("C", get_column_letter(2 + len(SUBJECTS)))


@dataclass
class Teacher:
    code: str  # ví dụ TOAN-01, dùng trong email
    name: str
    subject: SubjectSpec
    classes: list[str] = field(default_factory=list)
    homeroom: str | None = None

    @property
    def email(self) -> str:
        return f"gv.{self.code.lower().replace('-', '.')}@{EMAIL_DOMAIN}"

    @property
    def weekly(self) -> float:
        return len(self.classes) * self.subject.periods_per_year / WEEKS_PER_YEAR


def class_names() -> list[tuple[int, int, str]]:
    return [(g, i, f"{g}A{i}") for g in GRADES for i in range(1, CLASSES_PER_GRADE + 1)]


def build_plan() -> tuple[list[Teacher], dict[tuple[str, str], Teacher], dict[str, Teacher]]:
    """Trả (giáo viên, phân công (lớp, môn) → GV, GVCN lớp → GV)."""
    rng = random.Random(RANDOM_SEED)
    used_names: set[str] = set()

    def unique_name() -> str:
        while True:
            name = random_full_name(rng)
            if name not in used_names:
                used_names.add(name)
                return name

    teachers: list[Teacher] = []
    assignment: dict[tuple[str, str], Teacher] = {}
    for subject in SUBJECTS:
        taking = [name for g, i, name in class_names() if subject in class_subjects(i)]
        if not taking:
            continue
        weekly = subject.periods_per_year / WEEKS_PER_YEAR
        max_classes = math.floor(PERIOD_QUOTA / weekly)
        count = math.ceil(len(taking) / max_classes)
        base, extra = divmod(len(taking), count)
        start = 0
        for n in range(count):
            size = base + (1 if n < extra else 0)
            teacher = Teacher(
                code=f"{subject.code.upper()}-{n + 1:02d}", name=unique_name(), subject=subject
            )
            teacher.classes = taking[start : start + size]
            start += size
            for class_name in teacher.classes:
                assignment[(class_name, subject.name)] = teacher
            teachers.append(teacher)

    return teachers, assignment, assign_homerooms(assignment)


def assign_homerooms(assignment: dict[tuple[str, str], Teacher]) -> dict[str, Teacher]:
    """Mỗi lớp một GVCN đang dạy lớp đó, mỗi giáo viên tối đa một lớp.

    Ghép cặp hai phía (đường tăng, Kuhn): tham lam đơn thuần hết người ở các lớp cuối vì mỗi giáo
    viên dạy một dải lớp liền nhau. Ứng viên của lớp xếp theo thứ tự ưu tiên môn rồi ít tiết hơn.
    """
    rank = {name: index for index, name in enumerate(HOMEROOM_PRIORITY)}
    prefs: dict[str, list[Teacher]] = {}
    for _, _, class_name in class_names():
        candidates = [t for (c, _), t in assignment.items() if c == class_name]
        candidates.sort(key=lambda t: (rank.get(t.subject.name, len(rank)), t.weekly, t.code))
        prefs[class_name] = candidates

    owner: dict[str, str] = {}  # mã GV → lớp chủ nhiệm

    def place(class_name: str, seen: set[str]) -> bool:
        for teacher in prefs[class_name]:
            if teacher.code in seen:
                continue
            seen.add(teacher.code)
            if teacher.code not in owner or place(owner[teacher.code], seen):
                owner[teacher.code] = class_name
                return True
        return False

    for _, _, class_name in class_names():
        if not place(class_name, set()):
            raise RuntimeError(f"Không tìm được GVCN cho lớp {class_name}.")

    by_code = {t.code: t for t in assignment.values()}
    homeroom: dict[str, Teacher] = {}
    for code, class_name in owner.items():
        by_code[code].homeroom = class_name
        homeroom[class_name] = by_code[code]
    return homeroom


def style_header(cell, *, fill: PatternFill = HEADER_FILL, white: bool = True) -> None:
    cell.font = Font(name=FONT, bold=True, color="FFFFFF" if white else "000000")
    cell.fill = fill
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = BORDER


def body(cell, *, center: bool = False, blue: bool = False, number: str | None = None) -> None:
    cell.font = Font(name=FONT, color="0000FF" if blue else "000000")
    cell.alignment = Alignment(
        horizontal="center" if center else "left", vertical="center", wrap_text=True
    )
    cell.border = BORDER
    if number:
        cell.number_format = number


def title(ws: Worksheet, text: str, note: str, width: int) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    ws["A2"] = note
    ws["A2"].font = Font(name=FONT, italic=True, color="595959")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=width)
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 30


def sheet_teachers(ws: Worksheet, teachers: list[Teacher]) -> None:
    """Sheet đầu tiên, đúng định dạng 'Nhập giáo viên từ tệp': chỉ giá trị, tiêu đề ở dòng 1."""
    ws.title = "Giáo viên"
    headers = ("Họ và tên", "Email", "Vai trò", "Ghi chú")
    for col, text in enumerate(headers, start=1):
        style_header(ws.cell(row=1, column=col, value=text))
    for row, t in enumerate(teachers, start=2):
        note = f"Mã {t.code}; dạy {len(t.classes)} lớp: {', '.join(t.classes)}"
        if t.homeroom:
            note += f"; GVCN {t.homeroom}"
        values = (t.name, t.email, f"Giáo viên {t.subject.name}", note)
        for col, value in enumerate(values, start=1):
            body(ws.cell(row=row, column=col, value=value))
    for col, width in zip("ABCD", (24, 30, 44, 90), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:D{len(teachers) + 1}"


def sheet_guide(ws: Worksheet, teacher_count: int) -> tuple[str, str]:
    """Hướng dẫn + ô thông số. Trả địa chỉ tuyệt đối của ô 'số tuần' và ô 'định mức'."""
    ws["A1"] = "Danh sách giáo viên và phân công cho trường 3 khối × 12 lớp (dữ liệu GIẢ LẬP)"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    ws["A3"] = "Thông số (ô chữ xanh sửa được; các sheet tính lại theo)"
    ws["A3"].font = Font(name=FONT, bold=True)
    ws["A4"], ws["C4"] = "Số tuần thực học / năm", WEEKS_PER_YEAR
    ws["A5"], ws["C5"] = "Định mức tiết dạy / tuần của một giáo viên", PERIOD_QUOTA
    for ref in ("A4", "A5"):
        ws[ref].font = Font(name=FONT)
    for ref in ("C4", "C5"):
        body(ws[ref], center=True, blue=True)
    ws["C4"].comment = Comment(
        "Giả định dùng để tính tiết/tuần = tiết/năm ÷ số tuần. "
        "Đối chiếu kế hoạch năm học của trường.",
        "build_12_lop.py",
    )
    ws["C5"].comment = Comment(
        "Giả định 17 tiết/tuần cho giáo viên THPT; chưa trừ tiết giảm cho GVCN hay kiêm nhiệm. "
        "Đối chiếu quy định chế độ làm việc giáo viên hiện hành.",
        "build_12_lop.py",
    )
    lines = [
        "",
        "Các sheet",
        f"• Giáo viên — {teacher_count} giáo viên, đủ 17 môn. Đúng định dạng để nhập: Tài khoản → "
        "Nhập giáo viên từ tệp (hệ thống đọc sheet đầu tiên). Cột Vai trò ghi 'Giáo viên <môn>'.",
        "• Phân công — 36 lớp × 17 môn: ô ghi giáo viên dạy; ô xám là môn lớp không học (môn lựa "
        "chọn ngoài tổ hợp). Cột cuối là GVCN.",
        "• Lớp — khối, tổ hợp môn lựa chọn, GVCN và môn của GVCN.",
        "• Môn học — tiết/năm (sửa được), tiết/tuần, số lớp học, số giáo viên, tiết trung bình/GV.",
        "• Tải giảng dạy — số lớp, tiết/tuần của từng giáo viên so với định mức (công thức).",
        "",
        "Cách chia",
        "• 36 lớp: 10A1–10A12, 11A1–11A12, 12A1–12A12. Mỗi lớp 8 môn bắt buộc + 4 môn lựa "
        "chọn theo 3 tổ hợp quay vòng (4 lớp/tổ hợp/khối), giống dữ liệu seed của hệ thống.",
        "• Một giáo viên dạy tối đa ⌊định mức ÷ tiết/tuần của môn⌋ lớp; số giáo viên của môn = "
        "⌈số lớp học môn ÷ số lớp tối đa⌉; các lớp chia đều, liền nhau theo thứ tự lớp.",
        "• GVCN: mỗi lớp một người, chọn trong giáo viên đang dạy lớp đó (ưu tiên Ngữ văn, Toán, "
        "Tiếng Anh…), mỗi người chủ nhiệm tối đa một lớp.",
        "",
        "Lưu ý",
        "• Họ tên và email đều GIẢ (@thpt-demo.local). Không dùng cho dữ liệu thật.",
        "• Hệ thống hiện chỉ nhập được danh sách giáo viên từ tệp. Phân công và GVCN cần gán trên "
        "giao diện (Năm học & lớp → từng lớp), dùng sheet Phân công / Lớp làm bảng tra.",
        "• 'Giáo viên <môn>' chỉ là nhãn; quyền nhập điểm vẫn theo phân công lớp–môn.",
        "• Sinh lại tệp: PYTHONPATH=backend:. python data/samples/build_12_lop.py",
    ]
    for offset, text in enumerate(lines, start=6):
        cell = ws.cell(row=offset, column=1, value=text)
        cell.font = Font(name=FONT, bold=text in {"Các sheet", "Cách chia", "Lưu ý"})
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 4
    ws.column_dimensions["C"].width = 12
    return "'Hướng dẫn'!$C$4", "'Hướng dẫn'!$C$5"


def sheet_assignments(
    ws: Worksheet,
    assignment: dict[tuple[str, str], Teacher],
) -> str:
    """Ma trận lớp × môn. Trả dải ô giáo viên (mọi lớp × mọi môn) để các sheet khác đếm."""
    ws.title = "Phân công"
    first_subject_col = 3
    last_subject_col = first_subject_col + len(SUBJECTS) - 1
    homeroom_col = last_subject_col + 1
    title(
        ws,
        "Phân công giảng dạy: 36 lớp × 17 môn",
        "Ô ghi giáo viên dạy lớp–môn đó. Ô xám: lớp không học môn này (môn lựa chọn ngoài tổ hợp). "
        "Cột GVCN lấy từ sheet Lớp.",
        homeroom_col,
    )
    header_row = 4
    style_header(ws.cell(row=header_row, column=1, value="Khối"))
    style_header(ws.cell(row=header_row, column=2, value="Lớp"))
    for offset, subject in enumerate(SUBJECTS):
        style_header(ws.cell(row=header_row, column=first_subject_col + offset, value=subject.name))
    style_header(ws.cell(row=header_row, column=homeroom_col, value="GVCN"))
    ws.row_dimensions[header_row].height = 48

    first_row = header_row + 1
    for row, (grade, index, class_name) in enumerate(class_names(), start=first_row):
        body(ws.cell(row=row, column=1, value=grade), center=True)
        body(ws.cell(row=row, column=2, value=class_name), center=True)
        studied = class_subjects(index)
        for offset, subject in enumerate(SUBJECTS):
            cell = ws.cell(row=row, column=first_subject_col + offset)
            teacher = assignment.get((class_name, subject.name))
            if teacher:
                cell.value = teacher.name
            body(cell)
            if subject not in studied:
                cell.fill = NOT_STUDIED_FILL
        cell = ws.cell(
            row=row,
            column=homeroom_col,
            value=f'=IFERROR(INDEX(Lớp!$E$5:$E$40,MATCH(B{row},Lớp!$C$5:$C$40,0)),"")',
        )
        body(cell)
        cell.font = Font(name=FONT, color="008000")
    last_row = first_row + len(class_names()) - 1

    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 8
    for col in range(first_subject_col, homeroom_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 17
    ws.freeze_panes = ws.cell(row=first_row, column=first_subject_col)
    first, last = get_column_letter(first_subject_col), get_column_letter(last_subject_col)
    return f"'Phân công'!${first}${first_row}:${last}${last_row}"


def teacher_col(col: str, teacher_count: int) -> str:
    """Dải một cột của sheet Giáo viên, giới hạn đúng số dòng (tránh tham chiếu cả cột)."""
    return f"'Giáo viên'!${col}$2:${col}${teacher_count + 1}"


def sheet_classes(ws: Worksheet, homeroom: dict[str, Teacher], teacher_count: int) -> None:
    ws.title = "Lớp"
    title(
        ws, "Danh sách lớp, tổ hợp môn lựa chọn và GVCN", "Môn của GVCN tra từ sheet Giáo viên.", 7
    )
    headers = ("STT", "Khối", "Lớp", "Tổ hợp môn lựa chọn", "GVCN", "Môn của GVCN", "Số môn học")
    for col, text in enumerate(headers, start=1):
        style_header(ws.cell(row=4, column=col, value=text))
    for n, (grade, index, class_name) in enumerate(class_names(), start=1):
        row = 4 + n
        combo = ELECTIVE_COMBOS[(index - 1) % len(ELECTIVE_COMBOS)]
        values = (n, grade, class_name, ", ".join(combo), homeroom[class_name].name)
        for col, value in enumerate(values, start=1):
            body(ws.cell(row=row, column=col, value=value), center=col <= 3)
        role = ws.cell(
            row=row,
            column=6,
            value=(
                f"=IFERROR(INDEX({teacher_col('C', teacher_count)},"
                f'MATCH(E{row},{teacher_col("A", teacher_count)},0)),"")'
            ),
        )
        body(role)
        role.font = Font(name=FONT, color="008000")
        # Số môn của lớp = số ô có giáo viên trên dòng của lớp trong sheet Phân công (hai sheet liệt
        # kê lớp cùng thứ tự, cùng dòng bắt đầu nên dòng trùng nhau).
        first, last = SUBJECT_COLS
        count = ws.cell(row=row, column=7, value=f"=COUNTA('Phân công'!{first}{row}:{last}{row})")
        body(count, center=True)
    for col, width in zip("ABCDEFG", (6, 7, 8, 52, 24, 40, 11), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A5"


def sheet_subjects(ws: Worksheet, weeks: str, teacher_count: int) -> tuple[str, str]:
    """Trả dải tên môn và dải tiết/tuần để sheet Tải giảng dạy tra."""
    ws.title = "Môn học"
    title(
        ws,
        "17 môn THPT (Chương trình GDPT 2018) và nhu cầu giáo viên",
        "Tiết/năm (chữ xanh) lấy theo dữ liệu seed của hệ thống, cần đối chiếu kế hoạch giáo dục "
        "của trường; các cột còn lại là công thức.",
        10,
    )
    headers = (
        "STT", "Môn", "Đánh giá", "Loại", "Tiết/năm", "Tiết/tuần", "Số lớp học",
        "Tổng tiết/tuần", "Số giáo viên", "TB tiết/tuần/GV",
    )  # fmt: skip
    for col, text in enumerate(headers, start=1):
        style_header(ws.cell(row=4, column=col, value=text))
    first = 5
    for n, subject in enumerate(SUBJECTS, start=1):
        row = 4 + n
        body(ws.cell(row=row, column=1, value=n), center=True)
        body(ws.cell(row=row, column=2, value=subject.name))
        kind = "Cho điểm" if subject.assessment_type.value == "score" else "Nhận xét"
        body(ws.cell(row=row, column=3, value=kind), center=True)
        body(
            ws.cell(row=row, column=4, value="Lựa chọn" if subject.is_elective else "Bắt buộc"),
            center=True,
        )
        body(ws.cell(row=row, column=5, value=subject.periods_per_year), center=True, blue=True)
        formulas = (
            f"=E{row}/{weeks}",
            # Cột của môn trong sheet Phân công: cùng thứ tự SUBJECTS, bắt đầu từ cột C.
            f"=COUNTA('Phân công'!${get_column_letter(2 + n)}$5:${get_column_letter(2 + n)}$40)",
            f"=F{row}*G{row}",
            f'=COUNTIF({teacher_col("C", teacher_count)},"Giáo viên "&B{row})',
            f"=IFERROR(H{row}/I{row},0)",
        )
        for col, formula in enumerate(formulas, start=6):
            body(ws.cell(row=row, column=col, value=formula), center=True, number="0.0")
        ws.cell(row=row, column=7).number_format = "0"
        ws.cell(row=row, column=9).number_format = "0"
    last = first + len(SUBJECTS) - 1
    total = last + 1
    body(ws.cell(row=total, column=2, value="Tổng"))
    ws.cell(row=total, column=2).font = Font(name=FONT, bold=True)
    for col, fmt in ((7, "0"), (8, "0.0"), (9, "0")):
        letter = get_column_letter(col)
        cell = ws.cell(row=total, column=col, value=f"=SUM({letter}{first}:{letter}{last})")
        body(cell, center=True, number=fmt)
        cell.font = Font(name=FONT, bold=True)
    for col, width in zip("ABCDEFGHIJ", (6, 34, 11, 11, 10, 10, 11, 14, 13, 15), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A5"
    return f"'Môn học'!$B${first}:$B${last}", f"'Môn học'!$F${first}:$F${last}"


def sheet_load(
    ws: Worksheet,
    teachers: list[Teacher],
    quota: str,
    assign_data: str,
    subject_names: str,
    subject_weekly: str,
) -> None:
    ws.title = "Tải giảng dạy"
    title(
        ws,
        "Tải giảng dạy của từng giáo viên",
        "Số lớp đếm từ sheet Phân công; tiết/tuần = số lớp × tiết/tuần của môn; so với định mức ở "
        "sheet Hướng dẫn (chưa trừ tiết giảm cho GVCN).",
        9,
    )
    headers = (
        "STT", "Họ và tên", "Môn", "Số lớp dạy", "Tiết/tuần", "Định mức", "Còn trống (tiết)",
        "GVCN lớp", "Kiểm tra",
    )  # fmt: skip
    for col, text in enumerate(headers, start=1):
        style_header(ws.cell(row=4, column=col, value=text))
    for n, t in enumerate(teachers, start=1):
        row = 4 + n
        body(ws.cell(row=row, column=1, value=n), center=True)
        body(ws.cell(row=row, column=2, value=t.name))
        body(ws.cell(row=row, column=3, value=t.subject.name))
        formulas = (
            (f"=COUNTIF({assign_data},B{row})", "0"),
            (f"=D{row}*INDEX({subject_weekly},MATCH(C{row},{subject_names},0))", "0.0"),
            (f"={quota}", "0"),
            (f"=F{row}-E{row}", "0.0"),
            (f'=IFERROR(INDEX(Lớp!$C$5:$C$40,MATCH(B{row},Lớp!$E$5:$E$40,0)),"")', None),
            (f'=IF(E{row}>F{row},"Vượt định mức","Đạt")', None),
        )
        for col, (formula, fmt) in enumerate(formulas, start=4):
            body(ws.cell(row=row, column=col, value=formula), center=True, number=fmt)
    for col, width in zip("ABCDEFGHI", (6, 24, 34, 11, 10, 10, 15, 10, 15), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:I{4 + len(teachers)}"


def build() -> Path:
    teachers, assignment, homeroom = build_plan()
    wb = Workbook()
    sheet_teachers(wb.active, teachers)  # phải là sheet đầu: trình nhập đọc sheet_name=0
    weeks, quota = sheet_guide(wb.create_sheet("Hướng dẫn"), len(teachers))
    assign_data = sheet_assignments(wb.create_sheet(), assignment)
    sheet_classes(wb.create_sheet(), homeroom, len(teachers))
    names, weekly = sheet_subjects(wb.create_sheet(), weeks, len(teachers))
    sheet_load(wb.create_sheet(), teachers, quota, assign_data, names, weekly)
    # openpyxl không lưu giá trị đã tính: yêu cầu Excel tính lại toàn bộ khi mở tệp.
    wb.calculation.fullCalcOnLoad = True
    wb.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"Đã ghi {path}")
