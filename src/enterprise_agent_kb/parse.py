from __future__ import annotations

import base64
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz
import httpx

from .config import AppPaths
from .db import connect
from .doc_ir import build_doc_ir, save_doc_ir
from .ids import next_prefixed_id
from .layout_cleaner import clean_doc_ir, save_cleaned_doc_ir
from .pdf_chunking import (
    load_manifest,
    preprocess_cache_dir,
    render_chunk_to_images,
    save_manifest,
    split_pdf_into_chunks,
)
from .reading_order import restore_reading_order


@dataclass(frozen=True)
class ParseResult:
    doc_id: str
    page_count: int
    block_count: int
    normalized_path: Path
    parser_engine: str


class MiniMaxUsageLimitError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _shared_workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _page_dimensions_from_pdf(source_path: Path) -> dict[int, tuple[float, float]]:
    document = fitz.open(source_path)
    try:
        return {
            page_index: (float(page.rect.width), float(page.rect.height))
            for page_index, page in enumerate(document, start=1)
        }
    finally:
        document.close()


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _load_paddlevl_settings() -> tuple[str, str]:
    _load_env_file(_shared_workspace_root() / "KB" / "knowledge-base" / ".env")
    api_url = os.environ.get("PADDLEVL_API_URL")
    api_token = os.environ.get("PADDLEVL_API_TOKEN")
    if not api_url or not api_token:
        raise RuntimeError("PaddleVL configuration unavailable")
    return api_url, api_token


def _load_minimax_settings() -> tuple[str, str]:
    _load_env_file(_project_root() / ".env")
    api_host = os.environ.get("MINIMAX_API_HOST", "https://api.minimaxi.com")
    api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("MiniMax configuration unavailable")
    return api_host.rstrip("/"), api_key


def _load_astron_settings() -> tuple[str, str]:
    """加载 astron-code-latest 模型配置"""
    _load_env_file(_project_root() / ".env")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    api_base = os.environ.get("ANTHROPIC_BASE_URL", "https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic")
    if not auth_token:
        raise RuntimeError("astron-code-latest configuration unavailable (ANTHROPIC_AUTH_TOKEN)")
    return api_base.rstrip("/"), auth_token


