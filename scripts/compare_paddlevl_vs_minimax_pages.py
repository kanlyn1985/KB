from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz
import httpx

from enterprise_agent_kb.parse import _parse_pdf_with_paddlevl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "tmp" / "GBT+18487.1-2023.pdf"
REPORT_DIR = ROOT / "docs"
TMP_DIR = ROOT / "tmp" / "ocr_ab_benchmark"


@dataclass(frozen=True)
class CandidateScore:
    fidelity_0_5: int
    completeness_0_5: int
    terminology_0_5: int
    structure_0_5: int
    total_0_100: float
    issues: list[str]


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _sample_pages(page_count: int, sample_size: int) -> list[int]:
    if sample_size >= page_count:
        return list(range(1, page_count + 1))
    pages = {
        int(round(1 + i * (page_count - 1) / (sample_size - 1)))
        for i in range(sample_size)
    }
    ordered = sorted(pages)
    while len(ordered) < sample_size:
        for page_no in range(1, page_count + 1):
            if page_no not in pages:
                pages.add(page_no)
                ordered = sorted(pages)
                if len(ordered) == sample_size:
                    break
    return ordered


def _render_page(pdf_path: Path, page_no: int, scale: float = 2.0) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    image_path = TMP_DIR / f"{pdf_path.stem}_p{page_no:03d}.png"
    document = fitz.open(pdf_path)
    try:
        page = document.load_page(page_no - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        pix.save(image_path)
    finally:
        document.close()
    return image_path


def _minimax_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "MM-API-Source": "KB1-Benchmark",
        "Content-Type": "application/json",
    }


def _image_to_data_url(image_path: Path) -> str:
    import base64

    media_type = "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _call_minimax_vlm(api_host: str, api_key: str, prompt: str, image_path: Path) -> str:
    payload = {
        "prompt": prompt,
        "image_url": _image_to_data_url(image_path),
    }
    response = httpx.post(
        f"{api_host.rstrip('/')}/v1/coding_plan/vlm",
        headers=_minimax_headers(api_key),
        json=payload,
        timeout=180.0,
    )
    response.raise_for_status()
    data = response.json()
    base_resp = data.get("base_resp", {})
    if base_resp.get("status_code") not in (None, 0):
        raise RuntimeError(f"MiniMax VLM error: {base_resp}")
    content = str(data.get("content", "")).strip()
    if not content:
        raise RuntimeError("MiniMax VLM returned empty content")
    return content


def _extract_json_object(text: str) -> dict[str, object]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError(f"Unable to find JSON object in: {cleaned[:500]}")
    return json.loads(cleaned[start : end + 1])


def _coerce_score_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, min(5, int(round(float(value)))))
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        raise ValueError(f"Unable to coerce score from value: {value!r}")
    return max(0, min(5, int(round(float(match.group(0))))))


def _score_from_judge_payload(payload: dict[str, object]) -> CandidateScore:
    fidelity = _coerce_score_value(
        payload.get("fidelity_0_5", payload.get("fidelity", payload.get("忠实度")))
    )
    completeness = _coerce_score_value(
        payload.get("completeness_0_5", payload.get("completeness", payload.get("完整度")))
    )
    terminology = _coerce_score_value(
        payload.get(
            "terminology_0_5",
            payload.get("terminology", payload.get("术语准确性", payload.get("术语"))),
        )
    )
    structure = _coerce_score_value(
        payload.get("structure_0_5", payload.get("structure", payload.get("结构可读性")))
    )
    total = (
        fidelity * 0.35
        + completeness * 0.30
        + terminology * 0.20
        + structure * 0.15
    ) / 5.0 * 100.0
    raw_issues = payload.get("issues", [])
    issues = [str(item) for item in raw_issues] if isinstance(raw_issues, list) else []
    return CandidateScore(
        fidelity_0_5=fidelity,
        completeness_0_5=completeness,
        terminology_0_5=terminology,
        structure_0_5=structure,
        total_0_100=round(total, 1),
        issues=issues,
    )


