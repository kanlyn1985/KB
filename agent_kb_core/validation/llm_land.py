#!/usr/bin/env python3
"""全量 LLM 落位：内容单元 → 骨架节点（zcode 主模型 deepseek-v4-pro-0813）。

替换规则落位（rule_match 仅作对比基线保留在记录里）。

流程（每文档）：
1. extract_units 提取内容单元（噪声白名单过滤）
2. 分批（默认 40 单元/批，截断合批）送 LLM，输入含 177 节点目录
3. LLM 返回 {"assignments":[{"i","node_id","conf","reason"}]}
4. 代码白名单校验：node_id 必须存在于骨架；conf<0.5 或 node_id null → 复核队列
5. 记录写 JSONL（records），状态写 checkpoint（断点续跑）

输出（docs/ontology/tree_skeleton/llm_landing/）：
  records.jsonl            落位明细（含规则基线 rule_node_id 供对比）
  review.jsonl             未落位/低置信度队列（人工复核 + 后续增枝线索）
  state.json               checkpoint（done 文档列表 + 用量 + 计数）
  report.md                完成后统计（LLM vs 规则对比，按节点/层级分布）

用法：
  python3 llm_land.py --source ME --limit 10          # 冒烟
  python3 llm_land.py --source ME                     # 单来源全量
  python3 llm_land.py                                  # 全量
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "validation"))

from extract_units import extract_md, extract_docx, extract_xlsx, extract_pdf  # noqa: E402
from land_units import MANIFEST, load_skeleton, rule_match  # noqa: E402
from llm_client import chat, extract_json, USAGE  # noqa: E402

OUT_DIR = ROOT / "docs" / "ontology" / "tree_skeleton" / "llm_landing"
RECORDS = OUT_DIR / "records.jsonl"
REVIEW = OUT_DIR / "review.jsonl"
STATE = OUT_DIR / "state.json"

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

只输出一个 JSON 对象，不要任何其他文字：
{"assignments": [{"i": 0, "node_id": "P-...", "conf": 0.9, "reason": "简短理由"}]}
目录里每个输入的 i 都必须有一条 assignment（node_id 可为 null）。"""


def build_catalog(nodes: dict[str, dict]) -> str:
    lines = [f"{n['id']} | {n['layer']} | {n.get('type', '')} | {n['name']}" for n in nodes.values()]
    return "\n".join(lines)


def extract_for(d: dict) -> list[dict]:
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


def make_batches(units: list[dict], batch_size: int, max_chars: int) -> list[list[dict]]:
    """把单元切成批：兼顾条数与字符数，section 信息保留在单元内。"""
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
_counter = {"docs": 0, "units": 0, "assigned": 0, "review": 0, "llm_err": 0}


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


def _safe(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]


