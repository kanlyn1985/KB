#!/usr/bin/env python3
"""Post-process VL Markdown output into knowledge-base-ready Markdown.

Takes the raw VL cache (vl_N.md, local_N.json, images_N.json, page_N.png)
and produces clean KB-ready Markdown with:
  1. Table repair — fix misaligned columns, HTML entities, merged-cell loss
  2. Image semantic extraction — crop image regions, call LLM for description

Usage:
  python scripts/vl_md_to_kb_md.py \
    --pdf tmp/GBT+18487.1-2023.pdf \
    --work-dir /tmp/ppstruct_test/vl_cache \
    --output-dir output/kb_md \
    --pages 1-157

Output: output/kb_md/page_001.md ... page_157.md
        output/kb_md/kb_full.md  (concatenated)
"""

import argparse
import base64
import html
import io
import json
import os
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Table repair
# ---------------------------------------------------------------------------

def _decode_html_entities(text: str) -> str:
    """Replace HTML entities like &#x27; &#39; &lt; &gt; &amp; etc.
    Also clean up escaped newlines from VL output.
    """
    text = html.unescape(text)
    # VL sometimes outputs literal \n in table cells
    text = text.replace("\\n", " ")
    return text


def _normalize_pipe_row(row: str) -> list[str]:
    """Split a markdown table row on | and strip cells."""
    cells = row.split("|")
    # Remove leading/trailing empty from split
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.match(r"^:?-+:?$", c) for c in cells)


def _table_to_structured_text(rows: list[list[str]], col_count: int) -> str:
    """Convert a wide/complex table to structured text format.

    Used as fallback when Markdown tables lose too much information
    (merged cells, >6 columns, etc.)
    """
    lines = []
    # Find header row (first non-separator row)
    header = rows[0] if rows else []
    for i, row in enumerate(rows):
        if not _is_separator_row(row):
            header = row
            break

    for row in rows:
        if _is_separator_row(row):
            continue
        if row == header and len(rows) > 2:
            # Skip repeating header
            continue
        # Format as "col1: val1, col2: val2, ..."
        parts = []
        for ci, cell in enumerate(row):
            cell = cell.strip()
            if cell:
                col_name = header[ci].strip() if ci < len(header) and header[ci].strip() else f"列{ci+1}"
                parts.append(f"{col_name}: {cell}")
        if parts:
            lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


def repair_table(lines: list[str]) -> list[str]:
    """Repair a markdown table block.

    Fixes:
    - HTML entities
    - Column count mismatches (pad or merge)
    - Stray non-pipe lines inside tables
    - Wide tables (>6 cols) converted to structured text
    """
    if not lines:
        return lines

    # Decode HTML entities in all lines first
    lines = [_decode_html_entities(l) for l in lines]

    # Collect only actual pipe rows
    pipe_rows = [(i, l) for i, l in enumerate(lines) if "|" in l]

    if len(pipe_rows) < 2:
        return lines

    # Parse all pipe rows into cell lists
    parsed = []
    for idx, row_str in pipe_rows:
        cells = _normalize_pipe_row(row_str)
        parsed.append((idx, cells))

    # Find the separator row to determine column count
    sep_col_count = None
    for idx, cells in parsed:
        if _is_separator_row(cells):
            sep_col_count = len(cells)
            break

    # If no separator, use max column count as target
    if sep_col_count is None:
        sep_col_count = max(len(c) for _, c in parsed)

    # For wide tables (>6 columns), use structured text fallback
    if sep_col_count > 6:
        normalized_rows = []
        for idx, cells in parsed:
            if _is_separator_row(cells):
                continue
            if len(cells) < sep_col_count:
                cells = cells + [""] * (sep_col_count - len(cells))
            elif len(cells) > sep_col_count:
                merged = " ".join(cells[sep_col_count - 1:])
                cells = cells[: sep_col_count - 1] + [merged]
            normalized_rows.append(cells)
        text = _table_to_structured_text(normalized_rows, sep_col_count)
        return [text]

    # Normalize all rows to sep_col_count
    result_rows = []
    for idx, cells in parsed:
        if _is_separator_row(cells):
            # Rebuild separator row with correct column count
            result_rows.append("| " + " | ".join(["---"] * sep_col_count) + " |")
        else:
            # Pad short rows, truncate long rows
            if len(cells) < sep_col_count:
                cells = cells + [""] * (sep_col_count - len(cells))
            elif len(cells) > sep_col_count:
                merged = " ".join(cells[sep_col_count - 1:])
                cells = cells[: sep_col_count - 1] + [merged]
            result_rows.append("| " + " | ".join(cells) + " |")

    # Rebuild the full block: replace pipe rows, keep non-pipe lines
    output = list(lines)
    pipe_idx = 0
    for orig_idx, orig_line in enumerate(lines):
        if "|" in orig_line and pipe_idx < len(result_rows):
            output[orig_idx] = result_rows[pipe_idx]
            pipe_idx += 1

    return output


