"""Vẽ các sơ đồ Mermaid (docs/diagrams/src/*.mmd) thành PNG trong docs/diagrams/png/.

Dùng Chrome chạy ẩn và một tệp `mermaid.min.js` có sẵn trên máy (không tải gì từ mạng). Đường dẫn
mặc định là bản đi kèm extension "Markdown Preview Enhanced" của VS Code; đổi bằng biến môi trường
MERMAID_JS, CHROME. Chạy từ thư mục gốc repo:

    python docs/diagrams/render_mermaid.py            # vẽ tất cả
    python docs/diagrams/render_mermaid.py sd-01-dang-nhap   # chỉ một sơ đồ
"""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "src", HERE / "png"
CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEFAULT_JS = next(
    iter(
        sorted(
            (Path.home() / ".vscode" / "extensions").glob(
                "shd101wyy.markdown-preview-enhanced-*/crossnote/dependencies/mermaid/mermaid.min.js"
            )
        )
    ),
    None,
)
MERMAID_JS = Path(os.environ.get("MERMAID_JS", str(DEFAULT_JS or "")))

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;padding:24px;background:#fff}}</style>
<script src="mermaid.min.js"></script></head><body>
<pre class="mermaid">{src}</pre>
<script>
mermaid.initialize({{startOnLoad:true, theme:'neutral', securityLevel:'strict',
  themeVariables:{{fontFamily:'Times New Roman', fontSize:'17px'}},
  flowchart:{{htmlLabels:true, curve:'basis', useMaxWidth:false, wrappingWidth:300,
    nodeSpacing:40, rankSpacing:38}},
  sequence:{{mirrorActors:false, useMaxWidth:false, wrap:true, width:170}},
  er:{{useMaxWidth:false}}, state:{{useMaxWidth:false}}}});
</script></body></html>"""


def trim(path: Path, pad: int = 24) -> None:
    image = Image.open(path).convert("RGB")
    box = ImageChops.difference(image, Image.new("RGB", image.size, "white")).getbbox()
    if box:
        left, top, right, bottom = box
        image = image.crop((max(0, left - pad), max(0, top - pad),
                            min(image.width, right + pad), min(image.height, bottom + pad)))
    image.save(path)


def render(source: Path, target: Path, width: int = 3400, height: int = 4200) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy(MERMAID_JS, work / "mermaid.min.js")
        page = work / "page.html"
        page.write_text(PAGE.format(src=html.escape(source.read_text(encoding="utf-8"))),
                        encoding="utf-8")
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={work / 'profile'}", "--allow-file-access-from-files",
             "--force-device-scale-factor=2", f"--window-size={width},{height}",
             "--virtual-time-budget=10000", f"--screenshot={target}", page.as_uri()],
            check=True, capture_output=True, timeout=180,
        )
    trim(target)


def main() -> int:
    if not MERMAID_JS.is_file():
        print("Không thấy mermaid.min.js; đặt biến môi trường MERMAID_JS.", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for source in sorted(SRC.glob("*.mmd")):
        if only and source.stem not in only:
            continue
        target = OUT / f"{source.stem}.png"
        render(source, target)
        with Image.open(target) as image:
            print(f"{source.stem}: {image.size[0]}x{image.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