def land_doc(d: dict, nodes: dict[str, dict], catalog: str, args) -> dict:
    """单文档落位：提取 → 分批 LLM → 白名单校验 → 全部成功才并入 records/review。

    用本进程固定命名，不写临时文件：records 只在文档全部分批成功后一次写入，
    断点续跑以 state.json 的 done_docs 为准，无重复记录风险
    （worker 进程若在并入前被杀，该文档整篇重跑，代价可接受）。
    """
    doc_name = d["name"]
    units = [u for u in extract_for(d) if u.get("unit_type") != "noise"]
    if args.max_doc_units and len(units) > args.max_doc_units:
        units = units[: args.max_doc_units]
    if not units:
        return {"doc": doc_name, "units": 0, "assigned": 0, "review": 0, "skipped": "无内容单元"}

    rows: list[dict] = []
    review_rows: list[dict] = []
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
        try:
            raw = chat(user, system=SYSTEM_PROMPT + "\n\n节点目录:\n" + catalog,
                       max_tokens=4096, timeout=args.timeout)
        except RuntimeError as e:
            with _lock:
                _counter["llm_err"] += 1
            # 该批整批进复核队列，不丢数据
            for i, u in enumerate(batch):
                review_rows.append({"doc": doc_name, "source": d.get("source", ""),
                                    "unit_id": u.get("unit_id", ""),
                                    "unit_type": u.get("unit_type", ""),
                                    "text": u.get("text", "")[:200],
                                    "reason": f"LLM 调用失败: {e}"})
                review_cnt += 1
            continue
        parsed = extract_json(raw)
        if not isinstance(parsed, dict) or "assignments" not in parsed:
            with _lock:
                _counter["llm_err"] += 1
            for i, u in enumerate(batch):
                review_rows.append({"doc": doc_name, "source": d.get("source", ""),
                                    "unit_id": u.get("unit_id", ""),
                                    "unit_type": u.get("unit_type", ""),
                                    "text": u.get("text", "")[:200],
                                    "reason": f"输出无法解析: {raw[:120]}"})
                review_cnt += 1
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
            # 白名单校验：node_id 必须存在
            if node_id and node_id not in nodes:
                reason = f"非法节点 {node_id} → 复核;" + reason
                node_id = None
            if conf is not None and (not isinstance(conf, (int, float)) or conf < 0.5):
                if node_id:
                    reason = f"低置信度({conf});" + reason
                node_id = None
            # 规则基线（供对比）
            rn, rr, rc = rule_match(u, nodes)[:3]
            rows.append({
                "doc": doc_name, "doc_path": d["path"], "source": d.get("source", ""),
                "category": d.get("category", ""), "unit_id": u.get("unit_id", ""),
                "unit_type": u.get("unit_type", ""), "section": u.get("section", ""),
                "text": u.get("text", "")[:200],
                "node_id": node_id,
                "node_name": nodes[node_id]["name"] if node_id in nodes else None,
                "conf": conf, "llm_reason": reason,
                "rule_node_id": rn if rn in nodes else None,
                "rule_name": rr,
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

    append_jsonl(RECORDS, rows)
    if review_rows:
        append_jsonl(REVIEW, review_rows)
    return {"doc": doc_name, "units": len(units), "assigned": assigned, "review": review_cnt}


def report(done: set[str]) -> None:
    """完成后生成对比报告。"""
    rows = []
    if RECORDS.exists():
        for line in RECORDS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not rows:
        print("无落位记录")
        return
    n = len(rows)
    llm_ok = sum(1 for r in rows if r["node_id"])
    rule_ok = sum(1 for r in rows if r["rule_node_id"])
    agree = sum(1 for r in rows if r["node_id"] and r["node_id"] == r["rule_node_id"])
    differ = sum(1 for r in rows if r["node_id"] and r["rule_node_id"] and r["node_id"] != r["rule_node_id"])
    lines = [
        "# LLM 全量落位报告",
        f"- 模型: {USAGE.get('model')} | 文档: {len(done)} | 内容单元: {n}",
        f"- LLM 归属率: {llm_ok}/{n} = {llm_ok / max(n, 1) * 100:.1f}%",
        f"- 规则基线归属率: {rule_ok}/{n} = {rule_ok / max(n, 1) * 100:.1f}%",
        f"- 两法一致: {agree} | 分歧且两法均归属: {differ} | 仅LLM归属: {sum(1 for r in rows if r['node_id'] and not r['rule_node_id'])} | 仅规则归属: {sum(1 for r in rows if not r['node_id'] and r['rule_node_id'])}",
        f"- 复核队列: {sum(1 for r in rows if not r['node_id'])}（见 review.jsonl）",
        f"- LLM 用量: {json.dumps(USAGE, ensure_ascii=False)}",
        "",
        "## LLM 落位按节点 TOP 30",
        "",
    ]
    from collections import Counter
    node_cnt = Counter(r["node_id"] for r in rows if r["node_id"])
    for nid, c in node_cnt.most_common(30):
        name = next((r["node_name"] for r in rows if r["node_id"] == nid), "")
        lines.append(f"- {nid} {name}: {c}")
    lines += ["", "## 复核队列按原因 TOP 20", ""]
    review_rows = []
    if REVIEW.exists():
        for line in REVIEW.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    review_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    reason_cnt = Counter(r.get("reason", "")[:60] for r in review_rows)
    for reason, c in reason_cnt.most_common(20):
        lines.append(f"- [{c}] {reason}")
    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None, help="只处理某来源（Athena/external/EE/ME）")
    parser.add_argument("--category", default=None, help="只处理某分类")
    parser.add_argument("--limit", type=int, default=0, help="限制文档数（0=全部，冒烟用）")
    parser.add_argument("--workers", type=int, default=3, help="并行 worker 数")
    parser.add_argument("--batch-size", type=int, default=40, help="每批单元数")
    parser.add_argument("--max-chars", type=int, default=14000, help="每批最大字符数")
    parser.add_argument("--text-cap", type=int, default=300, help="单单元送入 LLM 的文本截断")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-doc-units", type=int, default=0, help="每文档最多处理单元数（0=不限）")
    parser.add_argument("--dry-run", action="store_true", help="只统计文档/单元数，不调 LLM")
    parser.add_argument("--report-only", action="store_true", help="只基于已有 records 生成报告")
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

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    allowed = {".md", ".docx", ".xlsx", ".pdf"}
    docs = [d for d in manifest["docs"] if d["ext"] in allowed]
    if args.source:
        docs = [d for d in docs if d.get("source") == args.source]
    if args.category:
        docs = [d for d in docs if d.get("category") == args.category]

    # 去重：pdf/docx 与同名 md 并存时只落 md（与 land_units 一致）
    md_stems = {d["name"][:-3] for d in docs if d["name"].endswith(".md")}
    docs = [d for d in docs if not (d["ext"] in {".pdf", ".docx"} and d["name"][: -len(d["ext"])] in md_stems)]
    if args.limit:
        docs = docs[: args.limit]

    done: set[str] = set()
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        done = set(st.get("done_docs", []))
        _counter.update(st.get("counter", {}))  # 续跑时恢复计数
    # 断点加固：records.jsonl 里已有的完整文档也视为完成
    # （覆盖"并入 records 后、保存 state 前"进程被杀的小窗口，杜绝重复落位）
    if RECORDS.exists():
        from itertools import islice
        with RECORDS.open(encoding="utf-8") as f:
            for line in islice(f, 0, None):
                line = line.strip()
                if not line:
                    continue
                try:
                    n = json.loads(line).get("doc")
                except json.JSONDecodeError:
                    continue
                if n:
                    done.add(n)
    todo = [d for d in docs if d["name"] not in done]
    print(f"共 {len(docs)} 文档 | 已完成 {len(done)} | 待落 {len(todo)} | workers={args.workers}")

    if args.dry_run:
        tot_u = 0
        for d in todo[:100]:
            units = [u for u in extract_for(d) if u.get("unit_type") != "noise"]
            tot_u += len(units)
            print(f"  {d['name'][:40]:42s} {len(units)} 单元 @ {d.get('source')}/{d.get('category')}")
        print(f"dry-run: 前100文档 {tot_u} 单元；估算批量数约 {tot_u // args.batch_size} 批")
        return 0

    if not todo:
        print("没有待落文档")
        report(done)
        return 0

    t0 = time.time()
    failed: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(land_doc, d, nodes, catalog, args): d for d in todo}
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001 单文档异常隔离，不让整个作业死掉
                failed.append({"doc": d["name"], "error": repr(e)[:200]})
                print(f"❌ 文档异常跳过: {d['name']} | {e}", flush=True)
                continue
            done.add(res["doc"])
            with _lock:
                _counter["docs"] += 1
                _counter["units"] += res["units"]
                _counter["assigned"] += res["assigned"]
                _counter["review"] += res["review"]
                n_done = _counter["docs"]
            eta = (time.time() - t0) / n_done * (len(todo) - n_done)
            if n_done % 5 == 0 or n_done == len(todo):
                print(f"[{n_done}/{len(todo)}] docs={_counter['docs']} units={_counter['units']} "
                      f"assigned={_counter['assigned']} review={_counter['review']} "
                      f"tokens={USAGE['input_tokens'] + USAGE['output_tokens']} "
                      f"ETA≈{eta / 60:.0f}min", flush=True)
                save_state(done)
    if failed:
        (OUT_DIR / "failed_docs.json").write_text(
            json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"⚠️ {len(failed)} 文档落位异常，已记入 failed_docs.json", flush=True)
    save_state(done)
    print(f"\n完成：{len(done)} 文档 | units={_counter['units']} | assigned={_counter['assigned']} | review={_counter['review']}")
    report(done)
    (OUT_DIR / "landing_done.flag").write_text(
        time.strftime("%Y-%m-%d %H:%M:%S") + f" done_docs={len(done)} units={_counter['units']}",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())