def _judge_candidate(api_host: str, api_key: str, image_path: Path, candidate_text: str) -> CandidateScore:
    judge_prompt = (
        "你是严格的OCR评审员。请只根据图片内容评估下面的候选转写，不要补充图片里没有的文字。"
        "若候选文本出现总结、解释、概述、补全推断，也要扣分。"
        "请只输出一个JSON对象，不要markdown代码块，不要额外解释。"
        'JSON字段固定为 {"fidelity_0_5": int, "completeness_0_5": int, "terminology_0_5": int, '
        '"structure_0_5": int, "issues": string[]}。'
        "评分标准：5=几乎无误；4=少量漏字或轻微格式差异；3=中等错误；2=错误较多；1=严重不准；0=不可用。"
        "fidelity 评估是否忠于可见文字；completeness 评估覆盖度；terminology 评估术语、编号、数字、单位准确性；"
        "structure 评估标题、条目、表格字段、分段是否保持清晰。"
        "\n候选转写如下：\n---\n"
        f"{candidate_text.strip()}\n"
        "---"
    )
    raw = _call_minimax_vlm(api_host, api_key, judge_prompt, image_path)
    try:
        return _score_from_judge_payload(_extract_json_object(raw))
    except Exception as exc:
        fallback_payload = {
            "fidelity_0_5": 0,
            "completeness_0_5": 0,
            "terminology_0_5": 0,
            "structure_0_5": 0,
            "issues": [
                f"judge_parse_error: {type(exc).__name__}",
                raw[:500],
            ],
        }
        return _score_from_judge_payload(fallback_payload)


def _benchmark(pdf_path: Path, sample_size: int = 10) -> dict[str, object]:
    env = _load_env_file(ROOT / ".env")
    api_key = env["OPENAI_API_KEY"]
    api_host = "https://api.minimaxi.com"

    paddle_engine, paddle_pages = _parse_pdf_with_paddlevl(pdf_path)
    page_count = len(paddle_pages)
    sampled_pages = _sample_pages(page_count, sample_size)

    results: list[dict[str, object]] = []
    for page_no in sampled_pages:
        print(f"benchmarking page {page_no}/{page_count}", flush=True)
        image_path = _render_page(pdf_path, page_no)
        paddle_text = ""
        blocks = paddle_pages[page_no - 1]["blocks"]
        if blocks:
            paddle_text = str(blocks[0].get("text", "")).strip()

        minimax_prompt = (
            "你在执行严格OCR。请逐行转写图片中所有可见文字，尽量保留原有阅读顺序、标题层级、编号、"
            "表格字段、单位以及中英文内容。只输出markdown正文，不要解释，不要总结，不要补充图片中没有的内容。"
        )
        minimax_text = _call_minimax_vlm(api_host, api_key, minimax_prompt, image_path)

        paddle_score = _judge_candidate(api_host, api_key, image_path, paddle_text)
        minimax_score = _judge_candidate(api_host, api_key, image_path, minimax_text)

        results.append(
            {
                "page_no": page_no,
                "image_path": str(image_path),
                "paddle": {
                    "text_preview": paddle_text[:2400],
                    "char_count": len(paddle_text),
                    "score": asdict(paddle_score),
                },
                "minimax": {
                    "text_preview": minimax_text[:2400],
                    "char_count": len(minimax_text),
                    "score": asdict(minimax_score),
                },
            }
        )

    def avg(path: str) -> float:
        parts = path.split(".")
        values: list[float] = []
        for item in results:
            current: object = item
            for part in parts:
                current = current[part]  # type: ignore[index]
            values.append(float(current))
        return round(sum(values) / len(values), 2)

    paddle_avg = {
        "fidelity_0_5": avg("paddle.score.fidelity_0_5"),
        "completeness_0_5": avg("paddle.score.completeness_0_5"),
        "terminology_0_5": avg("paddle.score.terminology_0_5"),
        "structure_0_5": avg("paddle.score.structure_0_5"),
        "total_0_100": avg("paddle.score.total_0_100"),
    }
    minimax_avg = {
        "fidelity_0_5": avg("minimax.score.fidelity_0_5"),
        "completeness_0_5": avg("minimax.score.completeness_0_5"),
        "terminology_0_5": avg("minimax.score.terminology_0_5"),
        "structure_0_5": avg("minimax.score.structure_0_5"),
        "total_0_100": avg("minimax.score.total_0_100"),
    }

    winner = "tie"
    if paddle_avg["total_0_100"] > minimax_avg["total_0_100"]:
        winner = "paddlevl"
    elif minimax_avg["total_0_100"] > paddle_avg["total_0_100"]:
        winner = "minimax_understand_image"

    return {
        "document": str(pdf_path),
        "document_size_mb": round(pdf_path.stat().st_size / 1024 / 1024, 3),
        "page_count": page_count,
        "sample_size": len(sampled_pages),
        "sampled_pages": sampled_pages,
        "paddle_engine": paddle_engine,
        "paddle_average": paddle_avg,
        "minimax_average": minimax_avg,
        "winner": winner,
        "page_results": results,
        "method_note": (
            "由于该PDF很多页面的内嵌文本层存在乱码，本次不使用文本层做参考答案。"
            "评分改为同页图像盲评：同一张页面图分别评估 PaddleVL 输出与 MiniMax understand_image 输出。"
        ),
    }


