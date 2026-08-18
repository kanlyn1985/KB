#!/usr/bin/env python3
"""复核队列处理：分类噪声 / 规则重判低置信度 / 输出人工复核清单。

输入：llm_landing/merged_full_records_v04.jsonl 中未归属记录（58,005 条）
处理：
1. 噪声分类（钉钉注释/HTTP错误/纯日期/无实质）→ noise_review.jsonl
2. 规则重判（用 land_units.rule_match 关键词匹配 v0.4 骨架）→ rule_reassigned.jsonl
3. 剩余 → manual_review.jsonl（人工复核清单）

输出目录：llm_landing/review_processing/
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "validation"))

from land_units import rule_match  # noqa: E402

TREE = ROOT / "docs" / "ontology" / "tree_skeleton"
MERGED = TREE / "llm_landing" / "merged_full_records_v04.jsonl"
OUT_DIR = TREE / "llm_landing" / "review_processing"
NOISE = OUT_DIR / "noise_review.jsonl"
RULE = OUT_DIR / "rule_reassigned.jsonl"
MANUAL = OUT_DIR / "manual_review.jsonl"

NOISE_PATTERNS = [
    (re.compile(r"ERROR: HTTP \d+"), "钉钉接口错误"),
    (re.compile(r"unsupported DingTalk|<!--.*-->", re.DOTALL), "钉钉块注释"),
    (re.compile(r"callout", re.I), "callout 块"),
    (re.compile(r"^[\d\s\-年月日周号期版本]+$"), "纯日期/版本号"),
]

NOISE_REASON_KW = ["无实质内容", "无实质技术", "无实质信息", "仅标题", "标题，无实质",
                   "纯标题", "日期信息", "仅日期", "章节标题", "无技术内容", "占位符",
                   "N/A", "无内容", "无信息", "无实质安全机制"]


def is_noise(r: dict) -> tuple[bool, str]:
    text = r.get("text", "")
    reason = r.get("llm_reason", "") or ""
    for pat, label in NOISE_PATTERNS:
        if pat.search(text):
            return True, label
    if any(k in reason for k in NOISE_REASON_KW):
        return True, "LLM判无实质"
    return False, ""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skel = json.loads((TREE / "skeleton_v0.4.json").read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in skel["nodes"]}

    noise_cnt = Counter()
    rule_ok = 0
    manual_cnt = 0
    total = 0

    with NOISE.open("w", encoding="utf-8") as fn, \
         RULE.open("w", encoding="utf-8") as fr, \
         MANUAL.open("w", encoding="utf-8") as fm:
        with MERGED.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("node_id") or r.get("unit_type") == "empty":
                    continue
                total += 1

                # 1. 噪声分类
                is_n, label = is_noise(r)
                if is_n:
                    r["noise_type"] = label
                    fn.write(json.dumps(r, ensure_ascii=False) + "\n")
                    noise_cnt[label] += 1
                    continue

                # 2. 规则重判（文本关键词 → 骨架节点）
                rn, rr, rc = rule_match({"text": r.get("text", ""), "unit_type": r.get("unit_type", "")},
                                        nodes)[:3]
                if rn and rn in nodes and rc >= 0.5:
                    r["node_id"] = rn
                    r["node_name"] = nodes[rn]["name"]
                    r["rule_reason"] = rr
                    r["rule_conf"] = rc
                    fr.write(json.dumps(r, ensure_ascii=False) + "\n")
                    rule_ok += 1
                    continue

                # 3. 人工复核
                fm.write(json.dumps(r, ensure_ascii=False) + "\n")
                manual_cnt += 1

    print(f"复核总数: {total}")
    print(f"噪声: {sum(noise_cnt.values())} ({sum(noise_cnt.values())/total*100:.1f}%)")
    for label, c in noise_cnt.most_common():
        print(f"  {label}: {c}")
    print(f"规则重判成功: {rule_ok} ({rule_ok/total*100:.1f}%)")
    print(f"人工复核: {manual_cnt} ({manual_cnt/total*100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
