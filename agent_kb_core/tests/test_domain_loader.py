from pathlib import Path

from agent_kb.domains.loader import load_domain_pack


def test_load_generic_domain_pack() -> None:
    root = Path(__file__).resolve().parents[1]
    pack = load_domain_pack(root / "domains" / "generic")

    assert pack.domain_id == "generic"
    assert "Concept" in pack.object_types
    assert "definition" in pack.answer_contracts


def test_load_obc_dcdc_domain_pack() -> None:
    root = Path(__file__).resolve().parents[1]
    pack = load_domain_pack(root / "domains" / "obc_dcdc")

    assert pack.domain_id == "obc_dcdc"
    assert "Parameter" in pack.object_types
    assert "DCDC_OUTPUT_RIPPLE" in pack.terminology
    assert "parameter_constraint" in pack.answer_contracts
    assert any(rule.rule_id == "dcdc_output_ripple_context" for rule in pack.hidden_context_rules)
