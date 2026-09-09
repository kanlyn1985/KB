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

ROOT = Path(__file__).resolve().parents[3]  # agent_kb_core/
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

ANSWER_SYSTEM_PROMPT = """你是汽车电子（OBC/DCDC）领域的资深工程师，基于知识库检索上下文回答用户问题。

【回答格式】
1. 直接给出结论，禁止以"根据知识库中的检索结果"这类话开头，不要复述检索过程。
2. 先给核心答案（1-3 句结论），再用要点分条展开细节，最后统一列出引用出处。
3. 回答中出现的每个具体数值/标准/参数，若来自知识库必须标注来源节点，格式：【节点 节点ID】。
4. 用中文回答，技术术语与英文缩写保留原文（如 ripple、Flotherm、ISO 26262）。

【证据使用规则】
5. 只依据提供的检索内容作答，禁止编造事实、数字、标准、节点。
6. 检索内容中有具体数值/标准时，**必须原样给出并注明出处**，即使证据判定是 partial——
   有数值就给数值，同时指出其上下文限制（如"该值出现在性能指标汇总中，未注明测试条件"），
   不得因为 partial 就说"未找到"。
7. 不要反问用户补充信息、不要索要更多输入、不要以提问结尾。

【知识库缺失时的通用知识补充】
8. 当检索内容中没有直接答案时，不要只说"未找到"就结束——先用领域通用知识（行业惯例、
   典型设计方法、常见参数范围、标准体系常识）给出**有实用价值**的回答，但必须遵守：
   a. 通用知识部分与知识库内容明确分开：用"**通用知识补充（非知识库内容）**"小节标注；
   b. 通用知识中不得编造精确数值/标准号/参数值冒充知识库数据——常识性范围可以给
      （如"典型 OBC 输出纹波通常在 50~100 mVpp 量级"），但必须注明"具体以项目规格书为准"；
   c. 若检索内容与问题完全无关（如查发动机机油却只命中 CAN 通信），说明"知识库未收录相关内容"，
      再按 (a)(b) 用通用知识补充；
   d. 回答末尾的"出处"小节只列知识库节点；通用知识部分不列入出处，保持来源可追溯。

【结构建议】
- 需要多要点时用 Markdown 分节（## / - / 1.），单点问题直接一两段回答。
- 结尾用"**出处**"小节列出引用的节点 ID（每个一行）；若无知识库引用则写"（无）"。

【多子问题拆解】
9. 用户问题含多个子问题（如"壁厚多少？收缩率多少？阈值多少？"）时，**必须逐个子问题分节回答**，
   每个子问题给出：明确结论 → 量化数值/范围 → 依据与限制。禁止只回答一部分或合并含糊带过。
10. 工程设计咨询类问题（选型、壁厚、公差、工艺参数）允许引用行业标准体系作为通用知识
    （如 ISO 8062/GB/T 6414 铸件公差、GB/T 15115 压铸铝合金、ISO 2768 一般公差），
    引用标准时给出标准号+适用场景，并注明"具体等级以图纸要求为准"。
11. 判定类问题（如"变形量多少算不合格"）应给出**分级判断策略**：基础参考值 → 判定依据
    （标准/公差带）→ 按功能分区（关键区/非关键区）不同阈值 → 实际操作建议（如与 CAD 比对、偏差分布图）。
12. 通用知识给出的推荐值必须带区间或量级（如"2.5~3.5mm""0.4%~0.6%"），
    禁止只给单一精确值而没有任何上下文；同时说明影响因素与验证手段（试模/模流分析/首件检测）。"""


SUMMARIZE_SYSTEM_PROMPT = """你是知识库内容压缩器。把每张节点卡的长内容压缩成紧凑摘要，供下游回答使用。

要求：
1. 逐张处理输入卡片，保留与工程相关的全部信息，特别是：
   - 所有具体数值、参数、单位（如 2.8mm、≤100 mV、95%）
   - 标准编号、规格号、客户要求（如 ISO 26262、GB/T 40432）
   - 关键设计决策、约束条件、因果逻辑
2. 丢弃：重复表述、表格装饰、清单罗列噪声、与工程无关的叙述。
3. 输出格式（必须严格遵循，每张卡一段，节点 ID 原样）：
   【节点 节点ID】摘要内容
4. 摘要用中文，技术术语保留原文；总长度控制在每卡 400~700 字。"""