def repair_tables_in_md(md_text: str) -> str:
    """Find and repair all table blocks in a markdown document."""
    lines = md_text.split("\n")
    result = []
    table_block = []
    in_table = False

    for line in lines:
        if "|" in line:
            in_table = True
            table_block.append(line)
        else:
            if in_table:
                result.extend(repair_table(table_block))
                table_block = []
                in_table = False
            result.append(line)

    if table_block:
        result.extend(repair_table(table_block))

    return "\n".join(result)


# ---------------------------------------------------------------------------
# 2. Base64 image stripping + placeholder
# ---------------------------------------------------------------------------

def strip_base64_images(md_text: str) -> tuple[str, list[tuple[int, str]]]:
    """Remove base64 image embeds and replace with numbered placeholders.

    Returns (cleaned_md, [(placeholder_index, base64_data), ...])
    """
    placeholders = []
    counter = 0

    def _replace(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        alt_text = m.group(1) or "Image"
        placeholders.append((counter, m.group(2)))
        return f"[{alt_text} - 见图{counter}]"

    # Match ![alt](data:image/...;base64,XXXX)
    cleaned = re.sub(
        r"!\[([^\]]*)\]\(data:image/[^;]+;base64,([A-Za-z0-9+/=]+)\)",
        _replace,
        md_text,
    )
    return cleaned, placeholders


# ---------------------------------------------------------------------------
# 3. Image region cropping + LLM description
# ---------------------------------------------------------------------------

def crop_image_region(
    page_png_path: str, x1: int, y1: int, x2: int, y2: int, scale: float = 1.0
) -> bytes | None:
    """Crop a rectangular region from a page PNG, return PNG bytes."""
    try:
        from PIL import Image

        img = Image.open(page_png_path)
        # Bboxes are already in PNG pixel coordinates
        region = img.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        region.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"  [crop] failed: {e}", flush=True)
        return None


def describe_image_llm(png_bytes: bytes, page_num: int, region_idx: int) -> str:
    """Call the local LLM proxy to describe an image.

    Returns a text description of the image content.
    """
    import httpx

    # Clear proxy env vars that interfere with local LLM calls
    for k in ("http_proxy", "https_proxy", "all_proxy", "ALL_PROXY"):
        os.environ.pop(k, None)

    api_base = os.environ.get("ANTHROPIC_BASE_URL", "http://127.0.0.1:15721")
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    model = os.environ.get("TEXT_LLM_MODEL", "claude-3-5-sonnet-20241022")

    b64 = base64.b64encode(png_bytes).decode()
    url = f"{api_base.rstrip('/')}/v1/messages"

    payload = {
        "model": model,
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"这是中国国家标准GB/T 18487.1-2023（电动汽车传导充电系统）"
                            f"第{page_num}页的一个图表/图片区域（区域{region_idx}）。"
                            f"请用中文简要描述这个图表的内容和关键信息，"
                            f"包括：图表类型、标注的关键参数、电路/结构特征等。"
                            f"只输出描述，不要加前缀。"
                        ),
                    },
                ],
            }
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"  [LLM] image description failed: {e}", flush=True)
        return ""


# ---------------------------------------------------------------------------
# 4. Heading normalization
# ---------------------------------------------------------------------------

def normalize_headings(md_text: str) -> str:
    """Clean up heading levels from VL output.

    VL often produces ## for section titles that should be ### or deeper,
    and mixes heading levels inconsistently. We normalize by looking at
    section numbering patterns.
    """
    lines = md_text.split("\n")
    result = []

    for line in lines:
        # Pattern: "##### 3.1.4.2" followed by "## 模式2 mode 2"
        # The section number should match the heading depth
        m = re.match(r"^(#{1,6})\s+(\d+(?:\.\d+)*)\s*$", line)
        if m:
            section_num = m.group(2)
            depth = section_num.count(".") + 1
            # Map: 3 → ##, 3.1 → ###, 3.1.4 → ####, 3.1.4.2 → #####
            new_depth = min(depth + 1, 6)
            line = "#" * new_depth + " " + section_num
        result.append(line)

    return "\n".join(result)


# ---------------------------------------------------------------------------
# 5. Noise cleanup
# ---------------------------------------------------------------------------

