"""PDF → visually-restored HTML via local layout + remote VL OCR.

Pipeline per page:
  1. Render PDF page to PNG via pypdfium2 (avoid PP-StructureV3 PDF OOM)
  2. Local: run PPStructureV3 (table rec off, no formula/seal/orientation,
     enable_mkldnn=False to bypass paddle 3.3.1 oneDNN bug) on the PNG.
     Output: line-level bbox + OCR text.
  3. Remote: submit one PaddleOCR-VL task for the entire PDF, poll until
     SUCCEED, download results.zip with per-page md.
  4. Match local lines against VL lines (substring/overlap heuristic),
     prefer VL text. Fallback to local OCR text where no match.
  5. Emit per-page HTML with absolutely-positioned <div> per line.

Three-phase decoupled workflow:
  Phase 1 (VL only):
    python ocr_layout_to_html.py input.pdf --vl-only --work-dir /tmp/cache/

  Phase 2 (local only):
    python ocr_layout_to_html.py input.pdf --local-only --work-dir /tmp/cache/ --pages 1-5

  Phase 3 (combine):
    python ocr_layout_to_html.py input.pdf --work-dir /tmp/cache/ --output out.html

Usage:
    python scripts/ocr_layout_to_html.py input.pdf --pages 1-5 --output out.html
    python scripts/ocr_layout_to_html.py input.pdf --pages 1 --debug

Requirements:
    - venv at /home/evt/projects/KB1/.venv-paddle with paddleocr[full], mcp
    - Remote OCR service reachable at http://172.19.160.213:7779
    - Unset all_proxy / https_proxy env vars before running

Exit codes:
    0 = success
    1 = usage error / pipeline failure
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import html as html_lib
from concurrent.futures import ThreadPoolExecutor  # noqa: F401  (kept for future parallel mode)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Proxy env vars break pip/requests to the OCR service — must clear before import.
for _v in ("all_proxy", "ALL_PROXY", "https_proxy", "HTTPS_PROXY",
           "http_proxy", "HTTP_PROXY"):
    os.environ.pop(_v, None)

VENV_SITE = Path("/home/evt/projects/KB1/.venv-paddle/lib/python3.12/site-packages")
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))

OCR_BASE = "http://172.19.160.213:7779"


@dataclass
class Line:
    """One OCR'd text line with bbox (pixel coordinates, origin top-left)."""
    text: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float
    source: str = "local"  # "local" or "vl"
    block_label: str = ""  # layout region type (doc_title, text, table, etc.)


def _char_width_estimate(ch: str, font_px: int) -> float:
    """Estimate rendered width of a single character at given font size."""
    if ord(ch) > 0x2E80:  # CJK and full-width chars
        return font_px * 1.05
    if ch in "il.,;:'|!":
        return font_px * 0.35
    if ch in "mwMW":
        return font_px * 0.85
    return font_px * 0.6


def _text_width(text: str, font_px: int) -> float:
    """Estimate rendered width of a text string at given font size."""
    return sum(_char_width_estimate(c, font_px) for c in text)


def _split_overflow_lines(lines: list[Line]) -> None:
    """Split lines whose text overflows the bbox width into multiple lines.

    PP-StructureV3 sometimes returns rec_texts that span multiple physical
    lines but assigns them to a single-line bbox. This causes the rendered
    text to overflow horizontally. Here we split such lines so each piece
    fits within the original bbox width, stacking the overflow pieces below.

    When a line is split into N pieces, the (N-1) extra lines need vertical
    room. We shift all subsequent lines down by (N-1) * line_h to make room,
    preventing overlap with the next real line.
    """
    if not lines:
        return
    from dataclasses import replace

    result: list[Line] = []
    y_offset = 0  # cumulative downward shift applied to subsequent lines
    for ln in lines:
        # Apply accumulated offset to this line first
        if y_offset:
            ln = replace(ln, y1=ln.y1 + y_offset, y2=ln.y2 + y_offset)

        bbox_w = ln.x2 - ln.x1
        font_px = max(8, int(ln.y2 - ln.y1))
        text_w = _text_width(ln.text, font_px)
        # If text fits (with 10% tolerance), keep as-is
        if text_w <= bbox_w * 1.1 or not ln.text:
            result.append(ln)
            continue
        # Need to split. Greedily pack characters into pieces that fit bbox_w.
        pieces: list[str] = []
        cur = ""
        cur_w = 0.0
        for ch in ln.text:
            cw = _char_width_estimate(ch, font_px)
            if cur and cur_w + cw > bbox_w:
                pieces.append(cur)
                cur = ch
                cur_w = cw
            else:
                cur += ch
                cur_w += cw
        if cur:
            pieces.append(cur)
        # Emit each piece as a separate line, stacked vertically by font_px.
        line_h = font_px
        extra_lines = len(pieces) - 1
        for i, piece in enumerate(pieces):
            new_y1 = ln.y1 + i * line_h
            new_y2 = new_y1 + line_h
            result.append(replace(ln, text=piece, y1=new_y1, y2=new_y2))
        # Make room for the extra lines by shifting all subsequent lines down.
        if extra_lines > 0:
            y_offset += extra_lines * line_h
    lines[:] = result


