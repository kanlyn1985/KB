"""CLI subcommand smoke tests (no live LLM / long-running servers)."""

from __future__ import annotations

import json
from pathlib import Path

from kb_ontology.cli import main
from kb_ontology.storage.store import OntologyStore


def _repo_domain() -> Path:
    return Path(__file__).resolve().parents[1] / "domains" / "obc_dcdc"


def _seed(db: Path) -> None:
    with OntologyStore(db) as store:
        ent = store.upsert_entity("Product", "DC-DC转换器", "obc_dcdc")
        store.upsert_attribute(ent.id, "description", "车载直流变换器", "string")
        store.add_evidence(
            ref_type="entity",
            ref_id=ent.id,
            document_id="doc1",
            text_span="DC-DC转换器用于车载电源",
            location="§1",
            confidence=0.9,
        )


def test_cli_health_and_query(tmp_path: Path, capsys) -> None:
    db = tmp_path / "ont.db"
    _seed(db)
    domain = str(_repo_domain())

    assert main(["health", "--db", str(db), "--domain-dir", domain]) == 0
    health = json.loads(capsys.readouterr().out)
    assert health["status"] == "ok"

    assert main(
        [
            "query",
            "--db",
            str(db),
            "--domain-dir",
            domain,
            "--text",
            "什么是DC-DC转换器",
        ]
    ) == 0
    pack = json.loads(capsys.readouterr().out)
    assert "judgement" in pack
    assert "recommended_answer_strategy" in pack
