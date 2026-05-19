from __future__ import annotations

import pytest

from enterprise_agent_kb.ambiguity_index import Sense, build_ambiguity_index, load_ambiguity_index, save_ambiguity_index
from enterprise_agent_kb.query_ambiguity import (
    AMBIGUOUS_ACRONYMS,
    QueryAmbiguity,
    detect_query_ambiguity,
    detect_query_ambiguity_with_kb,
    reload_kb_index,
)
from pathlib import Path
import sqlite3
import tempfile


@pytest.fixture
def kb_connection():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE facts (
            fact_id TEXT PRIMARY KEY,
            fact_type TEXT NOT NULL,
            subject_entity_id TEXT,
            predicate TEXT NOT NULL,
            object_value TEXT,
            object_entity_id TEXT,
            qualifiers_json TEXT,
            confidence REAL,
            fact_status TEXT NOT NULL DEFAULT 'active',
            source_doc_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            alias_json TEXT,
            description TEXT,
            source_confidence REAL,
            entity_status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


class TestAmbiguityIndexBuilder:

    def test_discovers_acronym_from_semicolon_term(self, kb_connection):
        kb_connection.execute(
            "INSERT INTO facts VALUES ('F1','term_definition',NULL,'defines_term',"
            "'{\"term\":\"连接确认功能 connection confirm function; CC\",\"definition\":\"test\"}',"
            "NULL,NULL,0.9,'active','D1','2026-01-01','2026-01-01')"
        )
        kb_connection.execute(
            "INSERT INTO facts VALUES ('F2','term_definition',NULL,'defines_term',"
            "'{\"term\":\"恒流充电 constant current; CC\",\"definition\":\"test2\"}',"
            "NULL,NULL,0.9,'active','D1','2026-01-01','2026-01-01')"
        )
        kb_connection.commit()
        index = build_ambiguity_index(kb_connection)
        assert "CC" in index
        assert len(index["CC"]) >= 2

    def test_removes_single_sense_acronyms(self, kb_connection):
        kb_connection.execute(
            "INSERT INTO facts VALUES ('F1','term_definition',NULL,'defines_term',"
            "'{\"term\":\"唯一术语 unique term; XX\",\"definition\":\"only one\"}',"
            "NULL,NULL,0.9,'active','D1','2026-01-01','2026-01-01')"
        )
        kb_connection.commit()
        index = build_ambiguity_index(kb_connection)
        assert "XX" not in index

    def test_extracts_context_terms_from_cjk(self, kb_connection):
        kb_connection.execute(
            "INSERT INTO facts VALUES ('F1','term_definition',NULL,'defines_term',"
            "'{\"term\":\"连接确认功能 connection confirm function; CC\",\"definition\":\"通过电子方式反映连接状态\"}',"
            "NULL,NULL,0.9,'active','D1','2026-01-01','2026-01-01')"
        )
        kb_connection.execute(
            "INSERT INTO facts VALUES ('F2','term_definition',NULL,'defines_term',"
            "'{\"term\":\"恒流充电 constant current; CC\",\"definition\":\"电流保持恒定\"}',"
            "NULL,NULL,0.9,'active','D1','2026-01-01','2026-01-01')"
        )
        kb_connection.commit()
        index = build_ambiguity_index(kb_connection)
        for sense in index["CC"]:
            assert len(sense.context_terms) > 0

    def test_persist_and_reload(self, kb_connection, tmp_path):
        kb_connection.execute(
            "INSERT INTO facts VALUES ('F1','term_definition',NULL,'defines_term',"
            "'{\"term\":\"连接确认功能; CC\",\"definition\":\"test\"}',"
            "NULL,NULL,0.9,'active','D1','2026-01-01','2026-01-01')"
        )
        kb_connection.execute(
            "INSERT INTO facts VALUES ('F2','term_definition',NULL,'defines_term',"
            "'{\"term\":\"恒流; CC\",\"definition\":\"test2\"}',"
            "NULL,NULL,0.9,'active','D1','2026-01-01','2026-01-01')"
        )
        kb_connection.commit()
        index = build_ambiguity_index(kb_connection)
        path = tmp_path / "test_index.json"
        save_ambiguity_index(index, str(path))
        loaded = load_ambiguity_index(str(path))
        assert "CC" in loaded
        assert len(loaded["CC"]) == len(index["CC"])


class TestDetectQueryAmbiguityWithKb:

    def test_manual_registry_still_works(self):
        result = detect_query_ambiguity("CC是什么意思")
        assert result is not None
        assert result.anchor == "CC"
        assert len(result.options) >= 2

    def test_context_disambiguates(self):
        result = detect_query_ambiguity("充电接口里的CC连接确认是什么意思")
        assert result is None

    def test_non_acronym_not_ambiguous(self):
        result = detect_query_ambiguity("充电模式是什么意思")
        assert result is None

    def test_with_context_passes_through(self):
        result = detect_query_ambiguity_with_kb("充电接口里的CC连接确认是什么意思")
        assert result is None

    def test_no_kb_index_falls_back_to_manual(self):
        reload_kb_index("/nonexistent/path.json")
        result = detect_query_ambiguity_with_kb("CC是什么意思")
        assert result is not None
        assert result.anchor == "CC"


class TestManualRegistryCoverage:

    def test_cc_has_two_real_senses(self):
        assert "CC" in AMBIGUOUS_ACRONYMS
        non_other = [o for o in AMBIGUOUS_ACRONYMS["CC"] if o.option_id != "other_context"]
        assert len(non_other) >= 2

    def test_cp_has_two_real_senses(self):
        assert "CP" in AMBIGUOUS_ACRONYMS
        non_other = [o for o in AMBIGUOUS_ACRONYMS["CP"] if o.option_id != "other_context"]
        assert len(non_other) >= 2

    def test_pe_has_at_least_one_sense(self):
        assert "PE" in AMBIGUOUS_ACRONYMS
        assert len(AMBIGUOUS_ACRONYMS["PE"]) >= 1
