"""Document cover/metadata extraction.

Extracted from `facts._impl` to isolate the cover-page metadata,
standard candidate, and section-heading extraction from the term,
process, and fact-payload concerns. Cross-module callers inside
this package must import via `from ._extract_cover import ...`.
"""
from __future__ import annotations

import re
import unicodedata
from html import unescape
from datetime import UTC, datetime
from pathlib import Path

def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean_text(value: str) -> str:
    value = unescape(str(value or "")).replace("\xa0", " ")
    value = _normalize_ocr_text(value)
    value = re.sub(r"&nbsp;?", " ", value, flags=re.I)
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.strip() for line in value.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def _sanitize_payload(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return _clean_text(value)
    return value


def _normalize_ocr_text(value: str) -> str:
    # Replace Private Use Area characters (U+E000–U+F8FF) used as
    # dashes/separators in Chinese PDF fonts (e.g.  as hyphen).
    normalized = re.sub(r"[-]", "-", value)
    normalized = (
        normalized.replace("犌", "G")
        .replace("犅", "B")
        .replace("犜", "T")
    )
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = (
        normalized.replace("／", "/")
        .replace("—", "—")
        .replace("‐", "-")
        .replace("‑", "-")
        .replace("‒", "-")
        .replace("–", "-")
        .replace("﹣", "-")
        .replace("－", "-")
    )
    return normalized


STANDARD_CODE_PATTERN = re.compile(
    r"(?:GB/T|GBT|GB|ISO/IEC|ISO|IEC|SAE|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[.\-—:]\d+)*",
    re.I,
)
PROCESS_BP_PATTERN = re.compile(
    r"\b((?:ACQ|SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM|MLE|SPL)\.\d+)\.BP\d+\b",
    re.I,
)


def _normalize_standard_candidate(match: str) -> str:
    standard_code = _normalize_ocr_text(match).strip()
    standard_code = re.sub(r"(?i)^GBT", "GB/T", standard_code)
    standard_code = re.sub(r"(?i)^GB/T(?=\d)", "GB/T ", standard_code)
    standard_code = re.sub(r"(?i)^GB(?=\d)", "GB ", standard_code)
    standard_code = re.sub(r"(?i)^QC/T(?=\d)", "QC/T ", standard_code)
    standard_code = re.sub(r"(?i)^QC(?=\d)", "QC ", standard_code)
    standard_code = re.sub(r"\s+", " ", standard_code)
    prefix_match = re.match(r"(?i)^(GB/T|GB|ISO/IEC|ISO|IEC|SAE|QC/T|QC)\s*(.+)$", standard_code)
    if not prefix_match:
        return standard_code
    prefix = prefix_match.group(1).upper()
    rest = prefix_match.group(2).strip().replace("—", "-").replace(":", "-")
    parts = [part for part in re.split(r"-+", rest) if part]
    if len(parts) >= 2 and re.fullmatch(r"(?:19|20)\d{2}", parts[-1]):
        return f"{prefix} {'-'.join(parts[:-1])}—{parts[-1]}"
    return f"{prefix} {rest}".strip()


def _is_copyright_or_boilerplate_line(line: str) -> bool:
    compact = re.sub(r"\s+", " ", _normalize_ocr_text(line)).strip().lower()
    return bool(
        compact.startswith("©")
        or compact.startswith("(c)")
        or "copyright" in compact
        or "all rights reserved" in compact
        or "iso copyright office" in compact
    )


def _is_valid_standard_candidate(candidate: str, source_line: str) -> bool:
    if not candidate or _is_copyright_or_boilerplate_line(source_line):
        return False
    normalized = candidate.upper().replace("—", "-")
    match = re.match(r"^(GB/T|GB|ISO/IEC|ISO|IEC|SAE|QC/T|QC)\s+(.+)$", normalized)
    if not match:
        return False
    prefix, rest = match.group(1), match.group(2).strip()
    if prefix in {"ISO", "IEC"} and re.fullmatch(r"(?:19|20)\d{2}", rest):
        return False
    return len(re.findall(r"\d", rest)) >= 2


def _extract_standard_candidates(text: str, source_filename: str = "") -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    search_texts = [text]
    if source_filename:
        search_texts.append(Path(source_filename).stem)
    for search_text in search_texts:
        lines = _normalize_ocr_text(search_text).splitlines() or [search_text]
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            for match in STANDARD_CODE_PATTERN.findall(line):
                candidate = _normalize_standard_candidate(match)
                if not _is_valid_standard_candidate(candidate, line):
                    continue
                key = candidate.upper()
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
    return candidates


def _choose_primary_standard(candidates: list[str]) -> str | None:
    if not candidates:
        return None
    for candidate in candidates:
        if re.search(r"[-—]\d{4}$", candidate):
            return candidate
    return candidates[0]


def _extract_doc_metadata(text: str, source_filename: str = "") -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    text = _normalize_ocr_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title_found = False
    for line in lines:
        if line.startswith("# "):
            results.append(("document_title", "title", {"value": line[2:].strip()}))
            title_found = True
            break

    primary_standard = _choose_primary_standard(_extract_standard_candidates(text, source_filename))
    if primary_standard:
        results.append(("document_standard", "standard_code", {"value": primary_standard}))

    # Fallback: if no title found yet, use the first substantial line
    if not title_found:
        for line in lines:
            stripped = line.strip()
            if len(stripped) < 4:
                continue
            if stripped.startswith(("|", "#", "---", "注:", "NOTE", "ICS", "CCS")):
                continue
            if re.search(r"^\d{4}[/_-]", stripped):
                continue
            # Skip page number markers like "1/148", "2/50", "Page 1"
            if re.search(r"^\d+[/\\]\d+$", stripped) or re.search(r"^Page\s+\d+", stripped, re.I):
                continue
            if "发布" in stripped or "实施" in stripped or "国家标准" in stripped:
                continue
            compact = re.sub(r"\s+", "", stripped)
            if re.search(r"^(ICS|CCS|GB/T|GB|ISO|IEC|\d{4}-\d{2}-\d{2})", compact):
                continue
            results.append(("document_title", "title", {"value": re.sub(r"\s{2,}", " ", stripped)[:120]}))
            title_found = True
            break

    # Fallback: project-style document IDs like VAVE-CCU-SW-REQ-V3.0
    if not any(r[0] == "document_standard" for r in results):
        m = re.search(
            r"([A-Z]{2,}(?:-[A-Z0-9]+){2,}(?:-V\d[\d.]*)?)",
            source_filename + " " + text[:500],
        )
        if m:
            results.append(("document_standard", "standard_code", {"value": m.group(1)}))

    # Fallback: publication_date from filename
    pub_date, eff_date = _extract_dates_from_text(text)
    if not pub_date and not any(r[0] == "document_lifecycle" and r[1] == "publication_date" for r in results):
        m = re.search(r"(\d{4})[/_-](\d{2})[/_-](\d{2})", source_filename)
        if m:
            pub_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            m = re.search(
                r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
                text[:1000],
            )
            if m:
                pub_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    if pub_date:
        results.append(("document_lifecycle", "publication_date", {"value": pub_date}))
    if eff_date:
        results.append(("document_lifecycle", "effective_date", {"value": eff_date}))
    elif pub_date and not any(r[1] == "effective_date" for r in results):
        results.append(("document_lifecycle", "effective_date", {"value": pub_date}))

    replace_match = re.search(r"代替\s+([A-Z]{1,4}/?[A-Z]*\s*[\d.\-—]+)", text)
    if replace_match:
        results.append(("document_versioning", "replaces_standard", {"value": replace_match.group(1).strip()}))

    return results


# Date separator pattern: hyphen, em-dash, or normalized PUA chars (-)
_DATE_SEP = r"[-—]"

# Month name map for English academic-style dates
_EN_MONTH_MAP = {
    "January": "01", "February": "02", "March": "03",
    "April": "04", "May": "05", "June": "06",
    "July": "07", "August": "08", "September": "09",
    "October": "10", "November": "11", "December": "12",
}


def _extract_dates_from_text(text: str) -> tuple[str | None, str | None]:
    """Extract publication_date and effective_date from cover/first-page text.

    Handles these patterns found in our document corpus:
    1. Chinese:  2021-08-20发布  2022-03-01实施
    2. IEC:      Edition 3.0 2017-02  (publication year-month only)
    3. ISO:      Second edition2013-03-15  /  First edition\n2013-03-15
    4. English:  Date:\n2023-11-29  /  日期:\n2023-11-29
    5. Academic: 发布日期：2024年6月27日
    6. English:   Published Online April 2024
    """
    # Normalize text so PUA chars → dash
    normed = _normalize_ocr_text(text)
    # Also collapse whitespace around newlines for joined-text matching
    collapsed = re.sub(r"\s+", " ", normed)

    pub_date: str | None = None
    eff_date: str | None = None

    # --- Pattern 1: Chinese 发布 / 实施 ---
    m = re.search(rf"(\d{{4}}{_DATE_SEP}\d{{2}}{_DATE_SEP}\d{{2}})\s*发布", normed)
    if m:
        pub_date = m.group(1).replace("—", "-")
    m = re.search(rf"(\d{{4}}{_DATE_SEP}\d{{2}}{_DATE_SEP}\d{{2}})\s*实施", normed)
    if m:
        eff_date = m.group(1).replace("—", "-")

    # --- Pattern 2: IEC "Edition X.Y YYYY-MM" ---
    if not pub_date:
        m = re.search(r"[Ee]dition\s+\d[\d.]+\s+(\d{{4}}{_DATE_SEP}\d{{2}})", collapsed)
        if m:
            pub_date = m.group(1).replace("—", "-") + "-01"

    # --- Pattern 3: ISO "First edition2013-03-15" / "Second edition\n2013-03-15" ---
    if not pub_date:
        m = re.search(
            rf"(?:First|Second|Third|\d+st|\d+nd|\d+rd|\d+th)\s+[Ee]dition\s*(\d{{4}}{_DATE_SEP}\d{{2}}{_DATE_SEP}\d{{2}})",
            collapsed,
        )
        if m:
            pub_date = m.group(1).replace("—", "-")

    # --- Pattern 4: "Date: YYYY-MM-DD" / "日期: YYYY-MM-DD" ---
    if not pub_date:
        m = re.search(rf"(?:[Dd]ate|日期)\s*[:：]\s*(\d{{4}}{_DATE_SEP}\d{{2}}{_DATE_SEP}\d{{2}})", collapsed)
        if m:
            pub_date = m.group(1).replace("—", "-")

    # --- Pattern 5: Chinese academic "发布日期：YYYY年M月D日" ---
    if not pub_date:
        m = re.search(r"发布日期[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", normed)
        if m:
            pub_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # --- Pattern 6: "Published Online Month YYYY" ---
    if not pub_date:
        m = re.search(r"Published\s+Online\s+(\w+)\s+(\d{4})", normed)
        if m:
            month_str = _EN_MONTH_MAP.get(m.group(1))
            if month_str:
                pub_date = f"{m.group(2)}-{month_str}-01"

    return pub_date, eff_date


def _extract_cover_metadata(text: str, source_filename: str = "") -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    text = _normalize_ocr_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    primary_standard = _choose_primary_standard(_extract_standard_candidates(joined, source_filename))
    if primary_standard:
        results.append(("document_standard", "standard_code", {"value": primary_standard}))

    title_found = False
    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if len(compact) < 8:
            continue
        if compact.startswith(("ICS", "CCS", "GB/T", "GB", "ISO", "IEC")):
            continue
        if "国家标准" in compact:
            continue
        if "发布" in line or "实施" in line:
            continue
        if any(token in line for token in ("电动汽车", "车载充电机", "charger", "charging", "系统", "部分", "逆变器", "电源", "Road vehicles", "Unified diagnostic", "Specification and requirements")):
            clean_title = re.sub(r"^#+\s*", "", line).strip()
            results.append(("document_title", "title", {"value": re.sub(r"\s{2,}", " ", clean_title)}))
            title_found = True
            break

    # --- Fallback extraction for project-type documents ---
    # If the hardcoded patterns didn't find a standard, try project-style IDs
    if not any(r[0] == "document_standard" for r in results):
        m = re.search(
            r"([A-Z]{2,}(?:-[A-Z0-9]+){2,}(?:-V\d[\d.]*)?)",
            source_filename + " " + joined[:500],
        )
        if m:
            results.append(("document_standard", "standard_code", {"value": m.group(1)}))

    # Fallback title: first substantial line that isn't metadata/noise
    if not title_found and not any(r[0] == "document_title" for r in results):
        for line in lines:
            stripped = line.strip()
            if len(stripped) < 4:
                continue
            if stripped.startswith(("|", "#", "---", "注:", "NOTE", "ICS", "CCS", "GB/T", "GB", "ISO", "IEC")):
                continue
            if re.search(r"^\d{4}[/_-]", stripped):
                continue
            # Skip page number markers like "1/148", "2/50", "Page 1"
            if re.search(r"^\d+[/\\]\d+$", stripped) or re.search(r"^Page\s+\d+", stripped, re.I):
                continue
            if "发布" in stripped or "实施" in stripped or "国家标准" in stripped:
                continue
            results.append(("document_title", "title", {"value": stripped[:120]}))
            break

    # Fallback publication_date from filename or text
    pub_date, eff_date = _extract_dates_from_text(joined)
    if not pub_date and not any(r[0] == "document_lifecycle" and r[1] == "publication_date" for r in results):
        # Try filename date like _20251125 or 2025-11-25
        m = re.search(r"(\d{4})[/_-](\d{2})[/_-](\d{2})", source_filename)
        if m:
            pub_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            # Chinese date in first 1000 chars: YYYY年M月D日
            m = re.search(
                r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
                joined[:1000],
            )
            if m:
                pub_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    if pub_date:
        results.append(("document_lifecycle", "publication_date", {"value": pub_date}))
    if eff_date:
        results.append(("document_lifecycle", "effective_date", {"value": eff_date}))

    # Fallback effective_date: default to publication_date
    if not eff_date and pub_date and not any(r[0] == "document_lifecycle" and r[1] == "effective_date" for r in results):
        results.append(("document_lifecycle", "effective_date", {"value": pub_date}))

    # Fallback abstract: 摘要/概述/范围 paragraphs
    if not any(r[0] == "document_abstract" for r in results):
        m = re.search(
            r"(?:摘\s*要|概\s*述|范\s*围|Abstract|Scope)[：:]\s*(.+?)(?:\n\n|\n[^\n]{20,})",
            joined[:3000],
            re.DOTALL,
        )
        if m:
            abstract_text = m.group(1).strip()[:500]
            if len(abstract_text) >= 20:
                results.append(("document_abstract", "has_abstract", {"value": abstract_text}))

    return results


def _extract_section_headings(text: str) -> list[tuple[str, str, dict[str, object]]]:
    results: list[tuple[str, str, dict[str, object]]] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            if title and title not in seen:
                seen.add(title)
                results.append(
                    (
                        "section_heading",
                        "has_section",
                        {"title": title, "heading_level": level},
                    )
                )
            continue

        numbered = re.match(r"^(\d+(?:\.\d+){0,4})\s+(.+)$", line)
        if numbered:
            title = numbered.group(2).strip()
            if title and title not in seen:
                seen.add(title)
                results.append(
                    (
                        "section_heading",
                        "has_section",
                        {"title": title, "section_number": numbered.group(1), "heading_level": 0},
                    )
                )
    return results
