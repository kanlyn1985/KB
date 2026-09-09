from pathlib import Path

from agent_kb.core import compile_text_document
from agent_kb.domains.loader import load_domain_pack


ROOT = Path(__file__).resolve().parents[1]


def test_compile_text_document_builds_evidence_units_and_facts() -> None:
    domain = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    text = """
1. 输出纹波要求

DCDC 输出纹波在额定负载下应不大于 30mVpp。

2. 测试方法

输出纹波测试方法应使用示波器在低压输出端测量。
""".strip()

    compiled = compile_text_document(text, title="DCDC sample", domain_pack=domain, max_evidence_chars=120)

    assert compiled.document.document_id.startswith("doc_")
    assert compiled.evidence_blocks
    assert compiled.source_units
    assert compiled.facts
    assert any(unit.unit_type == "requirement" for unit in compiled.source_units)
    assert any(fact.subject == "DCDC_OUTPUT_RIPPLE" for fact in compiled.facts)
    assert any(fact.fact_type == "parameter_constraint" for fact in compiled.facts)


def test_compile_text_document_without_domain_pack_still_extracts_generic_facts() -> None:
    text = "过压保护阈值应不小于 16V。"

    compiled = compile_text_document(text, title="generic requirement", max_evidence_chars=120)

    assert compiled.summary["documents"] == 1
    assert compiled.summary["facts"] >= 1
    assert compiled.facts[0].predicate == "constrains"
    assert compiled.facts[0].qualifiers["operator"] == ">="
    assert compiled.facts[0].qualifiers["value_numeric"] == 16
    assert compiled.facts[0].qualifiers["unit"] == "V"
