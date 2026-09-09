#!/usr/bin/env python3
"""落位质量审计：抽样落位记录 → LLM 判定归属正确性 → 规则精确率报告。

用法：
    python3 audit_landing.py --category ME --sample-per-rule 6 --max-docs 200

原理：
1. 从 manifest 抽样文档 → extract_units 提取单元 → rule_match 落位
2. 按规则分组，每组最多抽 sample-per-rule 条记录
3. 调用 MiniMax (Anthropic 兼容) 判定每条 (text, node) 归属是否正确
4. 输出：每规则精确率 + 整体精确率 + 错误样例（供修规则）

判定 prompt 要求 LLM 只输出 JSON：{"correct": true|false, "reason": "..."}
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "validation"))

from extract_units import extract_md, extract_docx, extract_xlsx, extract_pdf  # noqa: E402
from land_units import MANIFEST, load_skeleton, rule_match  # noqa: E402
from llm_client import chat, extract_json, USAGE  # noqa: E402


def llm_judge(env: dict[str, str], text: str, node_id: str, node_name: str, rule: str) -> dict:
    """调用 zcode 主模型（deepseek-v4-pro-0813）判定一条归属记录是否正确。"""
    prompt = f"""不要输出思考过程，直接给出最终 JSON 答案。
你是知识库落位质量审计员。判断以下内容单元归属到骨架节点是否合理。

骨架节点: {node_id} {node_name}
落位规则: {rule}
内容单元文本: {text[:400]}

判定归属是否合理。输出 JSON 且只输出 JSON:
{{"correct": true或false, "reason": "一句话理由（中文）"}}"""
    try:
        raw = chat(prompt, max_tokens=512, timeout=120)
    except RuntimeError as e:
        return {"correct": None, "reason": f"LLM 调用失败: {e}"}
    parsed = extract_json(raw)
    if isinstance(parsed, dict):
        return parsed
    return {"correct": None, "reason": f"LLM 输出无法解析: {raw[:100]}"}


def extract_units_for(d: dict) -> list[dict]:
    p = Path(d["path"])
    try:
        if p.suffix == ".md":
            return extract_md(p)
        if p.suffix == ".docx":
            return extract_docx(p)
        if p.suffix == ".xlsx":
            return extract_xlsx(p)
        if p.suffix == ".pdf":
            return extract_pdf(p)
    except Exception:  # noqa: BLE001
        return []
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", default="ME")
    parser.add_argument("--sample-per-rule", type=int, default=6)
    parser.add_argument("--max-docs", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="只抽样不调 LLM（打印待审清单）")
    args = parser.parse_args()

    env = load_env()
    nodes = load_skeleton()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = [d for d in manifest["docs"] if d.get("category") == args.category]

    random.seed(args.seed)
    sampled_docs = random.sample(docs, min(args.max_docs, len(docs)))

    # 收集落位记录（按规则分组）
    records_by_rule: dict[str, list[dict]] = defaultdict(list)
    for d in sampled_docs:
        for u in extract_units_for(d):
            if u.get("unit_type") == "noise":
                continue
            res = rule_match(u, nodes)
            node_id, rule, conf = res[0], res[1], res[2]
            if not node_id:
                continue
            records_by_rule[rule].append({
                "doc": d["name"],
                "text": u.get("text", "")[:300],
                "unit_type": u.get("unit_type"),
                "node_id": node_id,
                "node_name": nodes[node_id]["name"] if node_id in nodes else None,
                "rule": rule,
                "conf": conf,
            })

    # 每规则抽样
    sample: list[dict] = []
    for rule, recs in sorted(records_by_rule.items(), key=lambda kv: -len(kv[1])):
        random.shuffle(recs)
        sample.extend(recs[: args.sample_per_rule])

    print(f"抽样文档 {len(sampled_docs)} | 落位记录 {sum(len(v) for v in records_by_rule.values())} | 待审 {len(sample)}")

    if args.dry_run:
        out = ROOT / "docs" / "ontology" / "tree_skeleton" / "audit_sample.json"
        out.write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"dry-run: 待审清单已写入 {out}")
        return 0

    # LLM 判定
    results = []
    for i, rec in enumerate(sample, 1):
        verdict = llm_judge(env, rec["text"], rec["node_id"], rec["node_name"] or "", rec["rule"])
        rec["verdict"] = verdict
        results.append(rec)
        status = "✅" if verdict.get("correct") else ("❌" if verdict.get("correct") is False else "❓")
        print(f"[{i}/{len(sample)}] {status} {rec['rule']}: {rec['text'][:40]} -> {rec['node_id']} | {verdict.get('reason','')[:60]}")
        if (i % 20) == 0:
            # 中间保存
            _save(results)

    _save(results)
    report(results)
    print(f"\nLLM 用量: {json.dumps(USAGE, ensure_ascii=False)}")
    return 0


def _save(results: list[dict]) -> None:
    out = ROOT / "docs" / "ontology" / "tree_skeleton" / "audit_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


def report(results: list[dict]) -> None:
    by_rule: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        v = r.get("verdict", {}).get("correct")
        if v is not None:
            by_rule[r["rule"]].append(bool(v))
    total = sum(len(v) for v in by_rule.values())
    correct = sum(sum(v) for v in by_rule.values())
    print("\n" + "=" * 70)
    print(f"整体精确率: {correct}/{total} = {correct / max(total, 1) * 100:.1f}%")
    print("-" * 70)
    rows = sorted(by_rule.items(), key=lambda kv: -len(kv[1]))
    for rule, verdicts in rows:
        acc = sum(verdicts) / len(verdicts) * 100
        flag = "⚠️" if acc < 60 else ("🟡" if acc < 80 else "✅")
        print(f"{flag} {rule:32s} {len(verdicts):2d}条  精确率 {acc:5.1f}%")
    print("=" * 70)
    print("错误样例（供修规则）:")
    for r in results:
        if r.get("verdict", {}).get("correct") is False:
            print(f"  ❌ {r['rule']} | {r['text'][:50]} -> {r['node_id']}")
            print(f"     {r['verdict'].get('reason','')[:80]}")


if __name__ == "__main__":
    sys.exit(main())
