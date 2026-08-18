#!/usr/bin/env python3
"""review_queue 全量 LLM 重新落位（EVT/deepseek-v4-flash）。

消费 docs/ontology/tree_skeleton/review_queue.json 的全部条目（225420 条，
含已 reviewed 标记的一律重新判定），把每条内容单元归属到骨架节点。

流程：
1. 加载骨架（177 节点）→ 节点目录 catalog
2. 加载 review_queue.json 全部条目，按 doc 分组（同一文档的单元一起送，上下文连续）
3. 分批（默认 40 条/批，14k 字符上限）送 LLM（EVT/deepseek-v4-flash，Anthropic 兼容）
4. 白名单校验：node_id 必须存在于骨架；conf < 0.5 或 null → 复核队列
5. 单批 LLM 失败 → 指数退避重试（批次级，最多 5 次），仍失败 → failed 列表（不丢数据）
6. checkpoint 断点续跑（按 doc 粒度），产出记录 + 复核队列 + 报告

输出（docs/ontology/tree_skeleton/llm_landing/reland/）：
  reland_records.jsonl   全部条目的新落位结果（含 rule 基线对比）
  reland_review.jsonl    仍无法归属的条目（人工复核）
  reland_failed.jsonl    批次级 LLM 失败（可重跑）
  reland_state.json      checkpoint
  reland_report.md       完成后统计报告

用法：
  python3 reland_review_queue.py --dry-run
  python3 reland_review_queue.py                 # 全量
  python3 reland_review_queue.py --workers 4 --batch-size 40
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
REVIEW_QUEUE = TREE / "review_queue.json"
OUT_DIR = TREE / "llm_landing" / "reland"
RECORDS = OUT_DIR / "reland_records.jsonl"
REVIEW = OUT_DIR / "reland_review.jsonl"
FAILED = OUT_DIR / "reland_failed.jsonl"
STATE = OUT_DIR / "reland_state.json"

SYSTEM_PROMPT = """你是汽车电子（OBC/DCDC）知识库的"内容落位引擎"。下面是知识骨架的全部节点目录：
`ID | 层级 | 类型 | 名称`。

层级含义：
- P 物理分解（学科：电子/结构/磁件/软件；零件、电路、SW-C 组件）
- F 功能分解（充放电、对外服务等功能）
- L 逻辑/策略（控制策略、算法、保护逻辑等）
- R 需求与标准（性能/安全/接口/法规标准条款）
- G 过程（开发/生产/方法/验证测试活动/资产工具）
- Q 质量与经验（问题、失效、经验教训）
- M 项目实例（车型/项目/平台实例按阶段归档）

任务：把每个内容单元归属到目录中"最贴切且最具体"的节点。
规则：
1. node_id 只能从目录选，禁止编造任何不存在的 ID。
2. 最具体优先：内容能落到叶子节点（层级最深）就绝不落到父节点。
3. 一行含多个主题时，选主主题归属。
4. 表格行按行内容判定；标题行按标题语义判定。
5. 完全无法匹配 → node_id 为 null，并在 reason 里说明"建议新增什么节点"。
6. conf 是把握度 0~1；把握不足（conf < 0.5）时 node_id 必须填 null。
7. 文档名/分类/来源只是语境参考，落位依据是单元内容本身。
8. 内容为空或仅 HTML 注释/无实质信息 → node_id 为 null，reason 写"无实质内容"。

