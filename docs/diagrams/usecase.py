"""Vẽ các sơ đồ use case (UML) của SRS bằng matplotlib: tác nhân hình người, use case hình elip,
khung hệ thống, quan hệ liên kết, «include», «extend» và kế thừa tác nhân.

Mermaid không có sơ đồ use case nên phần này vẽ riêng. Chạy từ thư mục gốc repo:
    python docs/diagrams/usecase.py            # ghi docs/diagrams/png/uc-*.png
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse, FancyArrowPatch, Rectangle  # noqa: E402

OUT = Path(__file__).resolve().parent / "png"
plt.rcParams["font.family"] = "Times New Roman"
LINE = "#333333"
UC_FILL = "#EEF3FB"
BOX = "#5B7DB1"


@dataclass
class Actor:
    key: str
    label: str
    x: float
    y: float


@dataclass
class UseCase:
    key: str
    label: str
    x: float
    y: float
    w: float = 3.4
    h: float = 0.95


@dataclass
class Diagram:
    name: str
    size: tuple[float, float]
    boundary: tuple[float, float, float, float] | None  # x, y, w, h của khung hệ thống
    system: str
    actors: list[Actor]
    cases: list[UseCase] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # tác nhân -> use case
    includes: list[tuple[str, str]] = field(default_factory=list)  # gốc -> được gộp
    extends: list[tuple[str, str]] = field(default_factory=list)  # mở rộng -> gốc
    generalize: list[tuple[str, str]] = field(default_factory=list)  # con -> cha
    y0: float = 0.0  # cắt bỏ phần trống phía dưới


def draw_actor(ax, actor: Actor) -> None:
    x, y = actor.x, actor.y
    ax.add_patch(Rectangle((x - 0.45, y - 0.5), 0.9, 1.25, fc="white", ec="none", zorder=4))
    ax.add_patch(plt.Circle((x, y + 0.55), 0.16, fill=False, lw=1.4, color=LINE, zorder=5))
    for xs, ys in (
        ([x, x], [y + 0.39, y - 0.05]),
        ([x - 0.3, x + 0.3], [y + 0.25, y + 0.25]),
        ([x, x - 0.25], [y - 0.05, y - 0.45]),
        ([x, x + 0.25], [y - 0.05, y - 0.45]),
    ):
        ax.plot(xs, ys, color=LINE, lw=1.4, zorder=5)
    ax.text(x, y - 0.62, actor.label, ha="center", va="top", fontsize=11, zorder=5,
            bbox={"fc": "white", "ec": "none", "pad": 1})


def edge_point(case: UseCase, tx: float, ty: float) -> tuple[float, float]:
    """Giao điểm của đoạn từ tâm elip tới (tx, ty) với viền elip."""
    dx, dy = tx - case.x, ty - case.y
    if dx == 0 and dy == 0:
        return case.x, case.y
    a, b = case.w / 2, case.h / 2
    t = 1 / math.sqrt((dx / a) ** 2 + (dy / b) ** 2)
    return case.x + dx * t, case.y + dy * t


def actor_anchor(actor: Actor, tx: float) -> tuple[float, float]:
    return (actor.x + (0.35 if tx > actor.x else -0.35), actor.y + 0.15)


def draw_generalization(ax, child: Actor, parent: Actor) -> None:
    """Đường liền, đầu tam giác rỗng chỉ vào tác nhân cha (ký hiệu kế thừa UML)."""
    x1, y1, x2, y2 = child.x, child.y + 0.8, parent.x, parent.y - 1.15
    ang = math.atan2(y2 - y1, x2 - x1)
    size, half = 0.32, 0.17
    bx, by = x2 - size * math.cos(ang), y2 - size * math.sin(ang)
    ax.plot([x1, bx], [y1, by], color=LINE, lw=1.2, zorder=3)
    tri = [
        (x2, y2),
        (bx + half * math.sin(ang), by - half * math.cos(ang)),
        (bx - half * math.sin(ang), by + half * math.cos(ang)),
    ]
    ax.add_patch(plt.Polygon(tri, closed=True, fc="white", ec=LINE, lw=1.2, zorder=3))


def render(d: Diagram) -> Path:
    fig, ax = plt.subplots(figsize=(d.size[0], d.size[1] - d.y0))
    ax.set_xlim(0, d.size[0])
    ax.set_ylim(d.y0, d.size[1])
    ax.set_aspect("equal")
    ax.axis("off")
    if d.boundary:
        bx, by, bw, bh = d.boundary
        ax.add_patch(Rectangle((bx, by), bw, bh, fill=False, lw=1.3, color=BOX, zorder=0))
        ax.text(bx + bw / 2, by + bh - 0.2, d.system, ha="center", va="top", fontsize=13,
                fontweight="bold", color=BOX, zorder=6)
    actors = {a.key: a for a in d.actors}
    cases = {c.key: c for c in d.cases}

    # Kế thừa kiểu cây: một tam giác dưới mỗi tác nhân cha, các con nối vào một thanh ngang.
    children: dict[str, list[str]] = {}
    for child, parent in d.generalize:
        children.setdefault(parent, []).append(child)
    for parent_key, kids in children.items():
        parent = actors[parent_key]
        tip_y = parent.y - 1.15
        base_y = tip_y - 0.3
        ax.add_patch(plt.Polygon([(parent.x, tip_y), (parent.x - 0.17, base_y),
                                  (parent.x + 0.17, base_y)], closed=True, fc="white",
                                 ec=LINE, lw=1.2, zorder=3))
        bar_y = base_y - 0.25
        ax.plot([parent.x, parent.x], [base_y, bar_y], color=LINE, lw=1.2, zorder=3)
        xs = [actors[k].x for k in kids] + [parent.x]
        ax.plot([min(xs), max(xs)], [bar_y, bar_y], color=LINE, lw=1.2, zorder=3)
        for k in kids:
            kid = actors[k]
            ax.plot([kid.x, kid.x], [bar_y, kid.y + 0.75], color=LINE, lw=1.2, zorder=3)
    for actor_key, case_key in d.links:
        a, c = actors[actor_key], cases[case_key]
        start = actor_anchor(a, c.x)
        end = edge_point(c, *start)
        ax.plot([start[0], end[0]], [start[1], end[1]], color=LINE, lw=1.0, zorder=1)
    for kind, pairs in (("include", d.includes), ("extend", d.extends)):
        for src, dst in pairs:
            s, t = cases[src], cases[dst]
            p1, p2 = edge_point(s, t.x, t.y), edge_point(t, s.x, s.y)
            ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="->,head_length=6,head_width=3",
                                         mutation_scale=1.6, lw=1.0, ls=(0, (4, 3)),
                                         color="#555555", zorder=2))
            ax.text((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + 0.12, f"«{kind}»",
                    ha="center", va="bottom", fontsize=9, style="italic", color="#555555",
                    bbox={"fc": "white", "ec": "none", "pad": 0.5}, zorder=7)
    for c in d.cases:
        ax.add_patch(Ellipse((c.x, c.y), c.w, c.h, fc=UC_FILL, ec=BOX, lw=1.2, zorder=5))
        ax.text(c.x, c.y, c.label, ha="center", va="center", fontsize=10.5, zorder=6)
    for a in d.actors:
        draw_actor(ax, a)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{d.name}.png"
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# --- Các sơ đồ ---------------------------------------------------------------------------------

ACTORS = Diagram(
    name="uc-00-tac-nhan",
    size=(11, 7.6),
    boundary=None,
    system="",
    actors=[
        Actor("user", "Người dùng", 5.5, 6.5),
        Actor("gv", "Giáo viên", 2.6, 3.5),
        Actor("bgh", "Ban giám hiệu", 5.5, 3.5),
        Actor("admin", "Quản trị viên", 8.4, 3.5),
        Actor("gvbm", "Giáo viên bộ môn\n(theo phân công)", 1.2, 0.5),
        Actor("gvcn", "Giáo viên chủ nhiệm\n(theo lớp được gán)", 4.0, 0.5),
    ],
    generalize=[("gv", "user"), ("bgh", "user"), ("admin", "user"), ("gvbm", "gv"),
                ("gvcn", "gv")],
)

OVERVIEW = Diagram(
    name="uc-01-tong-quat",
    size=(17, 15.2),
    boundary=(3.3, 0.4, 10.8, 14.5),
    system="Hệ thống quản lý lớp học THPT",
    actors=[
        Actor("user", "Người dùng", 1.3, 13.7),
        Actor("gv", "Giáo viên\n(GVBM, GVCN)", 1.3, 8.0),
        Actor("llm", "Dịch vụ LLM\n(hệ thống ngoài)", 15.7, 13.2),
        Actor("bgh", "Ban giám hiệu", 15.7, 8.0),
        Actor("admin", "Quản trị viên", 15.7, 2.6),
    ],
    cases=[
        UseCase("login", "UC01 Đăng nhập,\nđổi mật khẩu", 5.6, 14.05),
        UseCase("year", "UC02 Chọn năm học\nđể xem", 5.6, 13.0),
        UseCase("import", "UC03 Nhập điểm\ntừ tệp", 5.2, 11.85),
        UseCase("edit", "UC04 Sửa / nhập tay\nđiểm", 6.2, 10.75),
        UseCase("att", "UC06 Nhập điểm danh,\nrèn luyện", 5.6, 5.3),
        UseCase("ai", "UC09 Hỏi trợ lý AI", 9.2, 10.1, h=0.85),
        UseCase("report", "UC10 Sinh, duyệt\nnhận xét / báo cáo", 9.2, 9.05, h=0.85),
        UseCase("scores", "UC05 Xem bảng điểm\nmôn", 9.2, 8.0, h=0.85),
        UseCase("dash", "UC07 Xem dashboard lớp,\nhồ sơ học sinh", 9.2, 6.95, w=3.8,
                h=0.85),
        UseCase("alert", "UC08 Xem, xử lý\ncảnh báo sớm", 9.2, 5.9, h=0.85),
        UseCase("grade", "UC11 So sánh khối,\ncảnh báo toàn trường", 12.6, 10.0, w=3.0),
        UseCase("users", "UC12 Quản lý\ntài khoản", 10.6, 4.3),
        UseCase("school", "UC13 Quản lý năm học,\nlớp, phân công", 10.6, 3.25, w=3.6),
        UseCase("roster", "UC14 Nhập danh sách\nhọc sinh", 10.6, 2.2),
        UseCase("reg", "UC15 Quản lý văn bản\nquy định", 10.6, 1.15),
    ],
    links=[
        ("user", "login"), ("user", "year"),
        ("gv", "import"), ("gv", "edit"), ("gv", "att"), ("gv", "ai"), ("gv", "report"),
        ("gv", "scores"), ("gv", "dash"), ("gv", "alert"),
        ("bgh", "ai"), ("bgh", "report"), ("bgh", "scores"), ("bgh", "dash"), ("bgh", "alert"),
        ("bgh", "grade"),
        ("admin", "users"), ("admin", "school"), ("admin", "roster"), ("admin", "reg"),
        ("llm", "ai"), ("llm", "report"),
    ],
)

TEACHER = Diagram(
    name="uc-02-diem-va-nhap-lieu",
    size=(16.5, 13.1),
    boundary=(3.4, 0.4, 12.6, 12.5),
    system="Phân hệ điểm và nhập dữ liệu",
    actors=[
        Actor("gvbm", "Giáo viên\nbộ môn", 1.4, 9.2),
        Actor("gvcn", "Giáo viên\nchủ nhiệm", 1.4, 3.6),
    ],
    cases=[
        UseCase("import", "Nhập điểm từ tệp", 6.0, 11.0),
        UseCase("preview", "Xem trước,\nkiểm lỗi từng dòng", 10.4, 11.4),
        UseCase("map", "Chọn / lưu mẫu\nánh xạ cột", 14.2, 10.6, w=3.0),
        UseCase("confirm", "Xác nhận ghi\ndữ liệu", 10.4, 10.0),
        UseCase("edit", "Sửa / nhập tay điểm\nmột học sinh", 6.0, 8.6),
        UseCase("reason", "Chọn lý do,\nghi chú", 10.4, 8.6),
        UseCase("history", "Xem lịch sử\nsửa điểm", 10.4, 7.3),
        UseCase("scores", "Xem bảng điểm môn", 6.0, 6.2),
        UseCase("filter", "Lọc học sinh theo\nkhoảng điểm", 10.4, 5.9),
        UseCase("att", "Nhập điểm danh\ntừ tệp", 6.0, 3.6),
        UseCase("conduct", "Nhập rèn luyện\ntừ tệp", 6.0, 2.1),
        UseCase("warn", "Tính lại cảnh báo\nsớm của lớp", 14.2, 8.4, w=3.0),
    ],
    links=[
        ("gvbm", "import"), ("gvbm", "edit"), ("gvbm", "scores"),
        ("gvcn", "scores"), ("gvcn", "att"), ("gvcn", "conduct"),
    ],
    includes=[
        ("import", "preview"), ("import", "confirm"), ("edit", "reason"), ("edit", "history"),
        ("confirm", "warn"),
    ],
    extends=[("map", "preview"), ("filter", "scores"), ("history", "scores")],
)

AI = Diagram(
    name="uc-03-tro-ly-va-nhan-xet",
    size=(17, 12.9),
    y0=3.9,
    boundary=(3.4, 4.2, 12.6, 8.5),
    system="Phân hệ AI",
    actors=[
        Actor("gv", "Giáo viên, BGH", 1.4, 8.2),
        Actor("llm", "Dịch vụ LLM", 16.6, 9.2),
    ],
    cases=[
        UseCase("ask", "Hỏi trợ lý AI", 6.2, 11.0),
        UseCase("anon", "Ẩn danh dữ liệu\nhọc sinh", 10.6, 11.5),
        UseCase("tools", "Gọi hàm Analytics\n(7 hàm chỉ đọc)", 10.6, 10.2),
        UseCase("rag", "Tra cứu văn bản\nquy định (RAG)", 14.1, 11.5, w=3.2),
        UseCase("rate", "Đánh giá câu trả lời\nđúng / sai", 6.2, 9.6),
        UseCase("gen", "Sinh nhận xét /\nbáo cáo nháp", 6.2, 8.2),
        UseCase("check", "Kiểm số liệu và\ntừ cấm", 10.6, 7.6),
        UseCase("gradeRep", "Báo cáo khối\n(chỉ BGH)", 10.6, 6.4),
        UseCase("editr", "Sửa bản nháp,\nsinh lại kèm góp ý", 6.2, 6.8),
        UseCase("approve", "Duyệt bản nháp", 6.2, 5.4),
        UseCase("pdf", "Xuất PDF", 10.6, 5.2),
    ],
    links=[
        ("gv", "ask"), ("gv", "rate"), ("gv", "gen"), ("gv", "editr"), ("gv", "approve"),
        ("llm", "tools"), ("llm", "gen"),
    ],
    includes=[("ask", "anon"), ("ask", "tools"), ("gen", "check")],
    extends=[("rag", "tools"), ("pdf", "approve"), ("gradeRep", "gen")],
)

ADMIN = Diagram(
    name="uc-04-quan-tri",
    size=(15.5, 12.5),
    boundary=(3.4, 0.4, 11.6, 11.7),
    system="Phân hệ quản trị",
    actors=[Actor("admin", "Quản trị viên", 1.4, 6.2)],
    cases=[
        UseCase("users", "Quản lý tài khoản", 6.2, 10.6),
        UseCase("create", "Tạo tài khoản\n(Giáo viên <môn>)", 10.6, 11.2),
        UseCase("reset", "Đặt lại mật khẩu,\nkhoá / mở khoá", 13.0, 10.0),
        UseCase("bulk", "Nhập giáo viên\ntừ tệp", 10.6, 8.9),
        UseCase("years", "Quản lý năm học", 6.2, 7.4),
        UseCase("rollover", "Tạo năm mới, chép lớp\nvà cho HS lên lớp", 10.6, 7.6, w=3.8),
        UseCase("current", "Đặt năm hiện hành", 10.6, 6.3),
        UseCase("classes", "Quản lý lớp, GVCN", 6.2, 5.0),
        UseCase("roster", "Nhập / gỡ\nhọc sinh của lớp", 10.6, 4.9),
        UseCase("assign", "Phân công giảng dạy", 6.2, 3.6),
        UseCase("copy", "Sao chép phân công\ntừ lớp khác", 10.6, 3.6),
        UseCase("reg", "Quản lý văn bản\nquy định", 6.2, 1.6),
        UseCase("embed", "Tách Điều/Khoản,\ntính vector", 10.6, 1.6),
    ],
    links=[("admin", "users"), ("admin", "years"), ("admin", "classes"), ("admin", "assign"),
           ("admin", "reg")],
    includes=[("users", "create"), ("users", "reset"), ("years", "current"), ("reg", "embed"),
              ("classes", "roster")],
    extends=[("bulk", "users"), ("rollover", "years"), ("copy", "assign")],
)

if __name__ == "__main__":
    for diagram in (ACTORS, OVERVIEW, TEACHER, AI, ADMIN):
        print(render(diagram))
