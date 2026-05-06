from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .coverage import build_coverage_for_document
from .entities import build_entities_for_document
from .evidence import build_evidence_for_document
from .facts import build_facts_for_document
from .generated_tests import generate_golden_tests_for_document, run_golden_tests_for_document
from .graph import build_graph_for_document
from .ingest import register_document
from .parse import parse_document
from .quality import assess_document_quality
from .wiki_compiler import build_wiki_for_document
from .ambiguity_index import build_ambiguity_index, save_ambiguity_index
from .db import connect


@dataclass(frozen=True)
class PipelineResult:
    doc_id: str
    registered: bool
    deduplicated: bool
    parser_engine: str
    page_count: int
    block_count: int
    overall_score: float
    evidence_count: int
    fact_count: int
    entity_count: int
    wiki_page_count: int
    edge_count: int
    coverage_source_unit_count: int
    coverage_text_rate: float
    coverage_semantic_rate: float
    coverage_object_rate: float
    coverage_test_rate: float
    coverage_uncovered_count: int
    coverage_summary_path: str
    coverage_report_path: str


@dataclass(frozen=True)
class PipelineAndTestResult:
    doc_id: str
    registered: bool
    deduplicated: bool
    parser_engine: str
    page_count: int
    block_count: int
    overall_score: float
    evidence_count: int
    fact_count: int
    entity_count: int
    wiki_page_count: int
    edge_count: int
    golden_case_count: int
    golden_network_case_count: int
    golden_local_case_count: int
    golden_test_success: bool
    golden_test_passed: int
    golden_test_failed: int
    coverage_source_unit_count: int
    coverage_text_rate: float
    coverage_semantic_rate: float
    coverage_object_rate: float
    coverage_test_rate: float
    coverage_uncovered_count: int
    coverage_summary_path: str
    coverage_report_path: str


def run_document_pipeline(workspace_root: Path, doc_id: str) -> PipelineResult:
    parse_result = parse_document(workspace_root, doc_id)
    quality_result = assess_document_quality(workspace_root, doc_id)
    evidence_result = build_evidence_for_document(workspace_root, doc_id)
    facts_result = build_facts_for_document(workspace_root, doc_id)
    entities_result = build_entities_for_document(workspace_root, doc_id)
    wiki_result = build_wiki_for_document(workspace_root, doc_id)
    graph_result = build_graph_for_document(workspace_root, doc_id)
    coverage_result = build_coverage_for_document(workspace_root, doc_id)

    return PipelineResult(
        doc_id=doc_id,
        registered=False,
        deduplicated=False,
        parser_engine=parse_result.parser_engine,
        page_count=parse_result.page_count,
        block_count=parse_result.block_count,
        overall_score=quality_result.overall_score,
        evidence_count=evidence_result.evidence_count,
        fact_count=facts_result.fact_count,
        entity_count=entities_result.entity_count,
        wiki_page_count=wiki_result.page_count,
        edge_count=graph_result.edge_count,
        coverage_source_unit_count=coverage_result.source_unit_count,
        coverage_text_rate=coverage_result.text_coverage_rate,
        coverage_semantic_rate=coverage_result.semantic_coverage_rate,
        coverage_object_rate=coverage_result.object_coverage_rate,
        coverage_test_rate=coverage_result.test_coverage_rate,
        coverage_uncovered_count=sum(coverage_result.uncovered_counts.values()),
        coverage_summary_path=str(coverage_result.summary_path),
        coverage_report_path=str(coverage_result.report_path),
    )


def run_file_pipeline(workspace_root: Path, source_file: Path) -> PipelineResult:
    register_result = register_document(workspace_root, source_file)
    result = run_document_pipeline(workspace_root, register_result.doc_id)
    return PipelineResult(
        doc_id=result.doc_id,
        registered=True,
        deduplicated=register_result.deduplicated,
        parser_engine=result.parser_engine,
        page_count=result.page_count,
        block_count=result.block_count,
        overall_score=result.overall_score,
        evidence_count=result.evidence_count,
        fact_count=result.fact_count,
        entity_count=result.entity_count,
        wiki_page_count=result.wiki_page_count,
        edge_count=result.edge_count,
        coverage_source_unit_count=result.coverage_source_unit_count,
        coverage_text_rate=result.coverage_text_rate,
        coverage_semantic_rate=result.coverage_semantic_rate,
        coverage_object_rate=result.coverage_object_rate,
        coverage_test_rate=result.coverage_test_rate,
        coverage_uncovered_count=result.coverage_uncovered_count,
        coverage_summary_path=result.coverage_summary_path,
        coverage_report_path=result.coverage_report_path,
    )


