#!/usr/bin/env python3
"""过载节点二次细分落位（EVT/deepseek-v4-flash，skeleton v0.4）。

对合并落位中属于 8 个过载节点的内容重新送 LLM，用 v0.4 骨架（210 节点）
细分到新子节点。输入为 merged_full_records.jsonl 中 node_id ∈ 过载集合的
记录（约 12 万条），输出细分后的新归属。

流程：
1. 读 merged_full_records.jsonl，筛出过载节点记录（text 字段）
2. 分批（20 条/批）送 LLM（v0.4 骨架目录 + 提示优先落到新子节点）
3. 白名单校验 + conf 过滤；失败批次整批跳过（下一轮重试）
4. 输出细分记录到 reland_split/split_records.jsonl

用法：
  python3 split_overload.py --dry-run
  python3 split_overload.py --workers 6
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

from land_units import load_skeleton  # noqa: E402
from llm_client import chat, extract_json, USAGE  # noqa: E402

TREE = ROOT / "docs" / "ontology" / "tree_skeleton"
MERGED = TREE / "llm_landing" / "merged_full_records.jsonl"
OUT_DIR = TREE / "llm_landing" / "reland_split"
RECORDS = OUT_DIR / "split_records.jsonl"
REVIEW = OUT_DIR / "split_review.jsonl"
STATE = OUT_DIR / "split_state.json"

# 过载节点（8 个，G-DEV 不拆）
OVERLOAD = {
    "G-METHOD-AUTOSAR", "G-PROD-ASSEMBLY", "G-PROD-POTTING", "G-VERIFY-CAE",
    "Q-PROBLEM", "G-METHOD-CAE-STRUCT", "P-SW-BSW", "G-VERIFY-VIBRATION",
}

SYSTEM_PROMPT = """你是汽车电子（OBC/DCDC）知识库的"内容落位引擎"。下面是知识骨架的全部节点目录：
`ID | 层级 | 类型 | 名称`。

这些内容此前被归属到某个父节点（见"原归属"），现在需要细分为更具体的子节点。
规则：
1. node_id 只能从目录选，禁止编造不存在的 ID。
2. **优先选择原归属节点的子节点**（最具体优先）；确实不属于任何子节点才保留父节点。
3. 完全无法匹配 → node_id 为 null，reason 写原因。
4. conf 是把握度 0~1；把握不足（conf < 0.5）时 node_id 必须填 null。
5. 内容为空或无实质信息 → node_id 为 null。

