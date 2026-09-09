#!/usr/bin/env python3
"""软件类文档专项 LLM 落位（EVT/deepseek-v4-flash）。

背景：全量落位时软件类文档（717 个）只有 4 个进了 review_queue，P-SW 软件组件
节点 17 个全部空置——因为 review_queue 只收集规则落位失败的单元，规则对软件
语义基本失效。本脚本把这些文档直接从 manifest 提取并送 LLM 落位，验证骨架
P-SW 软件域规划是否合理。

流程（与 reland_review_queue.py 一致）：
1. 从 doc_manifest.json 筛软件类文档（文件名关键词）
2. extract_units 提取内容单元（排除 noise）
3. 分批（20 条/批）送 LLM（thinking-off），含 177 节点目录
4. 白名单校验：node_id 必须存在于骨架；conf<0.5 或 null → 复核
5. 断点续跑（按文档）；失败批次整文档跳过，下轮重试

输出（docs/ontology/tree_skeleton/llm_landing/reland_sw/）：
  sw_records.jsonl   落位明细
  sw_review.jsonl    复核队列
  sw_state.json      checkpoint
  sw_report.md       报告
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

from extract_units import extract_md, extract_docx, extract_xlsx, extract_pdf  # noqa: E402
from land_units import load_skeleton  # noqa: E402
from llm_client import chat, extract_json, USAGE  # noqa: E402

TREE = ROOT / "docs" / "ontology" / "tree_skeleton"
MANIFEST = TREE / "doc_manifest.json"
OUT_DIR = TREE / "llm_landing" / "reland_sw"
RECORDS = OUT_DIR / "sw_records.jsonl"
REVIEW = OUT_DIR / "sw_review.jsonl"
STATE = OUT_DIR / "sw_state.json"

# 软件类文档筛选关键词（文件名）
SW_KEYWORDS = [
    "详细设计规范", "标准策略", "asw", "bsw", "rte", "autosar", "simulink", "stateflow",
    "dbc", "can_e2e", "arxml", "标定", "代码生成", "coding", "模型", "obcstate",
    "dcdcfault", "acrelayctrl", "adcsignal", "gunmanage", "insdet", "e2e", "sw",
    "软件", "诊断", "fault", "calibration", "neusar", "polarion", "mcu", "ecuk",
]

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
9. 软件组件/模型/代码/标定相关内容优先考虑 P 层 SW-C 组件节点（P-SW-ASW-*）、
   逻辑策略节点（L-*）或 G-METHOD-AUTOSAR（AUTOSAR 配置方法）。

只输出一个 JSON 对象，不要任何其他文字：
{"assignments": [{"i": 0, "node_id": "P-...", "conf": 0.9, "reason": "简短理由"}]}
目录里每个输入的 i 都必须有一条 assignment（node_id 可为 null）。"""


def to_win(p: str) -> str:
    s = str(p)
    if s.startswith("/mnt/e/"):
        return "E:/" + s[7:]
    return s


def build_catalog(nodes: dict[str, dict]) -> str:
    return "\n".join(f"{n['id']} | {n['layer']} | {n.get('type', '')} | {n['name']}" for n in nodes.values())


def make_batches(units: list[dict], batch_size: int, max_chars: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    cur: list[dict] = []
    cur_chars = 0
    for u in units:
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
_counter = {"docs": 0, "units": 0, "assigned": 0, "review": 0, "llm_err": 0, "failed": 0}


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


def extract_for(d: dict) -> list[dict]:
    p = Path(to_win(d["path"]))
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


def land_doc(d: dict, nodes: dict[str, dict], catalog: str, args) -> dict:
    doc_name = d["name"]
    units = [u for u in extract_for(d) if u.get("unit_type") != "noise"]
    if not units:
        # 无内容单元（路径不存在/空文档）：直接标记完成，避免反复进队列
        append_jsonl(RECORDS, [{"doc": doc_name, "doc_path": d["path"], "source": d.get("source", ""),
                                "category": d.get("category", ""), "unit_id": "", "unit_type": "empty",
                                "section": "", "text": "", "node_id": None, "node_name": None,
                                "conf": None, "llm_reason": "无内容单元（空文档/路径不存在）"}])
        return {"doc": doc_name, "units": 0, "assigned": 0, "review": 0, "failed": 0}

    rows: list[dict] = []
    review_rows: list[dict] = []
    failed_rows: list[dict] = []
    assigned = review_cnt = 0

    for bi, batch in enumerate(make_batches(units, args.batch_size, args.max_chars)):
        block = []
        for i, u in enumerate(batch):
            sec = u.get("section", "") or ""
            block.append(f"[{i}] ({u['unit_type']}|{sec}) {u['text'][:args.text_cap]}")
        user = (
            f"文档名: {doc_name}\n分类: {d.get('category', '')} 来源: {d.get('source', '')}\n"
            f"内容单元列表（共 {len(batch)} 条）:\n" + "\n".join(block)
        )

        raw = None
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
                "doc": doc_name, "doc_path": d["path"], "source": d.get("source", ""),
                "category": d.get("category", ""), "unit_id": u.get("unit_id", ""),
                "unit_type": u.get("unit_type", ""), "section": u.get("section", ""),
                "text": u.get("text", "")[:200],
                "node_id": node_id,
                "node_name": nodes[node_id]["name"] if node_id in nodes else None,
                "conf": conf, "llm_reason": reason,
            })
            if node_id:
                assigned += 1
            else:
                review_rows.append({"doc": doc_name, "source": d.get("source", ""),
                                    "unit_id": u.get("unit_id", ""),
                                    "unit_type": u.get("unit_type", ""),
                                    "text": u.get("text", "")[:200],
                                    "reason": reason or (f"LLM 未返回 ({len(by_idx)}/{len(batch)} 条已返回)" if a is None else "无归属")})
                review_cnt += 1

    if failed_rows:
        return {"doc": doc_name, "units": len(units), "assigned": 0,
                "review": 0, "failed": len(failed_rows)}

    append_jsonl(RECORDS, rows)
    if review_rows:
        append_jsonl(REVIEW, review_rows)
    return {"doc": doc_name, "units": len(units), "assigned": assigned,
            "review": review_cnt, "failed": 0}