def normalize_special_symbols(md_text: str) -> str:
    """Replace special Unicode symbols with searchable plain-text equivalents.

    These symbols are invisible to FTS5 unicode61 tokenizer and CJK LIKE
    queries, so they must be converted to plain text for KB retrieval.
    """
    SYMBOL_MAP = {
        # Math comparison
        "≤": "<=",
        "≥": ">=",
        "≠": "!=",
        "±": "+-",
        "×": "x",
        "÷": "/",
        "∞": "无穷大",
        # Arrows (state transitions in tables)
        "→": "转为",
        "←": "←",
        "↑": "↑",
        "↓": "↓",
        "⇒": "=>",
        # Temperature / units
        "℃": "摄氏度",
        "°": "度",
        "′": "角分",
        "″": "角秒",
        # Dashes — keep em-dash as Chinese dash for readability
        "—": "——",  # em dash
        "–": "-",    # en dash
        # Smart quotes → straight quotes
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        # Enclosed numbers
        "①": "(1)", "②": "(2)", "③": "(3)", "④": "(4)", "⑤": "(5)",
        "⑥": "(6)", "⑦": "(7)", "⑧": "(8)", "⑨": "(9)", "⑩": "(10)",
        "⑪": "(11)", "⑫": "(12)", "⑬": "(13)", "⑭": "(14)", "⑮": "(15)",
        "⑯": "(16)", "⑰": "(17)", "⑱": "(18)", "⑲": "(19)", "⑳": "(20)",
        # Geometric
        "○": "圆", "●": "实心圆", "△": "三角形", "▲": "上三角",
        "▽": "倒三角", "▼": "下三角", "◇": "菱形", "◆": "实心菱形",
        "□": "方框", "■": "实心方框", "☆": "星", "★": "实心星",
        # Misc
        "※": "参考", "〇": "零",
    }
    for sym, replacement in SYMBOL_MAP.items():
        md_text = md_text.replace(sym, replacement)
    return md_text


def cleanup_noise(md_text: str) -> str:
    """Remove common noise patterns from VL output."""
    lines = md_text.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.strip()

        # Skip lines that are only dots/dashes (dot leaders in TOC)
        if stripped and set(stripped) <= {"…", ".", "·", "⋮", "-", " ", "——"}:
            continue

        # Skip standalone page numbers
        if re.match(r"^\d{1,3}$", stripped):
            continue

        # Skip empty heading lines (e.g., "##### " with no text)
        if re.match(r"^#{1,6}\s*$", line):
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# 6. Content filtering — remove KB-irrelevant content
# ---------------------------------------------------------------------------

# Page ranges to skip entirely (0-indexed)
_SKIP_PAGE_RANGES = [
    (0, 0),    # page 1: cover / copyright
    (1, 1),    # page 2: table of contents
]

# Heading patterns that signal KB-irrelevant sections (matched against
# the title text AFTER stripping leading # and section numbers)
_SKIP_SECTION_TITLES = [
    r"^前\s*言$",
    r"^引\s*言$",
    r"^规范性引用文件$",
]

# Patterns for lines to strip anywhere
_STRIP_LINE_PATTERNS = [
    r"^##\s*第\d+页$",                           # page number headers
    r"^\*\*图片说明[：:]\*\*",                     # image description block header
    r"^\-?\s*\[图\d+[：:]",                       # individual image description items
    r"^\-?\s*---$",                                # standalone horizontal rules
]

# Inline patterns to clean (replace, not remove line)
_INLINE_CLEAN_PATTERNS = [
    # LaTeX math remnants: $ U_{a} $, $ ^{{a}} $, $I_{n}$
    # Also handles multi-line LaTeX that starts with $ but doesn't close
    (r"\$[^$]*\$", ""),
    (r"\$\s", ""),
    # Cross-reference dead links: 见表C.14, 如图C.5所示, 见4.3.5
    # But KEEP the reference target name — only remove the "见…所示" wrapper
    (r"[，,]?见[表图附][^\s，。；,]+?(?:的规定|所示|要求)?", ""),
    # ICS/CCS classification codes
    (r"ICS\s+\d+\.\d+\.\d+", ""),
    (r"CCS\s+[A-Z]\d+", ""),
]


def _is_skip_page(page_index: int) -> bool:
    for start, end in _SKIP_PAGE_RANGES:
        if start <= page_index <= end:
            return True
    return False


def _starts_skip_section(line: str) -> bool:
    """Check if a heading line starts a section to skip."""
    # Strip markdown heading markers
    title = line.lstrip("#").strip()
    # Strip section number prefix like "2 ", "A.1 "
    title = re.sub(r"^[A-Z]?\d*\.?\d*\s+", "", title)
    for pat in _SKIP_SECTION_TITLES:
        if re.match(pat, title):
            return True
    return False


