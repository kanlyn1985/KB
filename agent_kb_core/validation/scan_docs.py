"""全量文档扫描：建立知识库文档清单（落位工程输入）。

扫描两个知识源：
1. knowledge_base/raw/Athena-main/Athena-main/raw/  （团队知识库 ~1477 文件）
2. knowledge_base/raw/                                （外部文档：标准/需求/计划）

输出 docs/ontology/tree_skeleton/doc_manifest.json：
  [{path, name, ext, size, source(Athena|external), category(Athena分类|外部类型),
    doc_type(标准/需求/计划/策略/组件规范/参数表/经验/方法/其他)}]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATHENA_RAW = ROOT / "knowledge_base" / "raw" / "Athena-main" / "Athena-main" / "raw"
EXTERNAL_RAW = ROOT / "knowledge_base" / "raw"

# 外部文档类型映射（文件名 → 类型）
EXTERNAL_TYPES = {
    "曼岛项目系统需求分析说明书.xlsx": "客户系统需求",
    "项目计划模板.xlsx": "开发计划",
    "Ruan Jian Xu Qiu Fen Xi Shuo Ming Shu.docx": "软件需求SWRD",
    "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125.pdf": "客户软件需求",
    "DOC-000015_CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125.pdf": "客户软件需求",
}

# 内容性扩展名（可提取文本的知识文档）
TEXT_EXTS = {".md", ".txt", ".docx", ".xlsx", ".pdf", ".jsonl", ".json"}


def scan_athena() -> list[dict]:
    docs = []
    if not ATHENA_RAW.exists():
        return docs
    for p in sorted(ATHENA_RAW.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ATHENA_RAW)
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else "顶层"
        docs.append({
            "path": str(p),
            "name": p.name,
            "ext": p.suffix.lower(),
            "size": p.stat().st_size,
            "source": "Athena",
            "category": category,
            "doc_type": "其他",
        })
    return docs


def scan_external() -> list[dict]:
    docs = []
    if not EXTERNAL_RAW.exists():
        return docs
    for p in sorted(EXTERNAL_RAW.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        # 排除图片/zip/压缩包等非知识文档，纳入文本类
        if p.suffix.lower() in {".pdf", ".docx", ".xlsx", ".md", ".txt"}:
            docs.append({
                "path": str(p),
                "name": p.name,
                "ext": p.suffix.lower(),
                "size": p.stat().st_size,
                "source": "external",
                "category": "外部",
                "doc_type": EXTERNAL_TYPES.get(p.name, "标准/文档"),
            })
    return docs


def main() -> None:
    athena = scan_athena()
    external = scan_external()
    manifest = {"total": len(athena) + len(external),
                "athena": len(athena), "external": len(external),
                "docs": athena + external}
    out = ROOT / "docs" / "ontology" / "tree_skeleton" / "doc_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter
    print(f"全量文档: {manifest['total']}（Athena {len(athena)} + 外部 {len(external)}）")
    print("Athena 分类分布:", dict(Counter(d["category"] for d in athena)))
    print("扩展名分布:", dict(Counter(d["ext"] for d in manifest["docs"])))
    text_docs = [d for d in manifest["docs"] if d["ext"] in TEXT_EXTS]
    print(f"可提取文本的知识文档: {len(text_docs)}")


if __name__ == "__main__":
    main()
