"""Xuất tài liệu đặc tả Markdown sang Word (.docx) bằng python-docx.

Hỗ trợ tập con Markdown dùng trong SRS: tiêu đề #/##/###, bảng (ô có `<br>` thành nhiều dòng),
danh sách, **đậm**, `mã`, [liên kết], hình `![chú thích](đường dẫn)` (chèn ảnh, chú thích bên dưới),
dòng `<!-- toc -->` (chèn mục lục tự động). Chạy từ thư mục gốc repo:

    python docs/diagrams/build_docx.py docs/SRS.md docs/SRS.docx
    python docs/diagrams/build_docx.py docs/tai-lieu-dac-ta.md docs/tai-lieu-dac-ta.docx
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
MAX_W_CM, MAX_H_CM = 16.5, 21.5
FONT = "Times New Roman"
MONO = "Consolas"

STATUS = {"✅": "Đã làm", "🟡": "Một phần", "⬜": "Chưa làm", "✓": "Có", "✗": "Không"}
LEGEND = (
    "**Ký hiệu trạng thái:** Đã làm = đã làm và có test · Một phần = đã làm một phần hoặc còn "
    "hạn chế đã biết · Chưa làm = chưa làm."
)


def clean(text: str) -> str:
    for sym, word in STATUS.items():
        text = text.replace(sym, word)
    return text


def set_font(run, name=FONT, size=None, bold=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = color


TOKEN = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def add_inline(paragraph, text: str, size: float, bold: bool = False) -> None:
    text = clean(text).replace("&#91;", "[")
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            set_font(paragraph.add_run(part[2:-2]), size=size, bold=True)
        elif part.startswith("`") and part.endswith("`"):
            set_font(paragraph.add_run(part[1:-1]), name=MONO, size=size - 1, bold=bold,
                     color=RGBColor(0x8A, 0x1C, 0x1C))
        elif part.startswith("["):
            label = re.match(r"\[([^\]]+)\]", part).group(1)
            set_font(paragraph.add_run(label), size=size, bold=bold)
        else:
            set_font(paragraph.add_run(part), size=size, bold=bold)


def shade(cell, fill: str) -> None:
    tcpr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def repeat_header(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trpr.append(el)


def split_row(line: str) -> list[str]:
    inner = line.strip().strip("|")
    cells, buf, in_code = [], "", False
    for ch in inner:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(buf.strip())
            buf = ""
        else:
            buf += ch
    cells.append(buf.strip())
    return cells


def add_table(doc, rows: list[list[str]]) -> None:
    header, body = rows[0], rows[1:]
    ncols = len(header)
    table = doc.add_table(rows=0, cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, values in enumerate([header, *body]):
        cells = table.add_row().cells
        for col in range(ncols):
            value = values[col] if col < len(values) else ""
            cell = cells[col]
            for line_no, line in enumerate(value.split("<br>")):
                p = cell.paragraphs[0] if line_no == 0 else cell.add_paragraph()
                p.paragraph_format.space_after = Pt(1)
                add_inline(p, line.strip(), 10, bold=index == 0)
            if index == 0:
                shade(cell, "D9E2F3")
        if index == 0:
            repeat_header(table.rows[0])
    # Mỗi cột: tối thiểu đủ chứa từ dài nhất (cm), phần còn lại chia theo độ dài chữ trung bình.
    mins, avgs = [], []
    for col in range(ncols):
        texts = [
            clean(r[col]).replace("`", "").replace("*", "").replace("<br>", " ")
            for r in rows
            if col < len(r)
        ]
        longest_word = max((len(w) for t in texts for w in t.split()), default=4)
        mins.append(max(1.4, min(longest_word, 22) * 0.21 + 0.45))
        avgs.append(max(1.0, sum(len(t) for t in texts) / len(texts)))
    spare = max(0.0, 17 - sum(mins))
    widths_cm = [m + spare * a / sum(avgs) for m, a in zip(mins, avgs)]
    weights = widths_cm
    total = sum(weights)
    table.autofit = False
    tblpr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    for col, weight in enumerate(weights):
        width = Cm(17 * weight / total)
        table.columns[col].width = width
        for cell in table.columns[col].cells:
            cell.width = width
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_field(run, instruction: str, placeholder: str = "") -> None:
    """Chèn một trường Word (PAGE, TOC…) vào `run`; `placeholder` hiện tới khi trường được cập nhật."""
    parts = [("begin", None), (None, instruction), ("separate", None)]
    for tag, text in [*parts, ("text", placeholder), ("end", None)]:
        if tag == "text":
            el = OxmlElement("w:t")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        elif tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def add_page_number(section) -> None:
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    add_field(run, "PAGE")
    set_font(run, size=10)


def add_toc(doc) -> None:
    """Mục lục tự động (Heading 1–2) trên trang riêng; Word hỏi cập nhật trường khi mở tệp."""
    title = doc.add_paragraph()
    add_inline(title, "Mục lục", 15, bold=True)
    run = doc.add_paragraph().add_run()
    add_field(run, 'TOC \\o "1-2" \\h \\z \\u', "Mở tệp trong Word và chọn Có để cập nhật mục lục.")
    set_font(run, size=12)
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    doc.settings.element.append(update)
    doc.add_page_break()


def add_image(doc, caption: str, path: Path) -> None:
    """Chèn ảnh căn giữa, vừa trang (rộng tối đa 16,5 cm, cao tối đa 21,5 cm), chú thích ở dưới."""
    with Image.open(path) as im:
        w_px, h_px = im.size
    width = MAX_W_CM
    if width * h_px / w_px > MAX_H_CM:
        width = MAX_H_CM * w_px / h_px
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(6)
    p.add_run().add_picture(str(path), width=Cm(width))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(10)
    run = cap.add_run(caption)
    set_font(run, size=11)
    run.italic = True


def main() -> None:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin"):
        setattr(section, side, Cm(2))
    section.top_margin = section.bottom_margin = Cm(2)
    add_page_number(section)

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15
    for name, size, before in (("Title", 20, 0), ("Heading 1", 15, 14), ("Heading 2", 13, 10)):
        style = doc.styles[name]
        style.font.name = FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
        style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True

    lines = SRC.read_text(encoding="utf-8").splitlines()
    title = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped == "---":
            i += 1
            continue
        if stripped.startswith("<!--"):
            # Chú thích HTML không hiện ra; riêng `<!-- toc -->` là chỗ đặt mục lục.
            if stripped == "<!-- toc -->":
                add_toc(doc)
            i += 1
            continue
        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.fullmatch(r"\|[\s:|-]+\|", lines[i].strip()):
                    block.append(split_row(lines[i]))
                i += 1
            add_table(doc, block)
            continue
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image:
            add_image(doc, image.group(1), SRC.parent / image.group(2))
            i += 1
            continue
        if re.fullmatch(r"\*\*Bảng [^*]+\*\*", stripped):
            # Tên bảng đặc tả: đặt ngay trên bảng, không tách trang.
            p = doc.add_paragraph()
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.space_before = Pt(8)
            add_inline(p, stripped, 12)
            i += 1
            continue
        if stripped.startswith("# "):
            title = title or stripped[2:]
            p = doc.add_paragraph(style="Title")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_inline(p, stripped[2:], 20, bold=True)
        elif stripped.startswith("## "):
            p = doc.add_paragraph(style="Heading 1")
            add_inline(p, stripped[3:], 15, bold=True)
        elif stripped.startswith("### "):
            p = doc.add_paragraph(style="Heading 2")
            add_inline(p, stripped[4:], 13, bold=True)
        elif re.match(r"^\s*- ", line):
            level = 2 if len(line) - len(line.lstrip()) >= 2 else 1
            p = doc.add_paragraph(style="List Bullet" if level == 1 else "List Bullet 2")
            add_inline(p, stripped[2:], 12)
        elif re.match(r"^\d+\. ", stripped):
            p = doc.add_paragraph(style="List Number")
            add_inline(p, re.sub(r"^\d+\. ", "", stripped), 12)
        else:
            if stripped.startswith("**Ký hiệu trạng thái:**"):
                stripped = LEGEND
            p = doc.add_paragraph()
            add_inline(p, stripped, 12)
        i += 1

    doc.core_properties.title = title
    doc.core_properties.author = "Duong"
    doc.save(OUT)
    print(f"Đã ghi {OUT}")


if __name__ == "__main__":
    main()