只输出一个 JSON 对象，不要任何其他文字：
{"assignments": [{"i": 0, "node_id": "P-...", "conf": 0.9, "reason": "简短理由"}]}
目录里每个输入的 i 都必须有一条 assignment（node_id 可为 null）。"""


def build_catalog(nodes: dict[str, dict]) -> str:
    lines = [f"{n['id']} | {n['layer']} | {n.get('type', '')} | {n['name']}" for n in nodes.values()]
    return "\n".join(lines)


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
_counter = {"docs": 0, "units": 0, "assigned": 0, "review": 0, "llm_err": 0, "batches": 0}


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def save_state(done_docs: set[str]) -> None:
    with _lock:
        STATE.write_text(json.dumps({
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "done_docs": sorted(done_docs),
            "counter": dict(_counter),
            "usage": dict(USAGE),
        }, ensure_ascii=False, indent=1), encoding="utf-8")


def land_doc(doc_name: str, items: list[dict], nodes: dict[str, dict], catalog: str, args) -> dict:
    """单文档落位：分批 LLM → 白名单校验 → 全部成功才并入 records/review。"""
    rows: list[dict] = []
    review_rows: list[dict] = []
    failed_rows: list[dict] = []
    assigned = review_cnt = 0

    for bi, batch in enumerate(make_batches(items, args.batch_size, args.max_chars)):
        block = []
        for i, u in enumerate(batch):
            sec = u.get("section", "") or ""
            block.append(f"[{i}] ({u['unit_type']}|{sec}) {u['text'][:args.text_cap]}")
        user = (
            f"文档名: {doc_name}\n内容单元列表（共 {len(batch)} 条）:\n" + "\n".join(block)
        )

        # 批次级重试：LLM 失败或空响应/解析失败最多 batch_retries 次，仍失败 → failed
        raw = None
        parsed = None
        last_err = "未知错误"
        for attempt in range(args.batch_retries):
            try:
                raw = chat(user, system=SYSTEM_PROMPT + "\n\n节点目录:\n" + catalog,
                           max_tokens=4096, timeout=args.timeout, retries=2)
            except RuntimeError as e:
                with _lock:
                    _counter["llm_err"] += 1
                last_err = f"LLM 调用失败: {e}"
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            if not raw or not raw.strip():
                last_err = "空响应（网关间歇性故障）"
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            parsed = extract_json(raw)
            if not isinstance(parsed, dict) or "assignments" not in parsed:
                last_err = f"输出无法解析: {raw[:120]}"
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            break
        if parsed is None or "assignments" not in parsed:
            for i, u in enumerate(batch):
                failed_rows.append({"doc": doc_name, "unit_id": u.get("unit_id", ""),
                                    "unit_type": u.get("unit_type", ""),
                                    "text": u.get("text", "")[:200],
                                    "reason": f"LLM 失败（{args.batch_retries} 次重试后放弃）: {last_err}"})
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
                reason = f"非法节点 {node_id} → 复核;" + reason
                node_id = None
            if conf is not None and (not isinstance(conf, (int, float)) or conf < 0.5):
                if node_id:
                    reason = f"低置信度({conf});" + reason
                node_id = None
            rows.append({
                "doc": doc_name,
                "unit_id": u.get("unit_id", ""),
                "unit_type": u.get("unit_type", ""),
                "section": u.get("section", ""),
                "text": u.get("text", "")[:200],
                "node_id": node_id,
                "node_name": nodes[node_id]["name"] if node_id in nodes else None,
                "conf": conf,
                "llm_reason": reason,
                "rule": u.get("rule", ""),
            })
            if node_id:
                assigned += 1
            else:
                review_rows.append({"doc": doc_name, "unit_id": u.get("unit_id", ""),
                                    "unit_type": u.get("unit_type", ""),
                                    "text": u.get("text", "")[:200],
                                    "reason": reason or (f"LLM 未返回 ({len(by_idx)}/{len(batch)} 条已返回)" if a is None else "无归属")})
                review_cnt += 1

    # 有任何失败批次 → 整篇文档不写输出，留给下次续跑整体重试（避免重复记录）
    if failed_rows:
        return {"doc": doc_name, "units": len(items), "assigned": 0,
                "review": 0, "failed": len(failed_rows)}

    append_jsonl(RECORDS, rows)
    if review_rows:
        append_jsonl(REVIEW, review_rows)
    return {"doc": doc_name, "units": len(items), "assigned": assigned,
            "review": review_cnt, "failed": 0}


def report(done: set[str]) -> None:
    rows, review_rows, failed_rows = [], [], []
    for path, target in ((RECORDS, rows), (REVIEW, review_rows), (FAILED, failed_rows)):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        target.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    n = len(rows)
    llm_ok = sum(1 for r in rows if r["node_id"])
    lines = [
        "# review_queue 全量 LLM 重新落位报告",
        f"- 模型: {USAGE.get('model')} | 文档: {len(done)} | 内容单元: {n}",
        f"- LLM 归属率: {llm_ok}/{n} = {llm_ok / max(n, 1) * 100:.1f}%",
        f"- 复核队列: {len(review_rows)} | 批次失败: {len(failed_rows)}",
        f"- LLM 用量: {json.dumps(USAGE, ensure_ascii=False)}",
        "",
        "## LLM 落位按节点 TOP 30",
        "",
    ]
    node_cnt = Counter(r["node_id"] for r in rows if r["node_id"])
    for nid, c in node_cnt.most_common(30):
        name = next((r["node_name"] for r in rows if r["node_id"] == nid), "")
        lines.append(f"- {nid} {name}: {c}")
    lines += ["", "## 复核队列按原因 TOP 20", ""]
    reason_cnt = Counter(r.get("reason", "")[:60] for r in review_rows)
    for reason, c in reason_cnt.most_common(20):
        lines.append(f"- [{c}] {reason}")
    (OUT_DIR / "reland_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:10]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=3, help="并行 worker 数")
    parser.add_argument("--batch-size", type=int, default=20, help="每批单元数（模型单次可靠输出 ≤20 条）")
    parser.add_argument("--max-chars", type=int, default=14000, help="每批最大字符数")
    parser.add_argument("--text-cap", type=int, default=300, help="单单元送入 LLM 的文本截断")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--batch-retries", type=int, default=4, help="批次级 LLM 失败重试次数")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不调 LLM")
    parser.add_argument("--report-only", action="store_true", help="只基于已有记录生成报告")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nodes = load_skeleton()
    catalog = build_catalog(nodes)

    if args.report_only:
        done = set()
        if STATE.exists():
            done = set(json.loads(STATE.read_text(encoding="utf-8")).get("done_docs", []))
        report(done)
        return 0

    queue = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
    print(f"review_queue 总条数: {len(queue)}", flush=True)

    # 按 doc 分组（保留原始顺序）
    by_doc: dict[str, list[dict]] = {}
    for item in queue:
        by_doc.setdefault(item.get("doc", ""), []).append(item)
    print(f"文档数: {len(by_doc)}", flush=True)

    if args.dry_run:
        tot = sum(len(v) for v in by_doc.values())
        print(f"dry-run: {len(by_doc)} 文档 / {tot} 单元；估算批数 ≈ {tot // args.batch_size}")
        return 0

    done: set[str] = set()
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        done = set(st.get("done_docs", []))
        _counter.update(st.get("counter", {}))
    # 断点加固：records 里已有的完整文档视为完成
    if RECORDS.exists():
        for line in RECORDS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                dname = json.loads(line).get("doc")
            except json.JSONDecodeError:
                continue
            if dname:
                done.add(dname)

    todo = [(dname, items) for dname, items in by_doc.items() if dname not in done]
    todo_units = sum(len(items) for _, items in todo)
    print(f"共 {len(by_doc)} 文档 | 已完成 {len(done)} | 待落 {len(todo)} 文档 / {todo_units} 单元 | workers={args.workers}", flush=True)

    if not todo:
        print("没有待落文档")
        report(done)
        return 0

    t0 = time.time()
    failed_docs: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(land_doc, dname, items, nodes, catalog, args): dname for dname, items in todo}
        for fut in as_completed(futs):
            dname = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001 单文档异常隔离
                failed_docs.append({"doc": dname, "error": repr(e)[:200]})
                print(f"❌ 文档异常跳过: {dname} | {e}", flush=True)
                continue
            done.add(res["doc"])
            with _lock:
                _counter["docs"] += 1
                _counter["units"] += res["units"]
                _counter["assigned"] += res["assigned"]
                _counter["review"] += res["review"]
                _counter["failed"] = _counter.get("failed", 0) + res["failed"]
                n_done = _counter["docs"]
            if res["failed"]:
                # 有失败批次：该文档下次续跑会重试，但立即从 done 移除
                done.discard(res["doc"])
            eta = (time.time() - t0) / max(n_done, 1) * (len(todo) - n_done)
            if n_done % 5 == 0 or n_done == len(todo):
                print(f"[{n_done}/{len(todo)}] units={_counter['units']} "
                      f"assigned={_counter['assigned']} review={_counter['review']} "
                      f"tokens={USAGE['input_tokens'] + USAGE['output_tokens']} "
                      f"ETA≈{eta / 60:.0f}min", flush=True)
                save_state(done)
    if failed_docs:
        (OUT_DIR / "reland_failed_docs.json").write_text(
            json.dumps(failed_docs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"⚠️ {len(failed_docs)} 文档落位异常，已记入 reland_failed_docs.json", flush=True)
    save_state(done)
    print(f"\n完成：{len(done)} 文档 | units={_counter['units']} | assigned={_counter['assigned']} "
          f"| review={_counter['review']} | failed={_counter.get('failed', 0)}", flush=True)
    report(done)
    (OUT_DIR / "reland_done.flag").write_text(
        time.strftime("%Y-%m-%d %H:%M:%S") + f" done_docs={len(done)} units={_counter['units']}",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