def _parse_pdf_with_paddlevl(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    api_url, api_token = _load_paddlevl_settings()
    page_dimensions = _page_dimensions_from_pdf(source_path)

    file_bytes = source_path.read_bytes()
    file_size_mb = len(file_bytes) / (1024 * 1024)
    timeout = 180.0
    if file_size_mb > 20:
        timeout = 400.0
    elif file_size_mb > 10:
        timeout = 300.0

    headers = {
        "Authorization": f"token {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "file": base64.b64encode(file_bytes).decode("ascii"),
        "fileType": 0,
        "useDocOrientationClassify": True,
        "useDocUnwarping": True,
        "useChartRecognition": True,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()

    layout_results = result.get("result", {}).get("layoutParsingResults", [])
    parsed_pages: list[dict[str, object]] = []
    page_count = max(len(layout_results), len(page_dimensions))

    for page_no in range(1, page_count + 1):
        width, height = page_dimensions.get(page_no, (None, None))
        markdown_text = ""
        if page_no <= len(layout_results):
            markdown_text = (
                layout_results[page_no - 1]
                .get("markdown", {})
                .get("text", "")
                .strip()
            )

        blocks = []
        if markdown_text:
            blocks.append(
                {
                    "reading_order": 1,
                    "block_type": "ocr_markdown",
                    "text": markdown_text,
                    "raw_text": markdown_text,
                    "bbox": None,
                }
            )

        parsed_pages.append(
            {
                "page_no": page_no,
                "width": width,
                "height": height,
                "parser_confidence": 0.9,
                "ocr_confidence": 0.9,
                "risk_level": "unknown",
                "page_status": "parsed",
                "blocks": blocks,
            }
        )

    return "paddlevl", parsed_pages


def _parse_pdf_subset_with_paddlevl(
    source_path: Path,
    page_numbers: list[int],
) -> dict[int, dict[str, object]]:
    if not page_numbers:
        return {}

    temp_root = _project_root() / "tmp" / "paddle_subsets"
    temp_root.mkdir(parents=True, exist_ok=True)
    ordered_pages = sorted(set(page_numbers))
    subset_pdf = temp_root / f"{source_path.stem}_subset_{uuid.uuid4().hex}.pdf"
    source_doc = fitz.open(source_path)
    subset_doc = fitz.open()
    try:
        for page_no in ordered_pages:
            subset_doc.insert_pdf(source_doc, from_page=page_no - 1, to_page=page_no - 1)
        subset_doc.save(subset_pdf)
    finally:
        subset_doc.close()
        source_doc.close()

    try:
        _, subset_pages = _parse_pdf_with_paddlevl(subset_pdf)
    finally:
        if subset_pdf.exists():
            subset_pdf.unlink()

    mapped: dict[int, dict[str, object]] = {}
    for original_page_no, subset_page in zip(ordered_pages, subset_pages, strict=False):
        mapped[original_page_no] = subset_page
    return mapped


def _page_image_batches(source_path: Path) -> tuple[Path, list[list[tuple[int, str]]]]:
    total_pages = len(_page_dimensions_from_pdf(source_path))
    cache_dir = preprocess_cache_dir(_project_root(), source_path)
    manifest_path = cache_dir / "manifest.json"
    if manifest_path.exists():
        payload = load_manifest(manifest_path)
        batches: list[list[tuple[int, str]]] = []
        for chunk in payload.get("chunks", []):
            batch: list[tuple[int, str]] = []
            for image in chunk.get("images", []):
                image_path = Path(str(image["image_path"]))
                encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
                batch.append((int(image["page_no"]), f"data:image/png;base64,{encoded}"))
            batches.append(batch)
        return cache_dir, batches

    if total_pages <= 40:
        document = fitz.open(source_path)
        try:
            batch: list[tuple[int, str]] = []
            for page_index, page in enumerate(document, start=1):
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                encoded = base64.b64encode(pix.tobytes("png")).decode("ascii")
                batch.append((page_index, f"data:image/png;base64,{encoded}"))
            return cache_dir, [batch]
        finally:
            document.close()

    batches: list[list[tuple[int, str]]] = []
    chunk_dir = cache_dir / "chunks"
    image_dir = cache_dir / "images"
    chunk_size = 20 if total_pages >= 120 else 25
    chunks = split_pdf_into_chunks(source_path, chunk_dir, chunk_size=chunk_size)
    manifest_chunks: list[dict[str, object]] = []
    for chunk in chunks:
        images = render_chunk_to_images(chunk, image_dir, scale=1.8)
        batches.append([(image.page_no, image.data_url) for image in images])
        manifest_chunks.append(
            {
                "start_page": chunk.start_page,
                "end_page": chunk.end_page,
                "chunk_pdf": str(chunk.pdf_path),
                "images": [
                    {"page_no": image.page_no, "image_path": str(image.image_path)}
                    for image in images
                ],
            }
        )
    save_manifest(
        manifest_path,
        {
            "pdf": str(source_path),
            "chunk_size": chunk_size,
            "scale": 1.8,
            "chunk_count": len(chunks),
            "chunks": manifest_chunks,
        },
    )
    return cache_dir, batches


def _call_minimax_vlm(api_host: str, api_key: str, prompt: str, image_url: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "MM-API-Source": "KB1-Parse",
        "Content-Type": "application/json",
    }
    payload = {"prompt": prompt, "image_url": image_url}
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = httpx.post(
                f"{api_host}/v1/coding_plan/vlm",
                headers=headers,
                json=payload,
                timeout=180.0,
            )
            response.raise_for_status()
            data = response.json()
            base_resp = data.get("base_resp", {})
            status_code = base_resp.get("status_code")
            if status_code == 2056:
                raise MiniMaxUsageLimitError(f"MiniMax usage limit exceeded: {base_resp}")
            if status_code not in (None, 0):
                raise RuntimeError(f"MiniMax VLM error: {base_resp}")
            content = str(data.get("content", "")).strip()
            if not content:
                raise RuntimeError("MiniMax VLM returned empty content")
            return content
        except MiniMaxUsageLimitError:
            raise
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"MiniMax VLM failed after retries: {last_error}")


def _call_astron_vlm(api_base: str, auth_token: str, prompt: str, image_url: str) -> str:
    """调用 astron-code-latest 模型进行 OCR"""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": "astron-code-latest",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_url.split(",")[1]}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    timeout_ms = int(os.environ.get("API_TIMEOUT_MS", "600000"))
    timeout_sec = timeout_ms / 1000.0

    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = httpx.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_sec,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise RuntimeError("astron VLM returned empty content")
            return str(content).strip()
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"astron-code-latest VLM failed after retries: {last_error}")