@dataclass
class ImageBlock:
    """A non-text region (figure, table image) from layout detection."""
    x1: float
    y1: float
    x2: float
    y2: float
    label: str = "image"


@dataclass
class PageResult:
    page_index: int  # 0-based
    width: int
    height: int
    lines: list[Line] = field(default_factory=list)
    images: list[ImageBlock] = field(default_factory=list)


def parse_page_range(spec: str) -> list[int]:
    """Parse '1-3,5,7-9' → [0,1,2,4,6,7,8] (0-based)."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo) - 1, int(hi)))
        else:
            out.append(int(part) - 1)
    return sorted(set(out))


def render_pdf_page(pdf_path: str, page_index: int, out_png: Path,
                    scale: float = 1.5) -> tuple[int, int]:
    """Render one PDF page to PNG. Returns (width, height) of the rendered image."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_path)
    if page_index >= len(pdf):
        raise IndexError(f"page_index {page_index} >= page count {len(pdf)}")
    page = pdf[page_index]
    bitmap = page.render(scale=scale)
    img = bitmap.to_pil()
    img.save(str(out_png))
    return img.size  # (w, h)


def extract_pdf_images(pdf_path: str, page_index: int, scale: float = 1.5,
                       min_w: float = 40, min_h: float = 30) -> list[ImageBlock]:
    """Extract real image positions directly from the PDF via PyMuPDF.

    PP-StructureV3 sometimes misclassifies logos/figures as 'header'/'text'.
    This uses PyMuPDF to get the true image rects and converts PDF points to
    PNG pixel coordinates (× scale).

    Filters out tiny images (icons/symbols < min_w × min_h in PNG px).

    PyMuPDF may not be installed in the paddle venv, so we shell out to the
    system python3 which has it.
    """
    import subprocess, json as _json
    code = (
        "import sys, json, fitz\n"
        f"pdf_path = {pdf_path!r}\n"
        f"page_index = {page_index!r}\n"
        f"scale = {scale!r}\n"
        f"min_w = {min_w!r}\n"
        f"min_h = {min_h!r}\n"
        "doc = fitz.open(pdf_path)\n"
        "if page_index >= len(doc):\n"
        "    print('[]'); sys.exit(0)\n"
        "page = doc[page_index]\n"
        "out = []\n"
        "seen = set()\n"
        "for img in page.get_images(full=True):\n"
        "    xref = img[0]\n"
        "    for r in page.get_image_rects(xref):\n"
        "        x1, y1, x2, y2 = r.x0*scale, r.y0*scale, r.x1*scale, r.y1*scale\n"
        "        w, h = x2-x1, y2-y1\n"
        "        if w < min_w or h < min_h: continue\n"
        "        key = (round(x1), round(y1), round(x2), round(y2))\n"
        "        if key in seen: continue\n"
        "        seen.add(key)\n"
        "        out.append([x1, y1, x2, y2])\n"
        "doc.close()\n"
        "print(json.dumps(out))\n"
    )
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        rects = _json.loads(result.stdout.strip())
    except Exception:
        return []
    return [ImageBlock(x1=r[0], y1=r[1], x2=r[2], y2=r[3], label="image")
            for r in rects]


