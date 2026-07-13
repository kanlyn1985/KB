#!/usr/bin/env python3
"""Apply Requirement Resolver API server integration.

Idempotent. Scans the api_server package for a FastAPI ``app``/``include_router``
pattern. If found, patches the module to wire in the Requirement Resolver
router via ``create_fastapi_router``. If NOT found (KB1 uses a custom HTTP
dispatcher, not FastAPI), the script refuses to patch and exits nonzero with
a ``Refusing to patch`` message -- this is intentional so callers know the
automatic path did not apply. Pass ``--allow-skip`` to exit 0 instead.

Library API: ``integrate_api_server(repo_root, allow_skip=False) -> bool``
returns True if a FastAPI module was patched, False if already integrated,
and raises SystemExit on refusal (unless allow_skip=True).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_SERVER_DIR = REPO_ROOT / "src" / "enterprise_agent_kb" / "api_server"

CANDIDATES = [
    API_SERVER_DIR / "_request_handlers.py",
    API_SERVER_DIR / "__init__.py",
    API_SERVER_DIR / "app.py",
]

FASTAPI_MARKERS = ("FastAPI(", "include_router", "APIRouter(")
MARKER_TAG = "# requirement-api-router-integrated"
IMPORT_LINE = (
    "from enterprise_agent_kb.requirements.api import create_fastapi_router  # type: ignore  "
    + MARKER_TAG
    + "\n"
)
INCLUDE_LINE = "app.include_router(create_fastapi_router(root))  " + MARKER_TAG + "\n"


def fail(msg: str) -> None:
    raise SystemExit(f"[apply_requirement_api_integration] {msg}")


def find_fastapi_target(repo_root: Path) -> tuple[Path, str] | None:
    api_dir = repo_root / "src" / "enterprise_agent_kb" / "api_server"
    for path in CANDIDATES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in FASTAPI_MARKERS):
            return path, text
    return None


def patch_fastapi_module(path: Path, text: str) -> bool:
    """Patch a FastAPI-style module. Returns True if changed, False if already integrated."""
    if MARKER_TAG in text:
        return False
    lines = text.splitlines(keepends=True)

    # Insert import after the first import/from line.
    first_import_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("from ") or ln.startswith("import ")),
        0,
    )
    lines.insert(first_import_idx, IMPORT_LINE)
    base = "".join(lines)

    # Insert include_router after the last existing include_router line, else
    # after the FastAPI( construction line.
    if INCLUDE_LINE not in base:
        out: list[str] = []
        inserted = False
        target = "include_router" if "include_router" in base else "FastAPI("
        for ln in lines:
            out.append(ln)
            if not inserted and target in ln:
                out.append(INCLUDE_LINE)
                inserted = True
        if not inserted:
            out.append(INCLUDE_LINE)
        base = "".join(out)

    path.write_text(base, encoding="utf-8")
    return True


def integrate_api_server(repo_root: Path, allow_skip: bool = False) -> bool:
    """Apply API integration. Returns True if patched, False if already integrated.

    Raises SystemExit on refusal (non-FastAPI) unless allow_skip=True, in which
    case it prints a notice and returns False.
    """
    api_dir = repo_root / "src" / "enterprise_agent_kb" / "api_server"
    if not api_dir.exists():
        msg = f"api_server directory not found at {api_dir}; refusing to patch."
        if allow_skip:
            print(msg)
            return False
        fail(msg)

    target = find_fastapi_target(repo_root)
    if target is None:
        msg = (
            "Refusing to patch: no FastAPI app/include_router pattern found in api_server. "
            "KB1 uses a custom HTTP dispatcher. The framework-neutral handler "
            "enterprise_agent_kb.requirements.api.handle_requirement_api_request is available "
            "as a library import for manual wiring."
        )
        if allow_skip:
            print(msg)
            return False
        fail(msg)

    path, text = target
    changed = patch_fastapi_module(path, text)
    if changed:
        print(f"patched FastAPI module {path.relative_to(repo_root)}")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help="Exit 0 (instead of nonzero) when no FastAPI pattern is found.",
    )
    args = parser.parse_args()

    changed = integrate_api_server(REPO_ROOT, allow_skip=args.allow_skip)
    if not changed:
        if not args.allow_skip:
            # integrate_api_server already raised; this is unreachable but kept for safety.
            return
        print("no FastAPI pattern found; skipped (--allow-skip).")
        return
    # If already integrated (changed=False) and we did not skip, distinguish:
    # integrate_api_server returns False both for "already integrated" and "skipped".
    # Use MARKER_TAG presence to tell them apart.
    target = find_fastapi_target(REPO_ROOT)
    if target is not None:
        _path, text = target
        if MARKER_TAG in text:
            print("requirement API router already integrated; no changes made.")
            return
    print("requirement API integration applied successfully.")


if __name__ == "__main__":
    main()
