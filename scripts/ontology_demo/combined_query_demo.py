"""Demo of the combined (legacy + ontology) query system.

This script shows that for any question the user asks, the
combined system produces:
  1. A precise, structured answer from the ontology (when applicable)
  2. Prose context from the legacy system (when available)

The result is more useful than either system alone.

Run:
    python scripts/ontology_demo/combined_query_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.combined_query import combined_query, route_query
from kb1_ontology.db import default_db_path


WORKSPACE = ROOT / "knowledge_base"


# A curated list of questions that exercise the combined system.
QUESTIONS = [
    # === Parameter queries (ontology-friendly) ===
    "ISO 14229-3 中 P2 Server Timing 是多少？",
    "GB/T 18487.1 额定交流电压是多少？",
    "GB/T 18487.4 V2L 最大输出电压？",
    # === Reference queries (ontology-friendly) ===
    "GB/T 18487.1 引用了哪些标准？",
    "哪些标准引用了 ISO 14229-1？",
    # === Traversal queries (ontology-only) ===
    "从 ISO 14229-7 出发 2 跳可达的标准？",
    # === Service queries (ontology-friendly) ===
    "ISO 14229-1 定义了哪些 UDS 服务？",
    # === Definition queries (both systems) ===
    "ISO 14229-1 是什么？",
    "GB/T 18487.4 V2L 是什么意思？",
    # === Free-form (legacy-friendly) ===
    "车载充电机正常工作时产生的交流电压波动和闪烁的限值应以下要求?",
]


def main() -> None:
    print("=" * 70)
    print("  KB1 Combined Query Demo: Legacy + Ontology")
    print("=" * 70)
    print()
    if not default_db_path(WORKSPACE).exists():
        print("❌ Ontology DB not found. Run build first.")
        return
    for i, q in enumerate(QUESTIONS, 1):
        print()
        print("─" * 70)
        print(f"[Q{i}]  {q}")
        cat = route_query(q)
        print(f"      Category: {cat}")
        result = combined_query(WORKSPACE, q, limit=5)
        # Print ontology block
        print()
        if result.ontology_answer is None or result.ontology_answer == []:
            print("   📐 Ontology: (no answer)")
        else:
            ans = result.ontology_answer
            if isinstance(ans, list):
                head = ans[:5]
                for item in head:
                    print(f"   📐 Ontology: • {item}")
                if len(ans) > 5:
                    print(f"             ... ({len(ans) - 5} more)")
            else:
                print(f"   📐 Ontology: {ans}")
            print(f"             type: {result.ontology_exactness}")
        # Print legacy block
        if result.legacy_excerpt:
            print()
            print(f"   📖 Legacy:  {result.legacy_excerpt}")
        else:
            print()
            print("   📖 Legacy:  (no excerpt)")
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print()
    print("Both systems are running in parallel. For every question,")
    print("the user gets:")
    print("  - Precise typed answers (ontology) — when the question")
    print("    matches a structured capability (parameter, ref, traversal).")
    print("  - Prose context (legacy) — when the legacy pipeline can")
    print("    find supporting facts and produce a snippet.")
    print()
    print("The combined result is **more useful** than either system alone.")


if __name__ == "__main__":
    main()
