#!/usr/bin/env python3
"""Apply Requirement Resolver answer_api soft-router integration.

Idempotent: re-running after integration prints "already integrated" and
makes no changes. Adds an opt-in soft router guard at the top of
`answer_api.answer_query` that delegates requirement-intent queries to the
Requirement Resolver when `EAKB_ENABLE_REQUIREMENT_ROUTER=1`. When the env
var is unset (default), `try_answer_requirement_query` returns None and the
normal answer chain is unchanged.

Library API: ``integrate_answer_api(path) -> bool`` applies the patch to the
given answer_api.py path and returns True if any change was made. ``main()``
is the CLI wrapper that resolves the path from REPO_ROOT.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSWER_API_PATH = REPO_ROOT / "src" / "enterprise_agent_kb" / "answer_api.py"

IMPORT_LINE = "from .requirements.router import try_answer_requirement_query\n"

GUARD_BLOCK = (
    "    # requirement_router_mvp: opt-in soft route for customer/project requirement questions.\n"
    "    requirement_answer = try_answer_requirement_query(workspace_root, query)\n"
    "    if requirement_answer is not None:\n"
    "        return requirement_answer\n\n"
)


def fail(msg: str) -> None:
    raise SystemExit(f"[apply_requirement_answer_api_integration] {msg}")


def integrate_answer_api(path: Path) -> bool:
    """Apply the soft-router patch to the given answer_api.py path.

    Returns True if any change was made, False if already integrated.
    Raises SystemExit if a required anchor is missing (manual patch needed).
    """
    if not path.exists():
        fail(f"cannot find {path}; run from repo root or pass a valid path.")
    text = path.read_text(encoding="utf-8")
    changed = False
    import re

    # 1. import line: insert before the answer_query def. Prefer the
    #    ontology_adapter import block anchor; fall back to inserting right
    #    before the `def answer_query(` line for minimal fixtures.
    if IMPORT_LINE not in text:
        onto_close = (
            "from .ontology_adapter import (\n"
            "    EntityConstraint,\n"
            "    OntologySignal,\n"
            "    post_check as _ontology_post_check,\n"
            ")\n"
        )
        if onto_close in text:
            text = text.replace(onto_close, onto_close + IMPORT_LINE, 1)
            changed = True
        else:
            m = re.search(r"^def answer_query\(", text, re.M)
            if m is None:
                fail("answer_query def anchor not found; patch answer_api.py manually.")
            text = text[: m.start()] + IMPORT_LINE + "\n" + text[m.start() :]
            changed = True

    # 2. guard block: insert right after the answer_query docstring, before
    #    the first statement (the _resolve_intent_and_context call). For
    #    minimal fixtures without that call, insert right after the docstring
    #    close or the def signature.
    if "requirement_router_mvp" not in text:
        docstring_close = (
            '    """\n'
            "    routed = _resolve_intent_and_context(workspace_root, query, limit, preferred_doc_id)\n"
        )
        if docstring_close in text:
            replacement = (
                '    """\n'
                + GUARD_BLOCK
                + "    routed = _resolve_intent_and_context(workspace_root, query, limit, preferred_doc_id)\n"
            )
            text = text.replace(docstring_close, replacement, 1)
            changed = True
        else:
            # Minimal fixture: insert after the answer_query signature line.
            import re
            sig_match = re.search(r"^def answer_query\([^)]*\)[^:]*:\n", text, re.M)
            if sig_match:
                end = sig_match.end()
                text = text[:end] + GUARD_BLOCK + text[end:]
                changed = True
            else:
                # Multi-line signature: find the closing paren line.
                lines = text.splitlines(keepends=True)
                out: list[str] = []
                inserted = False
                in_sig = False
                for ln in lines:
                    out.append(ln)
                    if "def answer_query(" in ln:
                        in_sig = True
                    if in_sig and ln.rstrip().endswith("):"):
                        out.append(GUARD_BLOCK)
                        inserted = True
                        in_sig = False
                if not inserted:
                    fail("could not locate answer_query signature end; patch answer_api.py manually.")
                text = "".join(out)
                changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def main() -> None:
    changed = integrate_answer_api(ANSWER_API_PATH)
    if not changed:
        print("answer_api requirement soft-router already integrated; no changes made.")
        return
    print(f"updated {ANSWER_API_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
