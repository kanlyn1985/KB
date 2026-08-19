#!/usr/bin/env python3
"""answer-query：Context Pack → 最终答案生成（链路最后一环）。

流程：query_production_store（检索+打包）→ LLM 基于 Context Pack 生成答案。
- 证据判定 sufficient → answer_with_evidence
- partial → answer_with_caution_and_disclose_gaps（答案标注不确定）
- insufficient → abstain（不编造）

用法：
  agent-kb answer-query --db node-index.sqlite3 --query "OBC水道设计" \
      --domain-dir domains/obc_dcdc [--llm-understanding] [--max-answer-chars 2000]
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.pipeline.production_context import query_production_store  # noqa: E402
from agent_kb.query.understanding import UnderstandingOptions  # noqa: E402

# LLM 调用（validation/llm_client.py，网关 EVT/deepseek-v4-flash）
_LLM_AVAILABLE = False
try:
    _client_path = ROOT / "validation" / "llm_client.py"
    if _client_path.exists():
        _spec = importlib.util.spec_from_file_location("kb_llm_client", _client_path)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        chat = _mod.chat
        _LLM_AVAILABLE = True
except Exception:  # noqa: BLE001
    chat = None  # type: ignore[assignment]

ANSWER_SYSTEM_PROMPT = """你是汽车电子（OBC/DCDC）知识库助手。基于提供的检索上下文回答用户问题。

规则：
1. 只依据提供的检索内容作答，禁止编造事实、数字、标准。
2. 证据不足时明确说"知识库中未找到相关信息"，不要猜测。
3. 用中文回答，结构清晰（分点/小节），技术术语保留原文。
4. 若检索内容包含具体数值/标准（如壁厚、压降、标准编号），原样引用并注明出处节点。
5. 若判定为 insufficient（证据不足），直接回复无法回答并说明原因。"""


def _build_answer_prompt(query: str, context_pack, judgement_status: str) -> str:
    """把 Context Pack 组装成答案生成的 prompt。"""
    card_texts = []
    for card in context_pack.retrieval_cards:
        content = getattr(card, "search_text", "") or ""
        card_texts.append(f"【节点 {card.object_id}】{card.title}\n{content[:1500]}")
    evidence_texts = [e.snippet[:300] for e in context_pack.evidence[:8]]
    facts_texts = []
    for fact in context_pack.facts:
        facts_texts.append(f"- {fact.subject}: {str(fact.object_value)[:200]}")

    sections = [
        f"用户问题: {query}",
        f"证据判定: {judgement_status}",
        "",
        "检索到的节点内容:",
        "\n".join(card_texts) if card_texts else "（无检索卡）",
        "",
        "事实:",
        "\n".join(facts_texts) if facts_texts else "（无事实）",
        "",
        "证据片段:",
        "\n".join(evidence_texts) if evidence_texts else "（无证据）",
    ]
    return "\n".join(sections)


def answer_query(
    query: str,
    *,
    db_path: str | Path,
    domain_dir: Path | None = None,
    use_llm_understanding: bool = False,
    max_answer_chars: int = 2000,
) -> dict:
    """端到端问答：检索 → 打包 → 生成答案。"""
    domain_pack = load_domain_pack(domain_dir) if domain_dir else None
    result = query_production_store(
        query,
        db_path=db_path,
        domain_pack=domain_pack,
        understanding_options=UnderstandingOptions(use_llm=use_llm_understanding),
        retrieval_top_k=10,
    )
    judgement = result.evidence_judgement
    status = judgement.status

    answer: str | None = None
    abstain_reason: str | None = None
    if status == "insufficient" or not _LLM_AVAILABLE:
        abstain_reason = (
            "LLM 网关不可用" if not _LLM_AVAILABLE
            else "证据不足（insufficient），不编造答案"
        )
    else:
        prompt = _build_answer_prompt(query, result.context_pack, status)
        try:
            answer = chat(
                prompt,
                system=ANSWER_SYSTEM_PROMPT,
                max_tokens=max_answer_chars,
                timeout=120,
                retries=2,
            )
        except Exception as e:  # noqa: BLE001
            abstain_reason = f"答案生成失败: {e}"

    return {
        "query": query,
        "answer": answer,
        "abstain_reason": abstain_reason,
        "evidence_status": status,
        "evidence_score": judgement.score,
        "evidence_reasons": judgement.reasons,
        "target_objects": [o.object_id for o in result.context_pack.target_objects],
        "used_llm_understanding": result.query_frame.used_llm,
        "run_id": result.run_id,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--domain-dir", type=Path)
    parser.add_argument("--llm-understanding", action="store_true")
    parser.add_argument("--max-answer-chars", type=int, default=2000)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    result = answer_query(
        args.query,
        db_path=args.db,
        domain_dir=args.domain_dir,
        use_llm_understanding=args.llm_understanding,
        max_answer_chars=args.max_answer_chars,
    )
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