def filter_kb_content(md_text: str, page_index: int) -> str:
    """Remove content that is irrelevant for knowledge base retrieval.

    Removes:
    - Cover/copyright/TOC pages
    - Foreword (前言) and introduction (引言) sections
    - Normative references section (规范性引用文件) — full bibliographic entries
    - Page number headers from conversion
    - Image description blocks (LLM-generated alt-text)
    - LaTeX math remnants ($...$)
    - Cross-reference dead links (见表X, 如图Y所示)
    - ICS/CCS classification codes
    """
    # Skip entire pages
    if _is_skip_page(page_index):
        return ""

    lines = md_text.split("\n")
    result = []
    in_skip_section = False
    skip_depth = 0

    for line in lines:
        stripped = line.strip()

        # Track section-level skipping (前言, 规范性引用文件, etc.)
        heading_m = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_m:
            depth = len(heading_m.group(1))
            title = heading_m.group(2).strip()
            if in_skip_section:
                # Exit skip if same or shallower heading
                if depth <= skip_depth:
                    in_skip_section = False
                else:
                    continue
            # Enter skip if matches skip headings
            if _starts_skip_section(line):
                in_skip_section = True
                skip_depth = depth
                continue

        if in_skip_section:
            continue

        # Strip matching lines
        skip_line = False
        for pat in _STRIP_LINE_PATTERNS:
            if re.match(pat, stripped):
                skip_line = True
                break
        if skip_line:
            continue

        # Inline cleaning
        for pat, repl in _INLINE_CLEAN_PATTERNS:
            line = re.sub(pat, repl, line)

        # Remove trailing whitespace-only lines
        if stripped == "" and result and result[-1].strip() == "":
            continue

        result.append(line)

    # Trim leading/trailing blank lines
    while result and result[0].strip() == "":
        result.pop(0)
    while result and result[-1].strip() == "":
        result.pop()

    return "\n".join(result)


# ---------------------------------------------------------------------------
# 7. Main pipeline
# ---------------------------------------------------------------------------

def process_page(
    page_index: int,
    pdf_path: str,
    work_dir: str,
) -> str:
    """Process a single page and return KB-ready markdown."""

    vl_md_path = os.path.join(work_dir, f"vl_{page_index}.md")
    images_json_path = os.path.join(work_dir, f"images_{page_index}.json")
    page_png_path = os.path.join(work_dir, f"page_{page_index}.png")

    # Read VL markdown
    if not os.path.exists(vl_md_path):
        return f"<!-- Page {page_index + 1}: VL markdown not found -->\n"

    with open(vl_md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # Step 1: Strip base64 images, record placeholders
    md_text, b64_placeholders = strip_base64_images(md_text)

    # Step 2: Normalize headings
    md_text = normalize_headings(md_text)

    # Step 3: Repair tables
    md_text = repair_tables_in_md(md_text)

    # Step 4: Normalize special symbols (→ ≤ ≥ ℃ etc.)
    md_text = normalize_special_symbols(md_text)

    # Step 5: Cleanup noise
    md_text = cleanup_noise(md_text)

    # Step 6: Filter KB-irrelevant content (cover, TOC, foreword, image
    # descriptions, LaTeX, dead cross-references, etc.)
    md_text = filter_kb_content(md_text, page_index)

    if not md_text.strip():
        return ""

    return md_text


def main():
    parser = argparse.ArgumentParser(description="VL Markdown → KB-ready Markdown")
    parser.add_argument("--pdf", required=True, help="Source PDF path")
    parser.add_argument(
        "--work-dir", required=True, help="VL cache work directory"
    )
    parser.add_argument(
        "--output-dir", required=True, help="Output directory for KB markdown"
    )
    parser.add_argument(
        "--pages", default="1-157", help="Page range (e.g. 1-10, 1-157)"
    )
    args = parser.parse_args()

    # Parse page range
    m = re.match(r"(\d+)-(\d+)", args.pages)
    if not m:
        print(f"Invalid page range: {args.pages}", file=sys.stderr)
        sys.exit(1)
    start, end = int(m.group(1)), int(m.group(2))

    os.makedirs(args.output_dir, exist_ok=True)
    all_pages = []

    for pi in range(start - 1, end):
        page_num = pi + 1
        print(f"[page {page_num}] processing...", end="", flush=True)
        t0 = time.time()

        md = process_page(
            pi,
            args.pdf,
            args.work_dir,
        )

        # Skip empty pages (filtered out)
        if not md.strip():
            print(f" skipped (filtered)", flush=True)
            continue

        # Write per-page file
        out_path = os.path.join(args.output_dir, f"page_{page_num:03d}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)

        elapsed = time.time() - t0
        print(f" done ({elapsed:.1f}s)", flush=True)
        all_pages.append(md)

    # Write concatenated file
    full_path = os.path.join(args.output_dir, "kb_full.md")
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(
            f"# GB/T 18487.1-2023 电动汽车传导充电系统 第1部分：通用要求\n"
            f"# 知识库 Markdown（{end - start + 1} 页）\n\n"
        )
        f.write("\n\n".join(all_pages))

    print(f"\nDone. Output: {args.output_dir}/")


if __name__ == "__main__":
    main()
