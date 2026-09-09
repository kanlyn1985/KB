#!/usr/bin/env python3
"""Incremental DingTalk crawler for the ME (结构研发&技术) knowledge base.

Unlike the bundled skill script (which collects everything in memory and only
writes at the end), this crawler writes every document to disk as soon as it
is fetched and persists crawl state, so an interrupted run can resume.

Resume semantics:
- Every run re-walks the folder tree (one list call per folder, cheap) so
  children enqueued before an interruption are never lost.
- Docs/spreadsheets already fetched (recorded in crawl_state.json) are skipped.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

SKILL_SCRIPT = Path(__file__).resolve().parents[2] / ".agents/skills/skill-dingtalk-knowledge-doc-fetcher/scripts/fetch_dingtalk_knowledge_doc.py"


def load_env(repo_root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = repo_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def load_skill_module() -> object:
    spec = importlib.util.spec_from_file_location("fetch_dingtalk", SKILL_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_token(module: object, env: dict[str, str]) -> str:
    return module.resolve_access_token(
        argparse.Namespace(
            access_token=env.get("DINGTALK_ACCESS_TOKEN") or env.get("DINGTALK_API_TOKEN"),
            app_key=env.get("DINGTALK_APP_KEY"),
            app_secret=env.get("DINGTALK_APP_SECRET"),
        )
    )


def crawl_incremental(
    module: object,
    token: str,
    operator_id: str,
    root_node_id: str,
    output_dir: Path,
    include_raw: bool,
    limit_docs: int | None,
    retry_failures: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    state_file = output_dir / "crawl_state.json"
    log_file = output_dir / "crawl_progress.log"
    output_dir.mkdir(parents=True, exist_ok=True)
    spreadsheet_dir = output_dir / "spreadsheets"
    spreadsheet_dir.mkdir(parents=True, exist_ok=True)

    state: dict = {"fetched": {}, "failures": {}}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"fetched": {}, "failures": {}}
    fetched: dict[str, dict] = state.get("fetched", {})
    failures: dict[str, str] = state.get("failures", {})
    if retry_failures:
        failures = {}
        state["failures"] = {}

    def log(msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def save_state() -> None:
        state_file.write_text(
            json.dumps({"fetched": fetched, "failures": failures}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # DingTalk access tokens expire (default ~2h) while a full crawl of this
    # knowledge base takes 4-6h. Wrap every API call: on
    # InvalidAuthentication, refresh the token once and retry the call.
    token_holder: dict[str, str] = {"token": token}

    def api_call(fn, *args):
        while True:
            try:
                return fn(token_holder["token"], *args)
            except Exception as exc:  # noqa: BLE001
                if "InvalidAuthentication" in str(exc) or "不合法的access_token" in str(exc):
                    log("TOKEN EXPIRED - refreshing access token and retrying")
                    token_holder["token"] = get_token(module, env or {})
                    continue
                raise

    # BFS over the tree. Folders are re-expanded on every run (cheap);
    # already-fetched docs are skipped so resume never re-downloads.
    queue: list[tuple[dict, int, str]] = [
        ({"nodeId": root_node_id, "name": root_node_id, "type": "folder"}, 0, "ROOT")
    ]
    seen: set[str] = set()
    node_index: list[dict] = []
    fail_count = 0
    while queue:
        node, depth, path = queue.pop(0)
        node_id = module.extract_doc_key(node)
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        title = module.node_title(node)
        if depth >= 30:
            log(f"DEPTH LIMIT: {path}/{title}")
            continue

        is_folder = module.is_folder_node(node) or node.get("hasChildren")
        kind = "folder" if module.is_folder_node(node) else str(node.get("extension") or node.get("type") or "")
        node_index.append({"name": title, "type": kind, "nodeId": node_id, "path": path})

        if is_folder:
            try:
                children = api_call(module.list_nodes, operator_id, node_id)
            except Exception as exc:  # noqa: BLE001
                log(f"LIST FAIL {path}/{title} ({node_id}): {exc}")
                fail_count += 1
            else:
                for child in children:
                    queue.append((child, depth + 1, f"{path}/{module.node_title(child)}"))

        if node_id in fetched or node_id in failures:
            continue

        annotated = dict(node)
        annotated["_path"] = path
        if module.is_spreadsheet_node(node):
            stem = f"{module.sanitize_filename(title)}"
            xlsx_path = spreadsheet_dir / f"{stem}.xlsx"
            try:
                spreadsheet = api_call(module.fetch_spreadsheets, operator_id, [annotated], None)[0]
                if spreadsheet.get("error"):
                    raise Exception(spreadsheet["error"])  # noqa: TRY002
                module.write_spreadsheet_xlsx(xlsx_path, spreadsheet)
                fetched[node_id] = {"kind": "spreadsheet", "title": title, "path": path, "sheets": len(spreadsheet.get("sheets", [])), "xlsx": str(xlsx_path)}
                log(f"SHEET +{len(fetched)}: {path}/{title}")
            except Exception as exc:  # noqa: BLE001
                (spreadsheet_dir / f"{stem}.error.txt").write_text(f"{title}\n\nERROR: {exc}\n", encoding="utf-8")
                failures[node_id] = str(exc)
                log(f"SHEET FAIL {path}/{title}: {exc}")
                fail_count += 1
        elif module.is_document_node(node):
            if limit_docs is not None and len([v for v in fetched.values() if v.get("kind") == "doc"]) >= limit_docs:
                log(f"DOC LIMIT {limit_docs} reached, stopping.")
                break
            stem = f"{module.sanitize_filename(title)}"
            md_path = output_dir / f"{stem}.md"
            raw_path = output_dir / f"{stem}.blocks.json"
            try:
                raw = api_call(module.read_blocks, operator_id, node_id)
                markdown = module.blocks_to_markdown(raw.get("blocks", []))
                md_path.write_text(markdown, encoding="utf-8")
                if include_raw:
                    raw_path.write_text(json.dumps({"node": annotated, **raw}, ensure_ascii=False, indent=2), encoding="utf-8")
                fetched[node_id] = {"kind": "doc", "title": title, "path": path, "blocks": len(raw.get("blocks", [])), "markdown": str(md_path)}
                log(f"DOC +{len(fetched)}: {path}/{title}")
            except Exception as exc:  # noqa: BLE001
                md_path.write_text(f"# {title}\n\nERROR: {exc}\n", encoding="utf-8")
                failures[node_id] = str(exc)
                log(f"DOC FAIL {path}/{title}: {exc}")
                fail_count += 1
        # Binary/link/aitable nodes: recorded in node_index only (metadata level).
        save_state()

    index = {
        "documents": [v for v in fetched.values() if v.get("kind") == "doc"],
        "spreadsheets": [v for v in fetched.values() if v.get("kind") == "spreadsheet"],
        "nodes": node_index,
        "failures": failures,
    }
    (output_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    log(
        f"DONE docs={len(index['documents'])} sheets={len(index['spreadsheets'])} "
        f"nodes={len(node_index)} failures={len(failures)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-node-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--limit-docs", type=int)
    parser.add_argument("--retry-failures", action="store_true", help="Retry nodes previously recorded as failures (e.g. after fixing openpyxl).")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    env = load_env(repo_root)
    module = load_skill_module()
    token = get_token(module, env)
    operator_id = env["DINGTALK_OPERATOR_UNION_ID"]
    crawl_incremental(
        module,
        token,
        operator_id,
        args.root_node_id,
        Path(args.output_dir),
        args.include_raw,
        args.limit_docs,
        retry_failures=args.retry_failures,
        env=env,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