def _summarize_long_cards(long_cards: list[tuple[str, str]]) -> dict[str, str]:
    """用 LLM 把超长卡内容压缩成摘要（保留数值/标准，不截断丢弃）。

    long_cards: [(node_id, content), ...] 仅含超过阈值的卡。
    返回 {node_id: summary}；LLM 失败时回退原截断（保底可用）。
    """
    if not long_cards or not _LLM_AVAILABLE:
        return {}
    block = "\n\n".join(f"【节点 {nid}】\n{content}" for nid, content in long_cards)
    user = f"请压缩以下节点卡内容：\n\n{block}"
    try:
        raw = chat(user, system=SUMMARIZE_SYSTEM_PROMPT, max_tokens=2048, timeout=120, retries=2)
    except Exception:  # noqa: BLE001  网关故障 → 回退截断
        return {}
    if not raw:
        return {}
    summaries: dict[str, str] = {}
    current = ""
    current_id = ""
    for line in raw.splitlines():
        if line.startswith("【节点 "):
            if current_id:
                summaries[current_id] = current.strip()
            rest = line[len("【节点 "):]
            current_id = rest.split("】", 1)[0].strip()
            current = rest.split("】", 1)[1].strip() if "】" in rest else ""
        else:
            current += "\n" + line
    if current_id:
        summaries[current_id] = current.strip()
    return summaries


def _build_answer_prompt(
    query: str,
    context_pack,
    judgement_status: str,
    card_summaries: dict[str, str] | None = None,
) -> str:
    """把 Context Pack 组装成答案生成的 prompt。

    上下文按"节点卡（主内容）→ 证据片段（原文）→ 事实（结构）"组织，
    每段标注来源节点，让 LLM 能直接引用。
    超长卡内容由调用方预先 LLM 总结（card_summaries），避免硬截断丢关键数值。
    """
    card_summaries = card_summaries or {}
    card_texts = []
    for card in context_pack.retrieval_cards:
        content = getattr(card, "search_text", "") or ""
        nid = card.object_id
        if nid in card_summaries:
            card_texts.append(f"【节点 {nid}】{card.title}（压缩摘要）\n{card_summaries[nid]}")
        else:
            card_texts.append(f"【节点 {nid}】{card.title}\n{content[:1400]}")
    evidence_texts = []
    for e in context_pack.evidence[:10]:
        src = getattr(e, "document_id", "") or ""
        evidence_texts.append(f"[证据] {src}\n{e.snippet[:400]}")
    facts_texts = []
    for fact in context_pack.facts:
        facts_texts.append(f"- [{fact.fact_type}] {fact.subject}: {str(fact.object_value)[:250]}")

    sections = [
        f"用户问题: {query}",
        f"证据判定: {judgement_status}",
        "",
        "===== 节点内容（主要依据） =====",
        "\n".join(card_texts) if card_texts else "（无检索卡）",
        "",
        "===== 证据片段（原文摘录） =====",
        "\n".join(evidence_texts) if evidence_texts else "（无证据）",
        "",
        "===== 事实 =====",
        "\n".join(facts_texts) if facts_texts else "（无事实）",
    ]
    return "\n".join(sections)


def answer_query(
    query: str,
    *,
    db_path: str | Path,
    domain_dir: Path | None = None,
    use_llm_understanding: bool = False,
    max_answer_chars: int = 2000,
    embedding_provider=None,
) -> dict:
    """端到端问答：检索 → 打包 → 生成答案。"""
    domain_pack = load_domain_pack(domain_dir) if domain_dir else None
    result = query_production_store(
        query,
        db_path=db_path,
        domain_pack=domain_pack,
        understanding_options=UnderstandingOptions(use_llm=use_llm_understanding),
        retrieval_top_k=10,
        embedding_provider=embedding_provider,
    )
    judgement = result.evidence_judgement
    status = judgement.status

    answer: str | None = None
    abstain_reason: str | None = None
    if not _LLM_AVAILABLE:
        abstain_reason = "LLM 网关不可用"
    else:
        # 超长卡内容先 LLM 总结压缩（保留数值/标准，不硬截断），再组装最终 prompt
        LONG_CARD_THRESHOLD = 1400
        long_cards = [
            (card.object_id, getattr(card, "search_text", "") or "")
            for card in result.context_pack.retrieval_cards
            if len(getattr(card, "search_text", "") or "") > LONG_CARD_THRESHOLD
        ]
        summaries = _summarize_long_cards(long_cards)
        prompt = _build_answer_prompt(query, result.context_pack, status, summaries)
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