def _minimax_ocr_prompt(page_no: int, total_pages: int) -> str:
    return (
        f"你在执行第 {page_no}/{total_pages} 页的严格OCR。请逐行转写这页中所有可见文字，尽量保持原有阅读顺序、"
        "标题层级、编号、表格字段、单位、中英文、附录编号和参考文献编号。"
        "输出markdown正文即可，不要解释，不要总结，不要补充图片中没有的内容。"
        "如果页面包含图题、表题、电路图标注或页眉页码，也要转写出来。"
    )


def _parse_pdf_with_minimax_and_paddlevl(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    api_host, api_key = _load_minimax_settings()
    page_dimensions = _page_dimensions_from_pdf(source_path)
    page_count_hint = len(page_dimensions)

    paddle_pages: list[dict[str, object]] = []
    use_paddle_assist = page_count_hint <= 60
    if use_paddle_assist:
        try:
            _, paddle_pages = _parse_pdf_with_paddlevl(source_path)
        except Exception:
            paddle_pages = []

    cache_dir, page_batches = _page_image_batches(source_path)
    minimax_results: dict[int, str] = {}
    ocr_cache_dir = cache_dir / "ocr_text"
    ocr_cache_dir.mkdir(parents=True, exist_ok=True)
    page_count_for_prompt = max(len(page_dimensions), sum(len(batch) for batch in page_batches))

    # 尝试加载 astron-code-latest 备用配置
    astron_api_base = None
    astron_auth_token = None
    try:
        astron_api_base, astron_auth_token = _load_astron_settings()
    except RuntimeError:
        pass

    def _run_page(page_no: int, image_url: str) -> tuple[int, str]:
        cache_path = ocr_cache_dir / f"page_{page_no:03d}.md"
        if cache_path.exists():
            return page_no, cache_path.read_text(encoding="utf-8")
        prompt = _minimax_ocr_prompt(page_no, page_count_for_prompt)

        # MiniMax is the primary VLM; astron is only used as backup.
        try:
            text = _call_minimax_vlm(api_host, api_key, prompt, image_url)
        except Exception:
            if not astron_api_base or not astron_auth_token:
                raise
            text = _call_astron_vlm(astron_api_base, astron_auth_token, prompt, image_url)

        cache_path.write_text(text, encoding="utf-8")
        return page_no, text

    if page_batches and page_batches[0]:
        first_page_no, first_image_url = page_batches[0][0]
        preflight_cache = ocr_cache_dir / f"page_{first_page_no:03d}.md"
        if not preflight_cache.exists():
            # Preflight uses the same MiniMax-primary order as page parsing.
            prompt = _minimax_ocr_prompt(first_page_no, page_count_for_prompt)
            try:
                preflight_text = _call_minimax_vlm(api_host, api_key, prompt, first_image_url)
            except Exception:
                if not astron_api_base or not astron_auth_token:
                    raise
                preflight_text = _call_astron_vlm(astron_api_base, astron_auth_token, prompt, first_image_url)
            preflight_cache.write_text(preflight_text, encoding="utf-8")
            minimax_results[first_page_no] = preflight_text

    for batch in page_batches:
        worker_count = min(4 if page_count_for_prompt > 80 else 3, max(1, len(batch)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(_run_page, page_no, image_url)
                for page_no, image_url in batch
                if page_no not in minimax_results
            ]
            for future in as_completed(futures):
                try:
                    page_no, text = future.result()
                    minimax_results[page_no] = text
                except MiniMaxUsageLimitError:
                    break
                except Exception:
                    continue

    missing_pages = [page_no for page_no in range(1, page_count_for_prompt + 1) if page_no not in minimax_results]
    paddle_subset_pages: dict[int, dict[str, object]] = {}
    if missing_pages:
        try:
            paddle_subset_pages = _parse_pdf_subset_with_paddlevl(source_path, missing_pages)
        except Exception:
            paddle_subset_pages = {}

    parsed_pages: list[dict[str, object]] = []
    page_count = max(page_count_for_prompt, len(page_dimensions), len(paddle_pages))
    for page_no in range(1, page_count + 1):
        width, height = page_dimensions.get(page_no, (None, None))
        minimax_text = (minimax_results.get(page_no) or "").strip()
        paddle_text = ""
        subset_page = paddle_subset_pages.get(page_no)
        if subset_page:
            subset_blocks = subset_page.get("blocks", [])
            if subset_blocks:
                paddle_text = str(subset_blocks[0].get("text", "")).strip()
        if page_no <= len(paddle_pages):
            paddle_blocks = paddle_pages[page_no - 1].get("blocks", [])
            if paddle_blocks and not paddle_text:
                paddle_text = str(paddle_blocks[0].get("text", "")).strip()

        primary_text = minimax_text or paddle_text
        blocks: list[dict[str, object]] = []
        if primary_text:
            blocks.append(
                {
                    "reading_order": 1,
                    "block_type": "ocr_markdown",
                    "text": primary_text,
                    "raw_text": primary_text,
                    "bbox": None,
                }
            )
        if paddle_text and paddle_text != primary_text:
            blocks.append(
                {
                    "reading_order": 2,
                    "block_type": "structure_markdown",
                    "text": paddle_text,
                    "raw_text": paddle_text,
                    "bbox": None,
                }
            )

        parsed_pages.append(
            {
                "page_no": page_no,
                "width": width,
                "height": height,
                "parser_confidence": 0.96 if minimax_text else 0.82 if paddle_text else 0.1,
                "ocr_confidence": 0.96 if minimax_text else 0.82 if paddle_text else 0.1,
                "risk_level": "unknown",
                "page_status": "parsed",
                "blocks": blocks,
            }
        )

    if astron_api_base and astron_auth_token:
        engine = "minimax_primary+astron_backup+paddlevl" if paddle_pages else "minimax_primary+astron_backup"
    else:
        engine = "minimax+paddlevl" if paddle_pages else "minimax"
    return engine, parsed_pages


def _parse_pdf_with_pymupdf(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    parsed_pages: list[dict[str, object]] = []
    document = fitz.open(source_path)
    try:
        for page_index, page in enumerate(document, start=1):
            blocks: list[dict[str, object]] = []
            for reading_order, block in enumerate(page.get_text("blocks"), start=1):
                x0, y0, x1, y1, text, _, block_type = block
                cleaned = (text or "").strip()
                if not cleaned:
                    continue

                blocks.append(
                    {
                        "reading_order": reading_order,
                        "block_type": "text" if int(block_type) == 0 else "image",
                        "text": cleaned,
                        "raw_text": text or "",
                        "bbox": [x0, y0, x1, y1],
                    }
                )

            parsed_pages.append(
                {
                    "page_no": page_index,
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                    "parser_confidence": 1.0,
                    "ocr_confidence": None,
                    "risk_level": "unknown",
                    "page_status": "parsed",
                    "blocks": blocks,
                }
            )
    finally:
        document.close()

    return "pymupdf", parsed_pages


def _parse_pdf(source_path: Path) -> tuple[str, list[dict[str, object]]]:
    try:
        return _parse_pdf_with_minimax_and_paddlevl(source_path)
    except Exception:
        try:
            return _parse_pdf_with_paddlevl(source_path)
        except Exception:
            return _parse_pdf_with_pymupdf(source_path)


def _parse_text(source_path: Path) -> list[dict[str, object]]:
    text = source_path.read_text(encoding="utf-8", errors="replace")
    raw_blocks = [part.strip() for part in text.split("\n\n")]
    blocks = [
        {
            "reading_order": index,
            "block_type": "text",
            "text": content,
            "raw_text": content,
            "bbox": None,
        }
        for index, content in enumerate(raw_blocks, start=1)
        if content
    ]
    return [
        {
            "page_no": 1,
            "width": None,
            "height": None,
            "parser_confidence": 0.95,
            "ocr_confidence": None,
            "risk_level": "unknown",
            "page_status": "parsed",
            "blocks": blocks,
        }
    ]


def _select_parser(source_type: str):
    if source_type == "pdf":
        return _parse_pdf
    if source_type in {"markdown", "text", "file"}:
        return _parse_text
    raise ValueError(f"unsupported source_type for parse: {source_type}")


def parse_document(workspace_root: Path, doc_id: str) -> ParseResult:
    paths = AppPaths.from_root(workspace_root)
    now = _utc_now()
    connection = connect(paths.db_file)

    try:
        document_row = connection.execute(
            """
            SELECT doc_id, source_path, source_type
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document_row is None:
            raise ValueError(f"document not found: {doc_id}")

        parser = _select_parser(document_row["source_type"])
        source_path = Path(document_row["source_path"])
        parser_engine = "text"
        if document_row["source_type"] == "pdf":
            parser_engine, parsed_pages = parser(source_path)
        else:
            parsed_pages = parser(source_path)

        doc_ir = build_doc_ir(
            doc_id=doc_id,
            parser_engine=parser_engine,
            source_type=str(document_row["source_type"]),
            parsed_pages=parsed_pages,
        )

        connection.execute("DELETE FROM blocks WHERE doc_id = ?", (doc_id,))
        connection.execute("DELETE FROM pages WHERE doc_id = ?", (doc_id,))

        block_count = 0
        persisted_pages: list[dict[str, object]] = []

        for page_payload in parsed_pages:
            page_id = next_prefixed_id(connection, "page", "PAGE")
            connection.execute(
                """
                INSERT INTO pages (
                    page_id, doc_id, page_no, width, height, parser_confidence,
                    ocr_confidence, risk_level, page_status, screenshot_path,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    doc_id,
                    page_payload["page_no"],
                    page_payload["width"],
                    page_payload["height"],
                    page_payload["parser_confidence"],
                    page_payload["ocr_confidence"],
                    page_payload["risk_level"],
                    page_payload["page_status"],
                    None,
                    now,
                    now,
                ),
            )

            persisted_blocks: list[dict[str, object]] = []
            for block_payload in page_payload["blocks"]:
                block_id = next_prefixed_id(connection, "block", "BLK")
                connection.execute(
                    """
                    INSERT INTO blocks (
                        block_id, page_id, doc_id, block_type, reading_order,
                        text_content, raw_text, bbox_json, parser_confidence,
                        ocr_confidence, risk_flags_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        block_id,
                        page_id,
                        doc_id,
                        block_payload["block_type"],
                        block_payload["reading_order"],
                        block_payload["text"],
                        block_payload["raw_text"],
                        json.dumps(block_payload["bbox"], ensure_ascii=False)
                        if block_payload["bbox"] is not None
                        else None,
                        page_payload["parser_confidence"],
                        page_payload["ocr_confidence"],
                        json.dumps([], ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                block_count += 1
                persisted_blocks.append(
                    {
                        "block_id": block_id,
                        "block_type": block_payload["block_type"],
                        "reading_order": block_payload["reading_order"],
                        "text": block_payload["text"],
                        "bbox": block_payload["bbox"],
                    }
                )

            persisted_pages.append(
                {
                    "page_id": page_id,
                    "page_no": page_payload["page_no"],
                    "width": page_payload["width"],
                    "height": page_payload["height"],
                    "blocks": persisted_blocks,
                }
            )

        normalized_path = paths.normalized / f"{doc_id}.json"
        normalized_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "parsed_at": now,
                    "parser_engine": parser_engine,
                    "page_count": len(persisted_pages),
                    "block_count": block_count,
                    "pages": persisted_pages,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        doc_ir_path = paths.normalized / f"{doc_id}.doc_ir.json"
        save_doc_ir(doc_ir, doc_ir_path)
        cleaned_doc_ir = restore_reading_order(clean_doc_ir(doc_ir))
        cleaned_doc_ir_path = paths.normalized / f"{doc_id}.cleaned_doc_ir.json"
        save_cleaned_doc_ir(cleaned_doc_ir, cleaned_doc_ir_path)

        connection.execute(
            """
            UPDATE documents
            SET page_count = ?, parse_status = ?, update_time = ?
            WHERE doc_id = ?
            """,
            (len(persisted_pages), "parsed", now, doc_id),
        )
        connection.commit()
        return ParseResult(
            doc_id=doc_id,
            page_count=len(persisted_pages),
            block_count=block_count,
            normalized_path=normalized_path,
            parser_engine=parser_engine,
        )
    finally:
        connection.close()
