#!/usr/bin/env python3
"""工程复核内容二次筛选：LLM 判断哪些值得人工审核（EVT/deepseek-v4-flash）。

输入：review_processing/manual_review_engineering.jsonl（10,774 条）
判定：每条 → worth_review: true/false + reason
  true  = 含实质工程信息（参数/方法/问题/结论），缺失上下文但可恢复，人工审核有意义
  false = 纯标题/文件名/章节名（无正文）、无信息碎片、重复建议、空泛内容

输出：review_processing/triage/
  triage_records.jsonl   判定明细（含 worth_review）
  worth_review.jsonl     值得人工审核（导出 Excel 用）
  not_worth.jsonl        不值得（归档）
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "validation"))

from llm_client import chat, extract_json, USAGE  # noqa: E402

TREE = ROOT / "docs" / "ontology" / "tree_skeleton"
SRC = TREE / "llm_landing" / "review_processing" / "manual_review_engineering.jsonl"
OUT_DIR = TREE / "llm_landing" / "review_processing" / "triage"
RECORDS = OUT_DIR / "triage_records.jsonl"
WORTH = OUT_DIR / "worth_review.jsonl"
NOT_WORTH = OUT_DIR / "not_worth.jsonl"
STATE = OUT_DIR / "triage_state.json"

SYSTEM_PROMPT = """你是知识库质量管理员。下面每一条内容是 LLM 落位后无法归属、待人工审核的内容单元。
请判断：**这一条是否值得人工审核？**

值得人工审核（worth_review=true）的标准：
1. 包含实质工程信息：参数、数值约束、方法步骤、问题描述、结论、经验教训
2. 是真实知识内容，只是当前骨架无对应节点或上下文不足，人工可确认归属
3. 缺失上下文但内容本身有信息量（如孤立表格行含具体数值）

不值得人工审核（worth_review=false）的标准：
1. 纯标题/文件名/章节名，无正文内容（如"LC数字控制交流.pptx"、"附表"、"评估材料"）
2. 无信息量的碎片（如"分支路径："、单个词、无意义占位）
3. 与工程知识无关的重复性建议（"建议新增XX节点"且内容为空泛）
4. 明显是文档元数据残留（版本号、日期、作者名）

只输出一个 JSON 对象，不要其他文字：
{"verdicts": [{"i": 0, "worth_review": true, "reason": "简短理由"}]}
每个输入的 i 都必须有判定。"""


def build_batches(items: list[dict], batch_size: int) -> list[list[dict]]:
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


_lock = threading.Lock()
_counter = {"batches": 0, "units": 0, "worth": 0, "not_worth": 0, "llm_err": 0}


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def save_state(done_chunks: set[str]) -> None:
    with _lock:
        STATE.write_text(json.dumps({
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "done_chunks": sorted(done_chunks),
            "counter": dict(_counter),
            "usage": dict(USAGE),
        }, ensure_ascii=False, indent=1), encoding="utf-8")


def triage_chunk(chunk_id: str, items: list[dict], args) -> dict:
    rows: list[dict] = []
    for batch in build_batches(items, args.batch_size):
        block = []
        for i, u in enumerate(batch):
            block.append(f"[{i}] ({u.get('unit_type','')}) {u['text'][:200]}")
        user = f"内容单元列表（共 {len(batch)} 条）:\n" + "\n".join(block)

        parsed = None
        last_err = "未知错误"
        for attempt in range(args.batch_retries):
            try:
                raw = chat(user, system=SYSTEM_PROMPT, max_tokens=4096,
                           timeout=args.timeout, retries=2)
            except RuntimeError as e:
                with _lock:
                    _counter["llm_err"] += 1
                last_err = f"LLM 调用失败: {e}"
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            if not raw or not raw.strip():
                last_err = "空响应"
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            parsed = extract_json(raw)
            if not isinstance(parsed, dict) or "verdicts" not in parsed:
                last_err = f"解析失败: {raw[:100]}"
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            break
        if parsed is None or "verdicts" not in parsed:
            with _lock:
                _counter["llm_err"] += 1
            for i, u in enumerate(batch):
                rows.append({**u, "worth_review": True, "reason": f"LLM失败默认保留审核: {last_err}"})
            continue

        by_idx = {}
        for v in parsed["verdicts"]:
            if isinstance(v, dict) and isinstance(v.get("i"), int):
                by_idx[v["i"]] = v
        for i, u in enumerate(batch):
            v = by_idx.get(i)
            worth = bool(v.get("worth_review")) if v else True
            reason = (v.get("reason") or "")[:150] if v else ""
            rows.append({**u, "worth_review": worth, "triage_reason": reason})

    append_jsonl(RECORDS, rows)
    return {"chunk": chunk_id, "units": len(items),
            "worth": sum(1 for r in rows if r["worth_review"]),
            "not_worth": sum(1 for r in rows if not r["worth_review"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--batch-retries", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    print(f"工程复核内容: {len(items)} 条")

    chunks = {}
    for i in range(0, len(items), args.chunk_size):
        chunks[f"c{i // args.chunk_size}"] = items[i:i + args.chunk_size]
    print(f"chunks: {len(chunks)}")

    if args.dry_run:
        print(f"dry-run: {len(chunks)} chunks / {len(items)} 条 / 估算批数 {len(items) // args.batch_size}")
        return 0

    done: set[str] = set()
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        done = set(st.get("done_chunks", []))
        _counter.update(st.get("counter", {}))

    todo = [(cid, citems) for cid, citems in chunks.items() if cid not in done]
    print(f"待处理: {len(todo)} chunks / {sum(len(v) for _, v in todo)} 条", flush=True)
    if not todo:
        print("全部完成")
        return 0

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(triage_chunk, cid, citems, args): cid for cid, citems in todo}
        for fut in as_completed(futs):
            cid = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"❌ chunk 异常: {cid} | {e}", flush=True)
                continue
            done.add(res["chunk"])
            with _lock:
                _counter["batches"] += 1
                _counter["units"] += res["units"]
                _counter["worth"] += res["worth"]
                _counter["not_worth"] += res["not_worth"]
                n_done = len(done)
            if n_done % 20 == 0 or n_done == len(todo):
                eta = (time.time() - t0) / max(n_done, 1) * (len(todo) - n_done)
                print(f"[{n_done}/{len(todo)}] worth={_counter['worth']} not_worth={_counter['not_worth']} "
                      f"tokens={USAGE['input_tokens'] + USAGE['output_tokens']} ETA≈{eta / 60:.0f}min", flush=True)
                save_state(done)
    save_state(done)

    # 汇总写出 worth / not_worth
    with WORTH.open("w", encoding="utf-8") as fw, NOT_WORTH.open("w", encoding="utf-8") as fn:
        with RECORDS.open(encoding="utf-8") as fr:
            for line in fr:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("worth_review"):
                    fw.write(json.dumps(r, ensure_ascii=False) + "\n")
                else:
                    fn.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n完成: worth={_counter['worth']} | not_worth={_counter['not_worth']} | llm_err={_counter['llm_err']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