def run_batch_pipeline(workspace_root: Path, doc_ids: list[str]) -> list[dict[str, object]]:
    return [asdict(run_document_pipeline(workspace_root, doc_id)) for doc_id in doc_ids]


def run_document_pipeline_and_tests(workspace_root: Path, doc_id: str) -> PipelineAndTestResult:
    pipeline_result = run_document_pipeline(workspace_root, doc_id)
    golden_result = generate_golden_tests_for_document(workspace_root, doc_id)
    golden_run = run_golden_tests_for_document(workspace_root, doc_id)
    return PipelineAndTestResult(
        doc_id=pipeline_result.doc_id,
        registered=False,
        deduplicated=False,
        parser_engine=pipeline_result.parser_engine,
        page_count=pipeline_result.page_count,
        block_count=pipeline_result.block_count,
        overall_score=pipeline_result.overall_score,
        evidence_count=pipeline_result.evidence_count,
        fact_count=pipeline_result.fact_count,
        entity_count=pipeline_result.entity_count,
        wiki_page_count=pipeline_result.wiki_page_count,
        edge_count=pipeline_result.edge_count,
        golden_case_count=int(golden_result.get("case_count", 0)),
        golden_network_case_count=int(golden_result.get("network_case_count", 0)),
        golden_local_case_count=int(golden_result.get("local_case_count", 0)),
        golden_test_success=bool(golden_run.get("success", False)),
        golden_test_passed=int(golden_run.get("passed", 0)),
        golden_test_failed=int(golden_run.get("failed", 0)),
        coverage_source_unit_count=pipeline_result.coverage_source_unit_count,
        coverage_text_rate=pipeline_result.coverage_text_rate,
        coverage_semantic_rate=pipeline_result.coverage_semantic_rate,
        coverage_object_rate=pipeline_result.coverage_object_rate,
        coverage_test_rate=pipeline_result.coverage_test_rate,
        coverage_uncovered_count=pipeline_result.coverage_uncovered_count,
        coverage_summary_path=pipeline_result.coverage_summary_path,
        coverage_report_path=pipeline_result.coverage_report_path,
    )


def run_file_pipeline_and_tests(workspace_root: Path, source_file: Path) -> PipelineAndTestResult:
    register_result = register_document(workspace_root, source_file)
    result = run_document_pipeline_and_tests(workspace_root, register_result.doc_id)
    return PipelineAndTestResult(
        doc_id=result.doc_id,
        registered=True,
        deduplicated=register_result.deduplicated,
        parser_engine=result.parser_engine,
        page_count=result.page_count,
        block_count=result.block_count,
        overall_score=result.overall_score,
        evidence_count=result.evidence_count,
        fact_count=result.fact_count,
        entity_count=result.entity_count,
        wiki_page_count=result.wiki_page_count,
        edge_count=result.edge_count,
        golden_case_count=result.golden_case_count,
        golden_network_case_count=result.golden_network_case_count,
        golden_local_case_count=result.golden_local_case_count,
        golden_test_success=result.golden_test_success,
        golden_test_passed=result.golden_test_passed,
        golden_test_failed=result.golden_test_failed,
        coverage_source_unit_count=result.coverage_source_unit_count,
        coverage_text_rate=result.coverage_text_rate,
        coverage_semantic_rate=result.coverage_semantic_rate,
        coverage_object_rate=result.coverage_object_rate,
        coverage_test_rate=result.coverage_test_rate,
        coverage_uncovered_count=result.coverage_uncovered_count,
        coverage_summary_path=result.coverage_summary_path,
        coverage_report_path=result.coverage_report_path,
    )


def build_workspace_ambiguity_index(workspace_root: Path) -> dict[str, int]:
    db_path = workspace_root / "db" / "knowledge.db"
    conn = connect(db_path)
    try:
        index = build_ambiguity_index(conn)
    finally:
        conn.close()
    output_path = workspace_root / "ambiguity_index.json"
    save_ambiguity_index(index, str(output_path))
    return {acronym: len(senses) for acronym, senses in index.items()}