def _build_markdown(report: dict[str, object]) -> str:
    paddle_avg = report["paddle_average"]
    minimax_avg = report["minimax_average"]
    lines = [
        "# PaddleVL vs MiniMax understand_image 十页对比报告",
        "",
        "## 测试范围",
        "",
        f"- 文档: `{Path(str(report['document'])).name}`",
        f"- 文档页数: `{report['page_count']}`",
        f"- 抽样页: `{', '.join(str(p) for p in report['sampled_pages'])}`",
        f"- 抽样数: `{report['sample_size']}`",
        f"- 评分方式: `{report['method_note']}`",
        "",
        "## 平均分",
        "",
        "| 路径 | 忠实度 | 完整度 | 术语/数字准确性 | 结构可读性 | 总分 |",
        "|---|---:|---:|---:|---:|---:|",
        (
            f"| PaddleVL | {paddle_avg['fidelity_0_5']:.2f} | {paddle_avg['completeness_0_5']:.2f} | "
            f"{paddle_avg['terminology_0_5']:.2f} | {paddle_avg['structure_0_5']:.2f} | {paddle_avg['total_0_100']:.2f} |"
        ),
        (
            f"| MiniMax understand_image | {minimax_avg['fidelity_0_5']:.2f} | {minimax_avg['completeness_0_5']:.2f} | "
            f"{minimax_avg['terminology_0_5']:.2f} | {minimax_avg['structure_0_5']:.2f} | {minimax_avg['total_0_100']:.2f} |"
        ),
        "",
        f"## 总体结论",
        "",
        f"- 胜出路径: `{report['winner']}`",
        "",
        "## 分页结果",
        "",
    ]

    for page_result in report["page_results"]:
        paddle = page_result["paddle"]
        minimax = page_result["minimax"]
        lines.extend(
            [
                f"### 第 {page_result['page_no']} 页",
                "",
                (
                    f"- PaddleVL: `{paddle['score']['total_0_100']}` 分"
                    f" | 问题: `{'; '.join(paddle['score']['issues']) or '无明显问题'}`"
                ),
                (
                    f"- MiniMax understand_image: `{minimax['score']['total_0_100']}` 分"
                    f" | 问题: `{'; '.join(minimax['score']['issues']) or '无明显问题'}`"
                ),
                "",
            ]
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    report = _benchmark(DEFAULT_PDF, sample_size=10)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "paddlevl_vs_minimax_10page_benchmark_2026-04-20.json"
    md_path = REPORT_DIR / "paddlevl_vs_minimax_10page_benchmark_2026-04-20.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(report), encoding="utf-8")
    print(json_path)
    print(md_path)
    print(json.dumps(report["paddle_average"], ensure_ascii=False, indent=2))
    print(json.dumps(report["minimax_average"], ensure_ascii=False, indent=2))
    print(report["winner"])


if __name__ == "__main__":
    main()
