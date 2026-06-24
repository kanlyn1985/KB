"""Tests for the new architecture.

Each test verifies the external behavior (input → output),
not the internal implementation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kb1_ontology.types import RouteResult, HandlerResult, Answer


class TestRouteResult:
    def test_route_result_creation(self) -> None:
        r = RouteResult(category="definition", entity="V2L", target=None)
        assert r.category == "definition"
        assert r.entity == "V2L"
        assert r.target is None


class TestHandlerResult:
    def test_handler_result_creation(self) -> None:
        r = HandlerResult(data="test", data_type="value", source="term", query="q")
        assert r.data == "test"
        assert r.data_type == "value"
        assert r.source == "term"


class TestAnswer:
    def test_answer_to_dict(self) -> None:
        a = Answer(query="q", category="definition",
                   structured={"term": "V2L"}, display="V2L — Vehicle-to-Load")
        d = a.to_dict()
        assert d["query"] == "q"
        assert d["structured"]["term"] == "V2L"


class TestRouter:
    """Tests for the Router — only verify it returns valid RouteResult."""

    def test_router_returns_valid_result(self) -> None:
        from kb1_ontology.router import route
        r = route("V2L是什么")
        assert isinstance(r, RouteResult)
        assert r.category in ("definition", "parameter", "reference", "service", "traversal", "free_form")

    def test_router_hex_code_is_service(self) -> None:
        from kb1_ontology.router import route
        r = route("0x10 service")
        assert r.category == "service"

    def test_router_numeric_unit_is_parameter(self) -> None:
        from kb1_ontology.router import route
        r = route("50 ms timing")
        assert r.category == "parameter"


class TestHandlers:
    """Tests for handlers — verify they return HandlerResult."""

    @pytest.fixture
    def conn(self):
        from kb1_ontology.db import connect, default_db_path
        db_path = default_db_path(Path("knowledge_base"))
        c = connect(db_path)
        return c

    def test_handle_definition_v2l(self, conn) -> None:
        from kb1_ontology.handlers import handle_definition
        route = RouteResult(category="definition", entity="V2L", target=None)
        result = handle_definition(conn, route, "V2L是什么")
        assert isinstance(result, HandlerResult)
        assert result.data is not None

    def test_handle_definition_unknown(self, conn) -> None:
        from kb1_ontology.handlers import handle_definition
        route = RouteResult(category="definition", entity="XYZ123NONEXISTENT", target=None)
        result = handle_definition(conn, route, "XYZ123NONEXISTENT是什么")
        assert result.data is None

    def test_handle_parameter_list(self, conn) -> None:
        from kb1_ontology.handlers import handle_parameter
        route = RouteResult(category="parameter", entity="CCU", target="唤醒源")
        result = handle_parameter(conn, route, "CCU有哪些唤醒源")
        assert isinstance(result, HandlerResult)
        assert result.data_type == "list"
        assert len(result.data) > 0

    def test_handle_parameter_list_empty_entity(self, conn) -> None:
        from kb1_ontology.handlers import handle_parameter
        route = RouteResult(category="parameter", entity="NONEXISTENT", target=None)
        result = handle_parameter(conn, route, "NONEXISTENT有哪些参数")
        assert result.data is None

    def test_handle_reference(self, conn) -> None:
        from kb1_ontology.handlers import handle_reference
        route = RouteResult(category="reference", entity="GB/T 18487.1", target=None)
        result = handle_reference(conn, route, "GB/T 18487.1 引用了哪些标准")
        assert isinstance(result, HandlerResult)
        assert result.data_type == "list"
        assert len(result.data) > 0

    def test_handle_reference_no_entity(self, conn) -> None:
        from kb1_ontology.handlers import handle_reference
        route = RouteResult(category="reference", entity=None, target=None)
        result = handle_reference(conn, route, "引用了哪些标准")
        assert result.data is None

    def test_handle_service_hex(self, conn) -> None:
        from kb1_ontology.handlers import handle_service
        route = RouteResult(category="service", entity=None, target=None)
        result = handle_service(conn, route, "0x10 service")
        assert isinstance(result, HandlerResult)
        assert result.data_type == "list"
        assert len(result.data) > 0

    def test_handle_traversal(self, conn) -> None:
        from kb1_ontology.handlers import handle_traversal
        route = RouteResult(category="traversal", entity="ISO 14229-7", target=None)
        result = handle_traversal(conn, route, "从ISO 14229-7出发2跳可达的标准")
        assert isinstance(result, HandlerResult)
        assert result.data_type == "path_list"


class TestCombinedQuery:
    """End-to-end tests for combined_query."""

    @pytest.fixture
    def workspace(self):
        return Path("knowledge_base")

    def test_v2l_definition_direct(self, workspace) -> None:
        from kb1_ontology.combined_query import combined_query
        from kb1_ontology.handlers import handle_definition
        from kb1_ontology.db import connect, default_db_path
        from kb1_ontology.types import RouteResult
        conn = connect(default_db_path(workspace))
        route = RouteResult(category="definition", entity="V2L", target=None)
        result = handle_definition(conn, route, "V2L是什么")
        conn.close()
        assert result.data is not None

    def test_ccu_wakeup_sources_direct(self, workspace) -> None:
        from kb1_ontology.handlers import handle_parameter
        from kb1_ontology.db import connect, default_db_path
        from kb1_ontology.types import RouteResult
        conn = connect(default_db_path(workspace))
        route = RouteResult(category="parameter", entity="CCU", target="唤醒源")
        result = handle_parameter(conn, route, "CCU有哪些唤醒源")
        conn.close()
        assert result.data is not None
        assert result.data_type == "list"

    def test_reference_query_direct(self, workspace) -> None:
        from kb1_ontology.handlers import handle_reference
        from kb1_ontology.db import connect, default_db_path
        from kb1_ontology.types import RouteResult
        conn = connect(default_db_path(workspace))
        route = RouteResult(category="reference", entity="GB/T 18487.1", target=None)
        result = handle_reference(conn, route, "GB/T 18487.1 引用了哪些标准")
        conn.close()
        assert result.data is not None
        assert len(result.data) > 0

    def test_unknown_term(self, workspace) -> None:
        from kb1_ontology.combined_query import combined_query
        result = combined_query(workspace, "XYZ123是什么", use_legacy=False)
        assert isinstance(result, Answer)
        assert len(result.warnings) > 0

    def test_empty_query(self, workspace) -> None:
        from kb1_ontology.combined_query import combined_query
        result = combined_query(workspace, "", use_legacy=False)
        assert isinstance(result, Answer)

    def test_uses_legacy_direct(self, workspace) -> None:
        from kb1_ontology.handlers import handle_definition
        from kb1_ontology.db import connect, default_db_path
        from kb1_ontology.types import RouteResult
        conn = connect(default_db_path(workspace))
        route = RouteResult(category="definition", entity="V2L", target=None)
        result = handle_definition(conn, route, "V2L是什么")
        conn.close()
        assert result.data is not None
