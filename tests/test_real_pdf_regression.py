from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_agent_kb.pipeline import run_document_pipeline
from enterprise_agent_kb.answer_api import answer_query


REAL_PDF = Path(
    r"E:\AI_Project\opencode_workspace\KB1\knowledge_base\raw\GB_T 18487.5-2024 电动汽车传导充电系统   第5部分：用于GB_T 20234.3直流充电系统.pdf"
)


@pytest.mark.integration
def test_real_pdf_pipeline_regression() -> None:
    if not REAL_PDF.exists():
        pytest.skip("real PDF not available")

    workspace = Path("knowledge_base")
    result = run_document_pipeline(workspace, "DOC-000004")

    assert result.page_count >= 10
    assert result.evidence_count >= 10
    assert result.fact_count >= 4
    assert result.entity_count >= 2
    assert result.edge_count >= 1

    answer = answer_query(workspace, "GB/T 18487.5—2024", limit=6)
    assert "GB/T 18487.5—2024" in answer["direct_answer"] or "GB/T 18487.5—2024" in "\n".join(answer["summary"])