def merge_images(pp_images: list[ImageBlock],
                 pdf_images: list[ImageBlock]) -> list[ImageBlock]:
    """Merge PP-detected and PyMuPDF-extracted image blocks.

    PP images are kept as-is. PDF images are added only if they don't
    significantly overlap an existing PP image (avoiding duplicates).
    """
    def overlap(a: ImageBlock, b: ImageBlock) -> float:
        xo = min(a.x2, b.x2) - max(a.x1, b.x1)
        yo = min(a.y2, b.y2) - max(a.y1, b.y1)
        if xo <= 0 or yo <= 0:
            return 0
        return (xo * yo) / max((a.x2 - a.x1) * (a.y2 - a.y1), 1)

    result = list(pp_images)
    for pimg in pdf_images:
        if any(overlap(pimg, existing) > 0.3 for existing in result):
            continue
        result.append(pimg)
    result.sort(key=lambda im: (im.y1, im.x1))
    return result


# ----------------------- local PP-StructureV3 -----------------------

_pp_engine = None


def get_pp_engine():
    """Lazy singleton — PPStructureV3 takes ~5s to init, don't pay per page.

    Table recognition is DISABLED by default (peaks ~6GB RSS, triggers
    systemd-oomd on machines with <8GB RAM).  Enable with --with-tables.
    """
    global _pp_engine
    if _pp_engine is None:
        from paddleocr import PPStructureV3
        _pp_engine = PPStructureV3(
            enable_mkldnn=False,  # bypass paddle 3.3.1 oneDNN bug
            use_table_recognition=_FLAGS["with_tables"],
            use_formula_recognition=False,
            use_seal_recognition=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    return _pp_engine


# Runtime flags set from argparse before first engine init.
_FLAGS = {"with_tables": False}


def run_local_layout(png_path: Path) -> tuple[int, int, list[Line], list[ImageBlock]]:
    """Run PP-StructureV3 on a PNG. Returns (width, height, lines, images).

    Each OCR line is tagged with block_label from parsing_res_list.
    Image/figure/table blocks are returned separately for HTML embedding.
    """
    engine = get_pp_engine()
    results = list(engine.predict(str(png_path)))
    if not results:
        return 0, 0, [], []
    r = results[0]
    raw = r.json if isinstance(r.json, dict) else {}
    data = raw.get("res", raw)
    width = data.get("width", 0)
    height = data.get("height", 0)
    blocks = data.get("parsing_res_list", [])
    ocr = data.get("overall_ocr_res", {})
    polys = ocr.get("dt_polys", [])
    texts = ocr.get("rec_texts", [])
    scores = ocr.get("rec_scores", [])
    lines = []
    for poly, text, score in zip(polys, texts, scores):
        if len(poly) < 3:
            continue
        x1 = min(p[0] for p in poly)
        y1 = min(p[1] for p in poly)
        x2 = max(p[0] for p in poly)
        y2 = max(p[1] for p in poly)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        label = ""
        for blk in blocks:
            bb = blk.get("block_bbox", [])
            if len(bb) == 4 and bb[0] <= cx <= bb[2] and bb[1] <= cy <= bb[3]:
                label = blk.get("block_label", "")
                break
        lines.append(Line(text=text, score=score, x1=x1, y1=y1, x2=x2, y2=y2,
                          block_label=label))
    lines.sort(key=lambda l: (l.y1, l.x1))

    # Extract image/figure/table blocks, filtering out tiny noise (< 60x40 px)
    images = []
    for blk in blocks:
        label = blk.get("block_label", "")
        if label in ("image", "figure", "table"):
            bb = blk.get("block_bbox", [])
            if len(bb) == 4:
                w, h = bb[2] - bb[0], bb[3] - bb[1]
                if w >= 60 and h >= 40:
                    images.append(ImageBlock(x1=bb[0], y1=bb[1], x2=bb[2], y2=bb[3], label=label))

    return width, height, lines, images


# ----------------------- remote VL OCR -----------------------

async def _mcp_call(tool_name: str, args: dict) -> dict:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
    async with sse_client(f"{OCR_BASE}/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r = await session.call_tool(tool_name, args)
            for c in r.content:
                if hasattr(c, "text"):
                    return json.loads(c.text)
    return {}


def submit_vl_task(pdf_path: str, pages_spec: str) -> str:
    """POST /ocr-task/v1/create with page range. Returns taskId.

    VL service caches by file content MD5, so each call must use a unique
    file (we append a random comment to the PDF bytes to change the hash).
    """
    import httpx, os, hashlib
    # Append random bytes to PDF to bypass content-hash cache.
    # PDF readers ignore trailing garbage after %%EOF.
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    nonce = os.urandom(16).hex()
    unique_bytes = pdf_bytes + f"\n% cache-bust-{nonce}\n".encode()
    files = {"file": (Path(pdf_path).name, unique_bytes, "application/pdf")}
    data = {"ocr_type": "PaddleOCR-VL", "exec_pages": pages_spec}
    r = httpx.post(f"{OCR_BASE}/ocr-task/v1/create",
                   files=files, data=data, timeout=120)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success"):
        raise RuntimeError(f"VL create failed: {payload.get('message')}")
    return payload["data"]["taskId"]


def wait_vl_done(task_id: str, timeout_s: int = 600) -> None:
    """Poll MCP getTaskInfo until SUCCEED/FAILED."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        info = asyncio.run(_mcp_call("getTaskInfo", {"taskId": task_id}))
        data = info.get("data") or {}
        status = data.get("statusLbl") or data.get("status")
        if status in ("SUCCEED", 1, "1"):
            return
        if status in ("FAILED", 2, "2"):
            raise RuntimeError(f"VL task failed: {data}")
        time.sleep(5)
    raise TimeoutError(f"VL task {task_id} not done after {timeout_s}s")


def fetch_vl_paged_mds(task_id: str) -> dict[int, str]:
    """Download results.zip, return {page_index_0based: md_content}."""
    import io, zipfile, httpx, re
    result = asyncio.run(_mcp_call("presignedGetTaskOutput", {"taskId": task_id}))
    if not result.get("success"):
        raise RuntimeError(f"VL presignedGetTaskOutput failed: {result.get('message')}")
    urls = result["data"]["presignedOutputs"]
    if "results_file" not in urls:
        raise RuntimeError(f"VL results_file not in outputs: {list(urls.keys())}")
    r = httpx.get(urls["results_file"], timeout=120)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    out = {}
    for name in z.namelist():
        # results/0.md, results/1.md, ...
        m = re.match(r"results/(\d+)\.md$", name)
        if m:
            out[int(m.group(1))] = z.read(name).decode("utf-8")
    return out


def fetch_vl_all_pages(pdf_path: str) -> dict[int, str]:
    """Submit ONE task for the entire PDF, return {page_index_0based: md_content}.

    Sends the full PDF without exec_pages so VL processes all pages.
    Downloads results.zip and extracts per-page results/N.md.
    """
    task_id = submit_vl_task(pdf_path, "")  # empty = all pages
    print(f"  VL taskId: {task_id}", flush=True)
    wait_vl_done(task_id)
    return fetch_vl_paged_mds(task_id)


def fetch_vl_md_for_page(pdf_path: str, page_index_0based: int) -> str:
    """Legacy single-page API (kept for compatibility)."""
    return fetch_vl_all_pages(pdf_path).get(page_index_0based, "")


# ----------------------- alignment -----------------------

def split_vl_md_lines(md: str) -> list[str]:
    """Flatten markdown to a list of non-empty, heading-stripped lines."""
    out = []
    for block in md.split("\n\n"):
        for line in block.split("\n"):
            s = line.strip().lstrip("#").strip()
            if s:
                out.append(s)
    return out



def _is_junk_line(ln: Line) -> bool:
    """Skip lines that are noise: vertical text, stamps, or very low score."""
    w = ln.x2 - ln.x1
    h = ln.y2 - ln.y1
    text = ln.text.strip()
    # Dot leaders / standalone dots
    if text in ("……", "…", "⋯") or set(text) <= {"…", ".", "·", "⋮"}:
        return True
    # Stamp/vertical text: square or taller-than-wide, narrow, not tiny
    if h >= w * 0.5 and w < 100 and h > 20:
        return True
    # Large logo/graphic region
    if w > 150 and h > 80:
        return True
    # Very low OCR confidence
    if ln.score < 0.3:
        return True
    return False


def align_lines(local_lines: list[Line], vl_lines: list[str]) -> list[Line]:
    """Tag local lines with VL source when VL confirms the text.

    VL returns semantic paragraphs; local PP returns individual physical lines
    with bboxes. We keep local text (it matches the bbox) and mark source="vl"
    when VL contains matching content. This preserves correct positioning while
    indicating VL quality confirmation.
    """
    local_lines[:] = [ln for ln in local_lines if not _is_junk_line(ln)]
    _merge_nearby(local_lines)
    if not local_lines:
        return local_lines

    # Build a combined VL text blob for substring search
    vl_blob = "\n".join(vl_lines).replace(" ", "").lower()

    for ln in local_lines:
        local_ns = ln.text.replace(" ", "").lower()
        if not local_ns:
            ln.source = "local"
            continue
        # Check if local text (or a significant prefix) appears in VL output
        if len(local_ns) >= 3 and local_ns[:8] in vl_blob:
            ln.source = "vl"
        elif len(local_ns) >= 3 and local_ns[-8:] in vl_blob:
            ln.source = "vl"
        else:
            ln.source = "local"

    return local_lines

def _merge_nearby(lines: list[Line]) -> None:
    """Merge lines whose bboxes significantly overlap vertically AND are horizontally adjacent.

    This fixes vertical-text fragments (e.g. "督管" + "管理委" → "监督管理委")
    but does NOT merge lines that are side-by-side at the same y (e.g. two dates
    in left/right columns), or lines in different columns.
    """
    if not lines:
        return
    merged = [lines[0]]
    for ln in lines[1:]:
        prev = merged[-1]
        # Quick check: if horizontally far apart (> 40% of page width), never merge
        # This prevents merging left-column and right-column content at same y
        x_gap = max(ln.x1 - prev.x2, prev.x1 - ln.x2)  # positive = disjoint
        x_overlap = min(prev.x2, ln.x2) - max(prev.x1, ln.x1)  # positive = overlapping
        prev_w = prev.x2 - prev.x1
        ln_w = ln.x2 - ln.x1
        # Must have x overlap (not disjoint columns) for merge
        if x_overlap < -20:
            merged.append(ln)
            continue

        # Check vertical overlap
        overlap_start = max(prev.y1, ln.y1)
        overlap_end = min(prev.y2, ln.y2)
        prev_h = prev.y2 - prev.y1
        ln_h = ln.y2 - ln.y1
        min_h = min(prev_h, ln_h)
        if min_h > 0 and (overlap_end - overlap_start) / min_h > 0.5:
            # Merge: extend bbox, concatenate text
            prev.x1 = min(prev.x1, ln.x1)
            prev.x2 = max(prev.x2, ln.x2)
            prev.y1 = min(prev.y1, ln.y1)
            prev.y2 = max(prev.y2, ln.y2)
            if ln.source == "vl" and prev.source == "local":
                prev.text = ln.text
                prev.source = "vl"
            elif prev.source == "local" and ln.source == "local":
                prev.text += ln.text
            # else: keep prev VL text
            continue  # skip adding ln as separate line
        merged.append(ln)
    lines[:] = merged


# ----------------------- HTML emit -----------------------

PAGE_CSS = """
body { margin: 0; background: #ddd; font-family: "SimSun", "Microsoft YaHei", serif; }
.legend { font-family: sans-serif; font-size: 13px; padding: 10px; background: #fff;
          border-bottom: 1px solid #ccc; position: sticky; top: 0; }
.page { position: relative; background: #fff; margin: 20px auto;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15); overflow: hidden; }
.line { position: absolute; color: transparent; white-space: nowrap;
        line-height: 1.2; transform-origin: top left; overflow: visible;
        user-select: text; cursor: text; }
/* Invisible text for copy/select, with a subtle highlight on hover */
.line::selection { background: rgba(0,120,215,0.3); color: #000; }
.line:hover { color: rgba(0,0,0,0.5); background: rgba(0,120,215,0.08); }
"""


def _estimate_font_size(ln: Line) -> int:
    """Derive CSS font-size from bbox height.

    PNG is rendered at 1.5x PDF scale. The CSS page div is also 1.5x the PDF
    point size (893px = 595pt × 1.5). So bbox_height_px ≈ CSS_font_size_px.
    """
    h = ln.y2 - ln.y1
    return max(8, int(h))


def render_html(pages: list[PageResult], work_dir: Path, no_bg: bool = False) -> str:
    import base64

    if no_bg:
        # Text-only mode: visible positioned divs, no background image
        css = PAGE_CSS.replace("color: transparent", "color: #000") \
                       .replace("::selection", "DISABLED_selection") \
                       .replace(".line:hover { color: rgba(0,0,0,0.5); background: rgba(0,120,215,0.08); }", "")
    else:
        css = PAGE_CSS

    out = ['<!DOCTYPE html>', '<html lang="zh-CN"><head><meta charset="utf-8">',
           '<title>Layout restored</title>', f'<style>{css}</style>',
           '</head><body>']
    if no_bg:
        out.append('<div class="legend">纯文本模式 (无背景图)</div>')
    else:
        out.append('<div class="legend">'
                   '文本可选中复制 | 鼠标悬停高亮显示文本区域</div>')
    for p in pages:
        png_path = work_dir / f"page_{p.page_index}.png"
        if no_bg:
            out.append(f'<div class="page" style="width:{p.width}px; height:{p.height}px;">')
        else:
            b64 = base64.b64encode(png_path.read_bytes()).decode()
            bg = f"data:image/png;base64,{b64}"
            out.append(f'<div class="page" style="width:{p.width}px; height:{p.height}px; '
                       f'background-image:url({bg}); background-size:{p.width}px {p.height}px;">')

        # Embed cropped image regions from the page PNG
        if p.images and png_path.exists():
            from PIL import Image
            page_img = Image.open(png_path)
            for img in p.images:
                cropped = page_img.crop((int(img.x1), int(img.y1),
                                         int(img.x2), int(img.y2)))
                import io as _io
                buf = _io.BytesIO()
                cropped.save(buf, format="PNG")
                img_b64 = base64.b64encode(buf.getvalue()).decode()
                out.append(f'<img class="img-block" '
                           f'style="position:absolute; left:{img.x1:.0f}px; top:{img.y1:.0f}px; '
                           f'width:{img.x2-img.x1:.0f}px; height:{img.y2-img.y1:.0f}px; z-index:10;" '
                           f'src="data:image/png;base64,{img_b64}" alt="">')

        for ln in p.lines:
            font_px = _estimate_font_size(ln)
            text = html_lib.escape(ln.text)
            if no_bg:
                out.append(f'<div class="line" '
                           f'style="left:{ln.x1:.0f}px; top:{ln.y1:.0f}px; '
                           f'font-size:{font_px}px;">{text}</div>')
            else:
                out.append(f'<div class="line" '
                           f'style="left:{ln.x1:.0f}px; top:{ln.y1:.0f}px; '
                           f'font-size:{font_px}px; width:{ln.x2-ln.x1:.0f}px; '
                           f'height:{ln.y2-ln.y1:.0f}px;"'
                           f'>{text}</div>')
        out.append('</div>')
    out.append('</body></html>')
    return "\n".join(out)


# ----------------------- orchestration -----------------------

def process_page(pdf_path: str, page_index: int, work_dir: Path,
                 vl_md: str) -> PageResult:
    """Run local PP-StructureV3 only. VL md is fetched separately in batch."""
    png_path = work_dir / f"page_{page_index}.png"
    print(f"[page {page_index + 1}] rendering PNG...", flush=True)
    width, height = render_pdf_page(pdf_path, page_index, png_path)

    print(f"[page {page_index + 1}] running local PP-StructureV3...", flush=True)
    t0 = time.time()
    _, _, local_lines, pp_images = run_local_layout(png_path)
    print(f"[page {page_index + 1}] local PP done in {time.time() - t0:.1f}s "
          f"({len(local_lines)} lines, {len(pp_images)} images)", flush=True)

    # Also extract real image positions directly from the PDF (PyMuPDF).
    # PP sometimes misclassifies logos/figures as 'header'/'text'.
    pdf_images = extract_pdf_images(pdf_path, page_index)
    if pdf_images:
        print(f"[page {page_index + 1}] PDF-extracted images: {len(pdf_images)}",
              flush=True)
    images = merge_images(pp_images, pdf_images)

    vl_lines = split_vl_md_lines(vl_md)
    aligned = align_lines(local_lines, vl_lines)
    vl_count = sum(1 for l in aligned if l.source == "vl")
    print(f"[page {page_index + 1}] aligned: {vl_count}/{len(aligned)} "
          f"({vl_count / max(len(aligned), 1) * 100:.0f}%)", flush=True)

    _smooth_font_sizes(aligned)
    _split_overflow_lines(aligned)

    return PageResult(page_index=page_index, width=width, height=height,
                      lines=aligned, images=images)


def _smooth_font_sizes(lines: list[Line]) -> None:
    """Group lines into visual runs by y-gap, snap each run to its median height.

    Lines with large vertical gaps between them are different sections (body
    vs heading vs footnote). Small gaps are the same paragraph — OCR bbox
    jitter there is noise.
    """
    import statistics
    if not lines:
        return
    runs: list[list[int]] = []  # indices
    curr = [0]
    for i in range(1, len(lines)):
        gap = lines[i].y1 - lines[i - 1].y2
        if gap > 12:  # new section
            runs.append(curr)
            curr = [i]
        else:
            curr.append(i)
    runs.append(curr)

    for run in runs:
        heights = [lines[k].y2 - lines[k].y1 for k in run]
        median_h = statistics.median(heights)
        for k in run:
            lines[k].y2 = lines[k].y1 + median_h


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="input PDF path")
    parser.add_argument("--pages", default="1",
                        help="page range, e.g. '1', '1-5', '1,3,5-7' (1-based)")
    parser.add_argument("--output", default="layout_restored.html",
                        help="output HTML path (phase 3 only)")
    parser.add_argument("--work-dir", default=None,
                        help="dir for intermediate PNGs / cache (default: /tmp/ocr_layout_<pid>)")
    parser.add_argument("--no-background", action="store_true",
                        help="omit PNG background (text-only HTML with positioned divs)")
    parser.add_argument("--with-tables", action="store_true",
                        help="enable table structure recognition (uses ~2GB more RAM)")
    parser.add_argument("--debug", action="store_true",
                        help="keep intermediate files")
    parser.add_argument("--vl-only", action="store_true",
                        help="Phase 1: fetch VL md only, save to work-dir, exit")
    parser.add_argument("--local-only", action="store_true",
                        help="Phase 2: run local PP only, save bbox JSON to work-dir, exit")
    parser.add_argument("--vl-md-dir", default=None,
                        help="external VL md directory (phase 3: use these .md files instead of fetching)")
    args = parser.parse_args()

    if not Path(args.pdf).exists():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    _FLAGS["with_tables"] = args.with_tables

    pages = parse_page_range(args.pages)
    if not pages:
        print(f"invalid --pages: {args.pages}", file=sys.stderr)
        return 1

    work_dir = Path(args.work_dir) if args.work_dir else Path(f"/tmp/ocr_layout_{os.getpid()}")
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"work_dir: {work_dir}")

    # ---- Phase 1: VL only ----
    if args.vl_only:
        print(f"Phase 1: fetching VL md for {len(pages)} page(s) from full PDF...", flush=True)
        t0 = time.time()
        try:
            all_vl = fetch_vl_all_pages(args.pdf)
            print(f"VL done in {time.time() - t0:.1f}s ({len(all_vl)} pages total)", flush=True)
            vl_dir = work_dir / "vl_md"
            vl_dir.mkdir(exist_ok=True)
            for pi in sorted(all_vl):
                (vl_dir / f"{pi}.md").write_text(all_vl[pi])
            # Save per-page md for the requested range
            for pi in pages:
                md = all_vl.get(pi, "")
                path = work_dir / f"vl_{pi}.md"
                path.write_text(md)
                print(f"  saved vl_{pi}.md ({len(md)} chars)", flush=True)
            print(f"VL phase done. Cache at {work_dir}/", flush=True)
            return 0
        except Exception as e:
            print(f"VL phase FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            return 1

    # ---- Phase 2: local only ----
    if args.local_only:
        print(f"Phase 2: running local PP-StructureV3 on {len(pages)} page(s)...", flush=True)
        for pi in pages:
            png_path = work_dir / f"page_{pi}.png"
            print(f"  [page {pi + 1}] rendering PNG...", flush=True)
            width, height = render_pdf_page(args.pdf, pi, png_path)
            print(f"  [page {pi + 1}] running PP-StructureV3...", flush=True)
            t0 = time.time()
            _, _, lines, images = run_local_layout(png_path)
            elapsed = time.time() - t0
            print(f"  [page {pi + 1}] PP done in {elapsed:.1f}s "
                  f"({len(lines)} lines, {len(images)} images)", flush=True)
            # Save local bbox JSON
            bbox_records = [{"text": ln.text, "score": ln.score,
                             "x1": ln.x1, "y1": ln.y1, "x2": ln.x2, "y2": ln.y2,
                             "block_label": ln.block_label}
                            for ln in lines]
            bbox_path = work_dir / f"local_{pi}.json"
            bbox_path.write_text(json.dumps(bbox_records, ensure_ascii=False, indent=2))
            print(f"  saved local_{pi}.json", flush=True)
            # Save image blocks
            if images:
                img_records = [{"x1": i.x1, "y1": i.y1, "x2": i.x2, "y2": i.y2,
                                "label": i.label} for i in images]
                (work_dir / f"images_{pi}.json").write_text(
                    json.dumps(img_records, ensure_ascii=False, indent=2))
        print(f"Local phase done. Cache at {work_dir}/", flush=True)
        return 0

    # ---- Phase 3: combine (or single-shot) ----
    # Load VL md from work-dir cache or external vl-md-dir
    vl_paged: dict[int, str] = {}
    vl_from_cache = True
    for pi in pages:
        cache_path = work_dir / f"vl_{pi}.md"
        ext_path = Path(args.vl_md_dir) / f"{pi}.md" if args.vl_md_dir else None
        if ext_path and ext_path.exists():
            vl_paged[pi] = ext_path.read_text()
        elif cache_path.exists():
            vl_paged[pi] = cache_path.read_text()
        else:
            vl_from_cache = False
            break

    if vl_from_cache:
        print(f"VL md loaded from cache ({len(vl_paged)} pages)", flush=True)
    else:
        print(f"fetching VL md for {len(pages)} pages (single task)...", flush=True)
        t0 = time.time()
        try:
            vl_paged = fetch_vl_all_pages(args.pdf)
            # Also cache them
            for pi, md in vl_paged.items():
                (work_dir / f"vl_{pi}.md").write_text(md)
            print(f"VL done in {time.time() - t0:.1f}s ({len(vl_paged)} pages)", flush=True)
        except Exception as e:
            print(f"VL batch FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            vl_paged = {pi: "" for pi in pages}

    # Per-page local PP processing (serial to avoid OOM)
    page_results = []
    for pi in pages:
        try:
            vl_md = vl_paged.get(pi, "")
            page_results.append(process_page(args.pdf, pi, work_dir, vl_md))
        except Exception as e:
            print(f"[page {pi + 1}] FAILED: {type(e).__name__}: {e}",
                  file=sys.stderr)

    if not page_results:
        print("no pages succeeded", file=sys.stderr)
        return 1

    html = render_html(page_results, work_dir, no_bg=args.no_background)
    Path(args.output).write_text(html)
    print(f"\nwrote {args.output} ({len(page_results)} pages)")

    # Only clean up auto-generated temp dirs; keep user-specified work-dir
    if not args.debug and not args.work_dir:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    elif args.debug:
        # also dump per-page JSON for debugging
        for p in page_results:
            jf = work_dir / f"page_{p.page_index}_aligned.json"
            jf.write_text(json.dumps({
                "page_index": p.page_index,
                "width": p.width,
                "height": p.height,
                "lines": [{"text": l.text, "source": l.source,
                           "bbox": [l.x1, l.y1, l.x2, l.y2]}
                          for l in p.lines],
            }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