def report(done: set[str]) -> None:
    rows, review_rows = [], []
    for path, target in ((RECORDS, rows), (REVIEW, review_rows)):
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
        "# 软件类文档专项 LLM 落位报告",
        f"- 模型: {USAGE.get('model')} | 文档: {len(done)} | 内容单元: {n}",
        f"- LLM 归属率: {llm_ok}/{n} = {llm_ok / max(n, 1) * 100:.1f}%",
        f"- 复核队列: {len(review_rows)}",
        f"- LLM 用量: {json.dumps(USAGE, ensure_ascii=False)}",
        "",
        "## LLM 落位按节点 TOP 30",
        "",
    ]
    node_cnt = Counter(r["node_id"] for r in rows if r["node_id"])
    for nid, c in node_cnt.most_common(30):
        name = next((r["node_name"] for r in rows if r["node_id"] == nid), "")
        lines.append(f"- {nid} {name}: {c}")
    lines += ["", "## P-SW 节点归属统计", ""]
    psw = Counter(r["node_id"] for r in rows if r["node_id"] and r["node_id"].startswith("P-SW"))
    for nid, c in psw.most_common(30):
        name = next((r["node_name"] for r in rows if r["node_id"] == nid), "")
        lines.append(f"- {nid} {name}: {c}")
    (OUT_DIR / "sw_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:10]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-chars", type=int, default=14000)
    parser.add_argument("--text-cap", type=int, default=300)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--batch-retries", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="限制文档数（冒烟）")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nodes = load_skeleton()
    catalog = build_catalog(nodes)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    allowed = {".md", ".docx", ".xlsx", ".pdf"}
    docs = [d for d in manifest["docs"]
            if d["ext"] in allowed and any(k.lower() in d["name"].lower() for k in SW_KEYWORDS)]
    # 去重：pdf/docx 与同名 md 并存时只落 md
    md_stems = {d["name"][:-3] for d in docs if d["name"].endswith(".md")}
    docs = [d for d in docs if not (d["ext"] in {".pdf", ".docx"} and d["name"][: -len(d["ext"])] in md_stems)]
    if args.limit:
        docs = docs[: args.limit]
    print(f"软件类文档: {len(docs)} 个", flush=True)

    if args.dry_run:
        tot = 0
        for d in docs[:100]:
            units = [u for u in extract_for(d) if u.get("unit_type") != "noise"]
            tot += len(units)
            print(f"  {d['name'][:45]:47s} {len(units)} 单元")
        print(f"dry-run: 前{min(len(docs),100)}文档 {tot} 单元")
        return 0

    done: set[str] = set()
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        done = set(st.get("done_docs", []))
        _counter.update(st.get("counter", {}))
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

    todo = [d for d in docs if d["name"] not in done]
    print(f"共 {len(docs)} 文档 | 已完成 {len(done)} | 待落 {len(todo)} | workers={args.workers}", flush=True)
    if not todo:
        print("没有待落文档")
        report(done)
        return 0

    t0 = time.time()
    failed_docs: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(land_doc, d, nodes, catalog, args): d for d in todo}
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                failed_docs.append({"doc": d["name"], "error": repr(e)[:200]})
                print(f"❌ 文档异常跳过: {d['name']} | {e}", flush=True)
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
                done.discard(res["doc"])
            if n_done % 10 == 0 or n_done == len(todo):
                eta = (time.time() - t0) / max(n_done, 1) * (len(todo) - n_done)
                print(f"[{n_done}/{len(todo)}] units={_counter['units']} "
                      f"assigned={_counter['assigned']} review={_counter['review']} "
                      f"failed={_counter.get('failed', 0)} tokens={USAGE['input_tokens'] + USAGE['output_tokens']} "
                      f"ETA≈{eta / 60:.0f}min", flush=True)
                save_state(done)
    if failed_docs:
        (OUT_DIR / "sw_failed_docs.json").write_text(
            json.dumps(failed_docs, ensure_ascii=False, indent=1), encoding="utf-8")
    save_state(done)
    print(f"\n完成：{len(done)} 文档 | units={_counter['units']} | assigned={_counter['assigned']} "
          f"| review={_counter['review']} | failed={_counter.get('failed', 0)}", flush=True)
    report(done)
    (OUT_DIR / "sw_done.flag").write_text(
        time.strftime("%Y-%m-%d %H:%M:%S") + f" done_docs={len(done)} units={_counter['units']}",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
