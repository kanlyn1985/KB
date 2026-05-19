from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RecoveredSection:
    block_id: str
    title: str
    level: int
    section_number: str | None
    page_no: int


@dataclass(frozen=True)
class RecoveredStructure:
    doc_id: str
    sections: list[RecoveredSection]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def recover_structure_from_doc_ir(doc_ir_path: Path) -> RecoveredStructure:
    payload = json.loads(doc_ir_path.read_text(encoding="utf-8"))
    sections: list[RecoveredSection] = []

    for page in payload.get("pages", []):
        page_no = int(page["page_no"])
        for block in page.get("blocks", []):
            title = str(block.get("text") or "").strip()
            if not title:
                continue
            detected = _detect_heading(title, str(block.get("type", "")))
            if not detected:
                continue
            sections.append(
                RecoveredSection(
                    block_id=str(block["id"]),
                    title=title,
                    level=detected["level"],
                    section_number=detected["section_number"],
                    page_no=page_no,
                )
            )

    return RecoveredStructure(doc_id=str(payload["doc_id"]), sections=sections)


def save_recovered_structure(structure: RecoveredStructure, output_path: Path) -> Path:
    output_path.write_text(json.dumps(structure.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _detect_heading(text: str, block_type: str) -> dict[str, object] | None:
    stripped = text.strip()
    if block_type == "heading":
        hashes = len(stripped) - len(stripped.lstrip("#"))
        if hashes > 0:
            heading_text = stripped[hashes:].strip()
            numbered = _extract_section_number(heading_text)
            return {
                "level": min(hashes, 6),
                "section_number": numbered,
            }
        numbered = _extract_section_number(stripped)
        return {
            "level": _section_level(numbered),
            "section_number": numbered,
        }

    numbered = _extract_section_number(stripped)
    if numbered:
        return {
            "level": _section_level(numbered),
            "section_number": numbered,
        }
    if re.match(r"^附录\s*[A-ZＡ-Ｚ]", stripped):
        return {"level": 1, "section_number": None}
    return None


def _extract_section_number(text: str) -> str | None:
    match = re.match(r"^(\d+(?:\.\d+){0,5})\b", text)
    if match:
        return match.group(1)
    match = re.match(r"^([A-Z]\.\d+(?:\.\d+)*)\b", text)
    if match:
        return match.group(1)
    return None


def _section_level(section_number: str | None) -> int:
    if not section_number:
        return 2
    if "." not in section_number:
        return 1
    return min(section_number.count(".") + 1, 6)
