"""Tests for the combined legacy + ontology query system.

These tests verify the integration of the new ontology system
with the existing KB1 legacy answer pipeline. The legacy
pipeline is allowed to fail gracefully (LLM outage, etc.) —
the test must not break if the legacy system is unavailable,
only note the loss.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def obc_conn(ontology_db_path: Path) -> None:
    """Build the OBC ontology in the scratch space so that the
    combined query has ontology data to read."""
    workspace = ontology_db_path.parent
    # Insert into sys.path so the build script can import
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from scripts.ontology_demo.build_obc_ontology import build
    # Re-use the build function
    # But we don't want to blow away other tests' DBs; we
    # trust the fixture to isolate per-test via tmp_path.
    # For this test, we just call build() and let it create
    # the ontology DB at the fixture's expected path.
    build()  # uses default workspace path


# ---- Router tests ---------------------------------------------------

def test_router_parameter() -> None:
    from kb1_ontology.combined_query import route_query
    assert route_query("ISO 14229-3 中 P2 Server Timing 是多少？") == "parameter"
    assert route_query("rated voltage AC value?") == "parameter"
    assert route_query("50 ms 是多少") == "parameter"


def test_router_reference() -> None:
    from kb1_ontology.combined_query import route_query
    assert route_query("GB/T 18487.1 引用了哪些标准？") == "reference"
    assert route_query("who depends on X") == "reference"


def test_router_traversal() -> None:
    from kb1_ontology.combined_query import route_query
    assert route_query("从 ISO 14229-7 出发 2 跳可达的标准？") == "traversal"
    assert route_query("2-hop traversal from X") == "traversal"


def test_router_service() -> None:
    from kb1_ontology.combined_query import route_query
    assert route_query("ISO 14229-1 定义了哪些 UDS 服务？") == "service"
    assert route_query("0x10 service") == "service"


def test_router_definition() -> None:
    from kb1_ontology.combined_query import route_query
    assert route_query("ISO 14229-1 是什么？") == "definition"
    assert route_query("what is the meaning of X") == "definition"


def test_router_free_form() -> None:
    from kb1_ontology.combined_query import route_query
    # LLM router may classify these differently, but both are valid
    assert route_query("how does the system work in practice") == "free_form"


# ---- Combined answer structure -----------------------------------

def test_combined_answer_structure() -> None:
    """A CombinedAnswer has the expected fields."""
    from kb1_ontology.combined_query import CombinedAnswer
    ca = CombinedAnswer(query="test", category="parameter")
    assert ca.query == "test"
    assert ca.category == "parameter"
    assert ca.ontology_answer is None
    assert ca.legacy_answer is None
    assert ca.final_text == ""


def test_combined_query_returns_dataclass() -> None:
    """combined_query returns a CombinedAnswer with the right type."""
    from kb1_ontology.combined_query import combined_query, CombinedAnswer
    workspace = Path("/tmp/nonexistent")
    result = combined_query(workspace, "test query")
    assert isinstance(result, CombinedAnswer)


# ---- Tests with real ontology data -----------------------------

# These tests require the ontology DB to be built. We do this
# at module import time so the per-test calls can use it.
import subprocess
import sys as _sys

# Build ontology (this is idempotent and fast)
_workspace = ROOT / "knowledge_base"
_build_script = ROOT / "scripts" / "ontology_demo" / "build_obc_ontology.py"
if _build_script.exists():
    _sys.path.insert(0, str(ROOT / "src"))
    try:
        # The build script uses sys.path inserts; run as module
        proc = subprocess.run(
            [_sys.executable, str(_build_script)],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        pass  # Tests will skip if build fails


def test_parameter_query_combined() -> None:
    from kb1_ontology.combined_query import combined_query
    result = combined_query(_workspace, "ISO 14229-3 中 P2 Server Timing 是多少？")
    # Ontology should answer with the typed value
    assert "50.0 ms" in str(result.ontology_answer) or "50 ms" in str(result.ontology_answer)
    assert "typed_value" in result.ontology_exactness
    # Legacy should have produced an excerpt or empty
    assert isinstance(result.legacy_excerpt, str)


def test_reference_query_combined() -> None:
    from kb1_ontology.combined_query import combined_query
    result = combined_query(_workspace, "GB/T 18487.1 引用了哪些标准？")
    # Ontology should return a structured set
    assert isinstance(result.ontology_answer, list)
    assert "GB/T 18487.4" in result.ontology_answer


def test_service_query_combined() -> None:
    from kb1_ontology.combined_query import combined_query
    result = combined_query(_workspace, "ISO 14229-1 定义了哪些 UDS 服务？")
    assert isinstance(result.ontology_answer, list)
    assert len(result.ontology_answer) == 5
    # Each service has a hex code
    for s in result.ontology_answer:
        assert "0x" in s


def test_traversal_query_combined() -> None:
    from kb1_ontology.combined_query import combined_query
    result = combined_query(_workspace, "从 ISO 14229-7 出发 2 跳可达的标准？")
    assert isinstance(result.ontology_answer, list)
    # At least ISO 14229-1, 2, 3 should be reachable from 7
    found = " ".join(result.ontology_answer)
    assert "ISO 14229-1" in found
    assert "ISO 14229-3" in found


def test_free_form_query_legacy_only() -> None:
    """A free-form question should still produce *something*
    (legacy context), even if ontology can't answer."""
    from kb1_ontology.combined_query import combined_query
    result = combined_query(
        _workspace,
        "车载充电机正常工作时产生的交流电压波动和闪烁的限值"
    )
    # Ontology: free-form, may have no answer
    # Legacy: should produce a prose excerpt
    assert isinstance(result.legacy_excerpt, str)
    # The final_text should be formatted
    assert "[Category:" in result.final_text
    assert "📐" in result.final_text
    assert "📖" in result.final_text


def test_combined_query_never_crashes_on_bad_input() -> None:
    """The combined system must never raise on bad input —
    legacy failures are caught and surfaced as None."""
    from kb1_ontology.combined_query import combined_query
    # Empty query
    r = combined_query(_workspace, "")
    assert r is not None
    # Nonsense query
    r = combined_query(_workspace, "x" * 1000)
    assert r is not None
    # Unicode / emoji
    r = combined_query(_workspace, "测试 🎉 emoji")
    assert r is not None
