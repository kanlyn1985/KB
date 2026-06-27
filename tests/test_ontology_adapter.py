"""Tests for the ontology shadow/guard adapter (Sprint 2 WP3/WP4).

Covers: mode resolution, read-only entity detection, relation checks,
guard post-check, DB-missing fault tolerance, and the invariant that the
adapter never mutates retrieval/answer (changed_* always False in Sprint 2).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from enterprise_agent_kb.ontology_adapter import (
    AnswerPostCheck,
    EntityConstraint,
    OntologySignal,
    analyze,
    project_retrieval_filtering,
    get_ontology_mode,
    post_check,
)

KB_ROOT = Path("knowledge_base")
HAS_ONTOLOGY_DB = (KB_ROOT / "ontology" / "ontology.db").exists()


def test_default_mode_is_off():
    assert get_ontology_mode({}) == "off"
    assert get_ontology_mode({"KB1_ONTOLOGY_MODE": ""}) == "off"
    assert get_ontology_mode({"KB1_ONTOLOGY_MODE": "garbage"}) == "off"


def test_mode_resolution():
    assert get_ontology_mode({"KB1_ONTOLOGY_MODE": "off"}) == "off"
    assert get_ontology_mode({"KB1_ONTOLOGY_MODE": "shadow"}) == "shadow"
    assert get_ontology_mode({"KB1_ONTOLOGY_MODE": "GUARD"}) == "guard"
    assert get_ontology_mode({"KB1_ONTOLOGY_MODE": " Shadow "}) == "shadow"


def test_off_mode_returns_empty_signal_with_zero_overhead():
    sig = analyze("any query", KB_ROOT, mode="off")
    assert sig.mode == "off"
    assert sig.query_entities == []
    assert sig.relation_checks == []
    assert sig.post_checks == []
    assert sig.changed_retrieval is False
    assert sig.changed_answer is False
    assert sig.errors == []


def test_missing_db_is_captured_in_errors_not_raised(tmp_path):
    # tmp_path has no ontology/ontology.db
    sig = analyze("ISO 14229-1", tmp_path, mode="shadow")
    assert sig.mode == "shadow"
    assert sig.query_entities == []
    assert any("not found" in e for e in sig.errors)


@pytest.mark.skipif(not HAS_ONTOLOGY_DB, reason="ontology.db not available")
class TestWithRealOntologyDB:
    """Integration-style tests against the real ontology.db (OBC/UDS domain)."""

    def test_shadow_detects_standard_entity(self):
        sig = analyze("什么是 ISO 14229-1 的 0x22 服务？", KB_ROOT, mode="shadow")
        assert sig.mode == "shadow"
        assert sig.errors == []
        mentions = [e.mention for e in sig.query_entities]
        assert "ISO 14229-1" in mentions
        # longest-match dedup: 'ISO 14229' / 'ISO' should be dropped
        assert "ISO 14229" not in mentions
        assert "ISO" not in mentions
        std = next(e for e in sig.query_entities if e.mention == "ISO 14229-1")
        assert std.class_name == "Standard"
        assert std.confidence == pytest.approx(0.95)

    def test_shadow_never_mutates_retrieval_or_answer(self):
        sig = analyze("ISO 14229-1", KB_ROOT, mode="shadow")
        assert sig.changed_retrieval is False
        assert sig.changed_answer is False

    def test_guard_mode_also_reads_entities(self):
        sig = analyze("ISO 14229-1", KB_ROOT, mode="guard")
        assert sig.mode == "guard"
        assert len(sig.query_entities) >= 1


@pytest.mark.skipif(not HAS_ONTOLOGY_DB, reason="ontology.db not available")
def test_empty_query_returns_empty_signal():
    sig = analyze("", KB_ROOT, mode="shadow")
    assert sig.query_entities == []


@pytest.mark.skipif(not HAS_ONTOLOGY_DB, reason="ontology.db not available")
class TestGuardPostCheck:
    def test_post_check_does_not_mutate_answer(self):
        sig = analyze("ISO 14229-1", KB_ROOT, mode="guard")
        checks = post_check("ISO 14229-1", "some answer", sig, workspace_root=KB_ROOT)
        # guard never changes the answer
        assert sig.changed_answer is False
        assert isinstance(checks, list)

    def test_post_check_off_mode_returns_empty(self):
        sig = analyze("ISO 14229-1", KB_ROOT, mode="off")
        assert post_check("ISO 14229-1", "answer", sig, workspace_root=KB_ROOT) == []

    def test_post_check_no_query_entities_returns_empty(self):
        # A query with no ontology entity mentions
        sig = analyze("zzzzz nonexistent term", KB_ROOT, mode="guard")
        assert sig.query_entities == []
        assert post_check("zzzzz", "answer", sig, workspace_root=KB_ROOT) == []

    def test_post_check_flags_out_of_class_answer_entity(self, tmp_path):
        """A synthetic 2-class ontology: answer mentions a class outside the
        query's detected classes → warning produced (logic guard for WP4)."""
        db_path = tmp_path / "ontology" / "ontology.db"
        db_path.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE class_def (class_id TEXT PRIMARY KEY, class_name TEXT, parent_class_id TEXT,
                layer TEXT, domain TEXT, description TEXT, is_core INTEGER, created_at TEXT);
            CREATE TABLE entity (entity_id TEXT PRIMARY KEY, canonical_name TEXT, class_id TEXT,
                domain TEXT, description TEXT, aliases_json TEXT, source_path TEXT, created_at TEXT);
            CREATE TABLE relation_def (relation_name TEXT PRIMARY KEY, category TEXT, scope TEXT,
                inverse_name TEXT, description TEXT, created_at TEXT);
            CREATE TABLE relation (relation_id INTEGER PRIMARY KEY AUTOINCREMENT, relation_name TEXT,
                source_entity_id TEXT, target_entity_id TEXT, created_at TEXT);
            CREATE TABLE term (canonical_name TEXT, aliases_json TEXT, class_id TEXT);
            """
        )
        conn.executemany(
            "INSERT INTO class_def VALUES (?,?,?,?,?,?,?,?)",
            [
                ("CLS-A", "ClassA", None, "meta", None, "", 1, "2026"),
                ("CLS-B", "ClassB", None, "meta", None, "", 1, "2026"),
            ],
        )
        conn.executemany(
            "INSERT INTO entity VALUES (?,?,?,?,?,?,?,?)",
            [
                ("E1", "WidgetA", "CLS-A", None, "", "[]", "", "2026"),
                ("E2", "WidgetB", "CLS-B", None, "", "[]", "", "2026"),
            ],
        )
        conn.commit()
        conn.close()

        sig = analyze("WidgetA", tmp_path, mode="guard")
        assert [e.mention for e in sig.query_entities] == ["WidgetA"]
        # Answer mentions WidgetB (class B), which is outside the query's class A
        checks = post_check("WidgetA", "see also WidgetB", sig, workspace_root=tmp_path)
        assert sig.changed_answer is False
        assert len(checks) == 1
        assert checks[0].severity == "warning"
        assert "WidgetB" in checks[0].message

    def test_post_check_same_class_no_warning(self, tmp_path):
        """Answer mentioning another entity of the SAME class as the query → no warning."""
        db_path = tmp_path / "ontology" / "ontology.db"
        db_path.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE class_def (class_id TEXT PRIMARY KEY, class_name TEXT, parent_class_id TEXT,
                layer TEXT, domain TEXT, description TEXT, is_core INTEGER, created_at TEXT);
            CREATE TABLE entity (entity_id TEXT PRIMARY KEY, canonical_name TEXT, class_id TEXT,
                domain TEXT, description TEXT, aliases_json TEXT, source_path TEXT, created_at TEXT);
            CREATE TABLE relation_def (relation_name TEXT PRIMARY KEY, category TEXT, scope TEXT,
                inverse_name TEXT, description TEXT, created_at TEXT);
            CREATE TABLE relation (relation_id INTEGER PRIMARY KEY AUTOINCREMENT, relation_name TEXT,
                source_entity_id TEXT, target_entity_id TEXT, created_at TEXT);
            CREATE TABLE term (canonical_name TEXT, aliases_json TEXT, class_id TEXT);
            """
        )
        conn.executemany(
            "INSERT INTO class_def VALUES (?,?,?,?,?,?,?,?)",
            [("CLS-A", "ClassA", None, "meta", None, "", 1, "2026")],
        )
        conn.executemany(
            "INSERT INTO entity VALUES (?,?,?,?,?,?,?,?)",
            [
                ("E1", "WidgetA", "CLS-A", None, "", "[]", "", "2026"),
                ("E2", "WidgetA2", "CLS-A", None, "", "[]", "", "2026"),
            ],
        )
        conn.commit()
        conn.close()

        sig = analyze("WidgetA", tmp_path, mode="guard")
        checks = post_check("WidgetA", "see also WidgetA2", sig, workspace_root=tmp_path)
        # WidgetA2 shares the query's class (CLS-A) → not flagged
        assert checks == []
        assert sig.changed_answer is False


