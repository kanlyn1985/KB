from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.structure_recovery import recover_structure_from_doc_ir
from test_helpers import resolve_doc_id_by_filename


def test_recover_structure_from_doc_ir_extracts_sections() -> None:
    doc_id = resolve_doc_id_by_filename("QC_T 1036", "逆变器")
    structure = recover_structure_from_doc_ir(Path(f"knowledge_base/normalized/{doc_id}.doc_ir.json"))

    assert structure.doc_id == doc_id
    assert structure.sections
    assert any("汽车电源逆变器" in item.title for item in structure.sections)
    assert any(item.section_number in {"4.2", "4.6.4", "5.10", "7"} for item in structure.sections)