只输出一个 JSON 对象，不要任何其他文字：
{"assignments": [{"i": 0, "node_id": "P-...", "conf": 0.9, "reason": "简短理由"}]}
每个输入的 i 都必须有一条 assignment（node_id 可为 null）。"""


def build_catalog(nodes: dict[str, dict]) -> str:
    return "\n".join(f"{n['id']} | {n['layer']} | {n.get('type', '')} | {n['name']}" for n in nodes.values())


def make_batches(items: list[dict], batch_size: int, max_chars: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    cur: list[dict] = []
    cur_chars = 0
    for u in items:
        add = len(u.get("text", "")) + 40
        if cur and (len(cur) >= batch_size or cur_chars + add > max_chars):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(u)
        cur_chars += add
    if cur:
        batches.append(cur)
    return batches


_lock = threading.Lock()
_counter = {"batches": 0, "units": 0, "assigned": 0, "review": 0, "failed": 0, "llm_err": 0}


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


def land_chunk(chunk_id: str, items: list[dict], nodes: dict[str, dict], catalog: str, args) -> dict:
    rows: list[dict] = []
    review_rows: list[dict] = []
    assigned = review_cnt = 0

    for batch in make_batches(items, args.batch_size, args.max_chars):
        block = []
        for i, u in enumerate(batch):
            block.append(f"[{i}] ({u['unit_type']}|{u.get('section','')}) {u['text'][:args.text_cap]}")
        user = (
            f"文档名: {batch[0].get('doc','')}\n原归属: {batch[0].get('orig_node','')} {batch[0].get('orig_name','')}\n"
            f"内容单元列表（共 {len(batch)} 条）:\n" + "\n".join(block)
        )

        parsed = None
        last_err = "未知错误"
        for attempt in range(args.batch_retries):
            try:
                raw = chat(user, system=SYSTEM_PROMPT + "\n\n节点目录:\n" + catalog,
                           max_tokens=8192, timeout=args.timeout, retries=2)
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
            if not isinstance(parsed, dict) or "assignments" not in parsed:
                last_err = f"解析失败: {raw[:100]}"
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            break
        if parsed is None or "assignments" not in parsed:
            with _lock:
                _counter["failed"] += len(batch)
                _counter["llm_err"] += 1
            continue

        by_idx = {}
        for a in parsed["assignments"]:
            if isinstance(a, dict) and isinstance(a.get("i"), int):
                by_idx[a["i"]] = a
        for i, u in enumerate(batch):
            a = by_idx.get(i)
            node_id = a.get("node_id") if a else None
            conf = a.get("conf") if a else None
            reason = (a.get("reason") or "")[:200] if a else ""
            if node_id and node_id not in nodes:
                reason = f"非法节点 {node_id};" + reason
                node_id = None
            if conf is not None and (not isinstance(conf, (int, float)) or conf < 0.5):
                if node_id:
                    reason = f"低置信度({conf});" + reason
                node_id = None
            rows.append({
                "doc": u.get("doc", ""), "unit_id": u.get("unit_id", ""),
                "unit_type": u.get("unit_type", ""), "text": u.get("text", "")[:200],
                "orig_node": u.get("orig_node", ""), "orig_name": u.get("orig_name", ""),
                "node_id": node_id, "node_name": nodes[node_id]["name"] if node_id in nodes else None,
                "conf": conf, "llm_reason": reason,
            })
            if node_id:
                assigned += 1
            else:
                review_rows.append({"doc": u.get("doc", ""), "unit_id": u.get("unit_id", ""),
                                    "unit_type": u.get("unit_type", ""), "text": u.get("text", "")[:200],
                                    "orig_node": u.get("orig_node", ""),
                                    "reason": reason or "无归属"})
                review_cnt += 1

    append_jsonl(RECORDS, rows)
    if review_rows:
        append_jsonl(REVIEW, review_rows)
    return {"chunk": chunk_id, "units": len(items), "assigned": assigned,
            "review": review_cnt, "failed": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-chars", type=int, default=14000)
    parser.add_argument("--text-cap", type=int, default=200)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--batch-retries", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=200, help="每 chunk 单元数（断点粒度）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nodes = load_skeleton()  # 从 skeleton_v0.2.json 读？需指向 v0.4
    # 显式加载 v0.4
    skel = json.loads((TREE / "skeleton_v0.4.json").read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in skel["nodes"]}
    catalog = build_catalog(nodes)
    print(f"v0.4 骨架节点: {len(nodes)}")

    # 读取合并落位，筛过载节点
    items = []
    with MERGED.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("node_id") in OVERLOAD and r.get("text"):
                items.append({
                    "doc": r.get("doc", ""), "unit_id": r.get("unit_id", ""),
                    "unit_type": r.get("unit_type", ""), "text": r.get("text", ""),
                    "orig_node": r["node_id"], "orig_name": r.get("node_name", ""),
                })
    print(f"过载节点内容: {len(items)} 条")

    # 分 chunk（断点粒度）
    chunks = {}
    for i in range(0, len(items), args.chunk_size):
        chunks[f"c{i // args.chunk_size}"] = items[i:i + args.chunk_size]
    print(f"chunks: {len(chunks)}")

    if args.dry_run:
        tot = sum(len(v) for v in chunks.values())
        print(f"dry-run: {len(chunks)} chunks / {tot} 条 / 估算批数 {tot // args.batch_size}")
        return 0

    done: set[str] = set()
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        done = set(st.get("done_chunks", []))
        _counter.update(st.get("counter", {}))
    if RECORDS.exists():
        # 断点加固：records 里已有 doc+unit_id 视为完成（按 chunk 无法精确恢复，简单处理为已处理 chunk 跳过）
        pass

    todo = [(cid, citems) for cid, citems in chunks.items() if cid not in done]
    print(f"待处理: {len(todo)} chunks / {sum(len(v) for _, v in todo)} 条", flush=True)
    if not todo:
        print("全部完成")
        return 0

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(land_chunk, cid, citems, nodes, catalog, args): cid for cid, citems in todo}
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
                _counter["assigned"] += res["assigned"]
                _counter["review"] += res["review"]
                n_done = len(done)
            if n_done % 20 == 0 or n_done == len(todo):
                eta = (time.time() - t0) / max(n_done, 1) * (len(todo) - n_done)
                print(f"[{n_done}/{len(todo)}] units={_counter['units']} "
                      f"assigned={_counter['assigned']} review={_counter['review']} "
                      f"failed={_counter['failed']} tokens={USAGE['input_tokens'] + USAGE['output_tokens']} "
                      f"ETA≈{eta / 60:.0f}min", flush=True)
                save_state(done)
    save_state(done)
    print(f"\n完成: {len(done)} chunks | units={_counter['units']} | assigned={_counter['assigned']} "
          f"| review={_counter['review']} | failed={_counter['failed']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