def test_to_dict_roundtrip_shape():
    sig = OntologySignal(
        mode="shadow",
        query_entities=[EntityConstraint("X", "CLS-A", "ClassA", 0.9)],
    )
    d = sig.to_dict()
    assert d["mode"] == "shadow"
    assert d["query_entities"][0]["mention"] == "X"
    assert d["changed_retrieval"] is False
    assert d["changed_answer"] is False


@pytest.mark.skipif(not HAS_ONTOLOGY_DB, reason="ontology.db not available")
class TestAnswerQueryGuardWiring:
    """WP4: answer_query exposes ontology post-check fields and never mutates
    the answer, regardless of mode."""

    def test_off_mode_post_check_skipped(self, monkeypatch):
        monkeypatch.delenv("KB1_ONTOLOGY_MODE", raising=False)
        from enterprise_agent_kb.answer_api import answer_query

        payload = answer_query(KB_ROOT, "什么是控制导引电路？", limit=4)
        assert payload["ontology_post_check_status"] == "skipped"
        assert payload["answer_changed_by_ontology"] is False
        assert payload["ontology_post_checks"] == []
        # the answer itself is unaffected by the adapter
        assert "控制导引电路" in str(payload.get("direct_answer") or "")

    def test_guard_mode_runs_post_check_without_mutating_answer(self, monkeypatch):
        monkeypatch.setenv("KB1_ONTOLOGY_MODE", "guard")
        from enterprise_agent_kb.answer_api import answer_query

        payload = answer_query(KB_ROOT, "什么是控制导引电路？", limit=4)
        assert payload["ontology_post_check_status"] == "completed"
        assert payload["answer_changed_by_ontology"] is False
        assert isinstance(payload["ontology_post_checks"], list)
        # guard never rewrites the answer text
        assert "控制导引电路" in str(payload.get("direct_answer") or "")

    def test_wp6_guard_findings_merged_into_warnings(self, monkeypatch):
        """Sprint 3 WP6: guard post-check findings surface in answer warnings.

        Monkeypatch the ontology post_check to return a synthetic finding and
        assert it appears as a structured ontology_guard warning (source/type/
        severity/message, changed_answer=False) without mutating direct_answer.
        """
        monkeypatch.setenv("KB1_ONTOLOGY_MODE", "guard")
        import enterprise_agent_kb.answer_api as aa
        from enterprise_agent_kb.ontology_adapter import AnswerPostCheck

        synthetic = [AnswerPostCheck(
            type="entity_type_mismatch", severity="warning",
            message="synthetic finding for test",
        )]
        monkeypatch.setattr(aa, "_ontology_post_check", lambda *a, **k: synthetic)

        payload = aa.answer_query(KB_ROOT, "什么是控制导引电路？", limit=4)
        guard_warnings = [
            w for w in payload["warnings"]
            if isinstance(w, dict) and w.get("source") == "ontology_guard"
        ]
        assert len(guard_warnings) == 1
        assert guard_warnings[0]["type"] == "entity_type_mismatch"
        assert guard_warnings[0]["severity"] == "warning"
        assert guard_warnings[0]["changed_answer"] is False
        # answer text unchanged, flag stays false
        assert payload["answer_changed_by_ontology"] is False
        assert "控制导引电路" in str(payload.get("direct_answer") or "")
        # the finding also appears in ontology_post_checks
        assert payload["ontology_post_checks"][0]["type"] == "entity_type_mismatch"



