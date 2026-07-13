#!/usr/bin/env python3
"""Restore the integrated requirement-management program package from chunk files.

Run from repository root:

    python scripts/restore_requirement_program.py --extract

The script reassembles artifacts/requirement_program_package/parts/*.b64
into artifacts/evt_requirement_resolver_integrated_program_system_audit.zip,
verifies SHA-256, and optionally extracts it into the repository root.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "artifacts" / "requirement_program_package"
PARTS_DIR = PACKAGE_DIR / "parts"
MANIFEST_PATH = PACKAGE_DIR / "manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", action="store_true", help="Extract the restored zip into the repository root")
    parser.add_argument("--overwrite", action="store_true", help="Allow zip extraction to overwrite existing files")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    chunk_count = int(manifest["chunk_count"])
    output = PACKAGE_DIR / manifest["artifact"]

    encoded_parts = []
    for idx in range(1, chunk_count + 1):
        part_path = PARTS_DIR / f"part_{idx:03d}.b64"
        if not part_path.exists():
            raise FileNotFoundError(f"missing chunk: {part_path}")
        encoded_parts.append(part_path.read_text(encoding="utf-8").strip())

    raw = base64.b64decode("".join(encoded_parts).encode("ascii"))
    digest = hashlib.sha256(raw).hexdigest()
    expected = manifest["sha256"]
    if digest != expected:
        raise RuntimeError(f"sha256 mismatch: expected {expected}, got {digest}")

    output.write_bytes(raw)
    print(f"restored: {output}")
    print(f"sha256:   {digest}")

    if args.extract:
        with zipfile.ZipFile(output) as zf:
            if not args.overwrite:
                collisions = [name for name in zf.namelist() if (ROOT / name).exists() and not name.endswith("/")]
                if collisions:
                    preview = "\n".join(collisions[:20])
                    raise RuntimeError(
                        "extraction would overwrite existing files. "
                        "re-run with --overwrite after review. Collisions:\n" + preview
                    )
            zf.extractall(ROOT)
        print(f"extracted into: {ROOT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
