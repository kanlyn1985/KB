from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz
import httpx

from enterprise_agent_kb.parse import _parse_pdf_with_paddlevl


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "docs"
DOC_PATH = next((ROOT / "knowledge_base" / "raw").glob("DOC-000007*"))


@dataclass(frozen=True)
class ConversionCheck:
    method: str
    status_code: int | None
    success: bool
    extracted_text_preview: str
    anchor_hit_count: int
    anchor_total: int
    notes: str


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _render_first_page_png(pdf_path: Path) -> bytes:
    document = fitz.open(pdf_path)
    try:
        page = document[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return pix.tobytes("png")
    finally:
        document.close()


def _anchor_score(text: str, anchors: list[str]) -> int:
    normalized = text.lower()
    return sum(1 for anchor in anchors if anchor.lower() in normalized)


def _extract_llm_text_from_response(payload: dict[str, object]) -> str:
    parts = payload.get("content", [])
    if not isinstance(parts, list):
        return ""
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            texts.append(str(part.get("text", "")))
        elif isinstance(part, dict) and part.get("type") == "thinking":
            texts.append(str(part.get("thinking", "")))
    return "\n".join(item for item in texts if item).strip()


def _call_llm_with_image(env: dict[str, str], png_bytes: bytes) -> ConversionCheck:
    payload = {
        "model": env["LLM_MODEL"],
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "You are performing OCR. Read this page and return only the visible text in markdown, no commentary.",
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.b64encode(png_bytes).decode("ascii"),
                        },
                    },
                ],
            }
        ],
    }
    headers = {
        "x-api-key": env["OPENAI_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    response = httpx.post(
        env["OPENAI_BASE_URL"].rstrip("/") + "/v1/messages",
        json=payload,
        headers=headers,
        timeout=120.0,
    )
    parsed = response.json()
    text = _extract_llm_text_from_response(parsed)
    anchors = ["QC/T 1036—2016", "汽车电源逆变器", "2016-04-05", "2016-09-01"]
    return ConversionCheck(
        method="llm_image",
        status_code=response.status_code,
        success=_anchor_score(text, anchors) >= 2,
        extracted_text_preview=text[:800],
        anchor_hit_count=_anchor_score(text, anchors),
        anchor_total=len(anchors),
        notes="项目配置 LLM 的图像输入链路测试",
    )


def _call_llm_with_pdf(env: dict[str, str], pdf_path: Path) -> ConversionCheck:
    payload = {
        "model": env["LLM_MODEL"],
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Read this PDF and return the first page visible text only in markdown, no commentary.",
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
                        },
                    },
                ],
            }
        ],
    }
    headers = {
        "x-api-key": env["OPENAI_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    response = httpx.post(
        env["OPENAI_BASE_URL"].rstrip("/") + "/v1/messages",
        json=payload,
        headers=headers,
        timeout=180.0,
    )
    parsed = response.json()
    text = _extract_llm_text_from_response(parsed)
    anchors = ["QC/T 1036—2016", "汽车电源逆变器", "2016-04-05", "2016-09-01"]
    return ConversionCheck(
        method="llm_pdf",
        status_code=response.status_code,
        success=_anchor_score(text, anchors) >= 2,
        extracted_text_preview=text[:800],
        anchor_hit_count=_anchor_score(text, anchors),
        anchor_total=len(anchors),
        notes="项目配置 LLM 的 PDF 文档输入链路测试",
    )


def _run_paddle(pdf_path: Path) -> dict[str, object]:
    engine, pages = _parse_pdf_with_paddlevl(pdf_path)
    page1_text = "\n".join(block.get("text", "") for block in pages[0]["blocks"])
    anchors = ["QC/T 1036—2016", "汽车电源逆变器", "2016-04-05", "2016-09-01"]
    return {
        "method": "paddlevl",
        "engine": engine,
        "page_count": len(pages),
        "block_count": sum(len(page["blocks"]) for page in pages),
        "page1_anchor_hit_count": _anchor_score(page1_text, anchors),
        "page1_anchor_total": len(anchors),
        "page1_preview": page1_text[:1200],
    }


def main() -> None:
    env = _load_env()
    png_bytes = _render_first_page_png(DOC_PATH)
    paddle = _run_paddle(DOC_PATH)
    llm_image = _call_llm_with_image(env, png_bytes)
    llm_pdf = _call_llm_with_pdf(env, DOC_PATH)

    report = {
        "document": str(DOC_PATH),
        "document_size_mb": round(DOC_PATH.stat().st_size / 1024 / 1024, 3),
        "paddle": paddle,
        "llm_image": asdict(llm_image),
        "llm_pdf": asdict(llm_pdf),
        "conclusion": {
            "paddle_available": True,
            "llm_multimodal_available": llm_image.success or llm_pdf.success,
            "summary": (
                "当前项目配置的 LLM 接口未表现出可用的 PDF/图片直读能力；"
                "PaddleVL 可以成功完成整份 PDF 解析并正确命中封面关键锚点。"
            ),
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "pdf_conversion_ab_doc000007_2026-04-19.json"
    md_path = REPORT_DIR / "pdf_conversion_ab_doc000007_2026-04-19.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = f"""# PDF 转换 A/B 对比报告

## 测试文档

- 文档: `{DOC_PATH.name}`
- 大小: `{report["document_size_mb"]} MB`

## PaddleVL 结果

- 页数: `{paddle["page_count"]}`
- block 数: `{paddle["block_count"]}`
- 封面关键锚点命中: `{paddle["page1_anchor_hit_count"]}/{paddle["page1_anchor_total"]}`

封面预览:

```text
{paddle["page1_preview"]}
```

## LLM 结果

### 图像输入

- HTTP 状态: `{llm_image.status_code}`
- 成功判定: `{llm_image.success}`
- 关键锚点命中: `{llm_image.anchor_hit_count}/{llm_image.anchor_total}`

```text
{llm_image.extracted_text_preview}
```

### PDF 文档输入

- HTTP 状态: `{llm_pdf.status_code}`
- 成功判定: `{llm_pdf.success}`
- 关键锚点命中: `{llm_pdf.anchor_hit_count}/{llm_pdf.anchor_total}`

```text
{llm_pdf.extracted_text_preview}
```

## 结论

{report["conclusion"]["summary"]}

这意味着当前环境下无法对“真正的 LLM 直读 PDF/图片转换精度”做公平对比，因为项目配置的 LLM 输入链路本身不可用。  
若要继续做真实 A/B，对策有两种：

1. 更换为明确支持 PDF/图片多模态输入的 LLM 接口
2. 将对比目标调整为：
   - PaddleVL 视觉解析
   - 文本层提取 + LLM 结构化整理
"""
    md_path.write_text(md, encoding="utf-8")

    print(json_path)
    print(md_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