# ── Sprint 3 WP5: projected retrieval filtering (shadow A/B) ────────────


@pytest.mark.unit
class TestProjectedRetrievalFiltering:
    def test_no_candidates_returns_no_candidates_reason(self, tmp_path) -> None:
        r = project_retrieval_filtering("anything", [], tmp_path)
        assert r["reason"] == "no_candidates"
        assert r["candidates_would_drop"] == []

    def test_never_raises_on_missing_db(self, tmp_path) -> None:
        # tmp_path has no ontology.db -> graceful reason, no exception
        r = project_retrieval_filtering("ISO 14229", [{"evidence_id":"EV-1","snippet":"x"}], tmp_path)
        assert "reason" in r
        assert r["candidates_would_drop"] == []

    def test_projected_filtering_never_mutates_input(self, tmp_path) -> None:
        cands = [{"evidence_id": "EV-1", "snippet": "text"}]
        before = list(cands)
        project_retrieval_filtering("ISO 14229", cands, tmp_path)
        assert cands == before  # input list untouched (read-only)

    def test_returns_structured_metrics_fields(self, tmp_path) -> None:
        r = project_retrieval_filtering("x", [], tmp_path)
        for k in ("enabled", "query_class_ids", "candidates_total",
                  "candidates_would_drop", "evidence_loss_cases",
                  "false_positive_filter_cases", "safe_filter_candidates",
                  "reason"):
            assert k in r
