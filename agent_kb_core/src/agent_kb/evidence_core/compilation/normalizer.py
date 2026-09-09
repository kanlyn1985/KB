# -*- coding: utf-8 -*-
"""L1 Preprocessor + L2 SemanticNormalizer（V0.2_COMPILATION_PIPELINE L1/L2）。"""
from __future__ import annotations

import re
import unicodedata

from agent_kb.evidence_core.compilation.errors import (
    E_COMPILER_INVALID_EVIDENCE,
    E_NORMALIZATION_FAILED,
    CompilationError,
)
from agent_kb.evidence_core.compilation.models import NormalizedSegment, TextSegment

NORMALIZER_VERSION = "norm-v1.0"

# N-04 全角→半角映射（常见标点）
_WIDTH_MAP = {ord(f): ord(t) for f, t in zip(
    "，。：；！？（）【】《》“”‘’",
    ",.:;!?()[]<>\"\"''")}
_WIDTH_MAP.update({ord(c): ord(c) - 0xFEE0 for c in
                   "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
                   "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"})

_UNIT_MAP = {"Ω": "ohm", "μF": "uF", "µF": "uF"}


class Preprocessor:
    """L1：Evidence → list[TextSegment]（span 保留；只读；顺序稳定）。"""

    def segment(self, evidence) -> list[TextSegment]:
        content = evidence.content
        if not content or not content.strip():
            raise CompilationError(E_COMPILER_INVALID_EVIDENCE,
                                   f"evidence {evidence.evidence_id} content empty")
        segments: list[TextSegment] = []
        pos = 0
        seq = 0
        for raw in content.split("\n"):
            start = pos
            end = pos + len(raw)
            pos = end + 1  # +1 消耗换行符
            stripped = raw.strip()
            if not stripped:
                continue
            block_type = "heading" if self._looks_like_heading(stripped) else "text"
            # span 指向原文（含原缩进起点——定位首个非空白字符）
            offset = raw.find(stripped[0]) if stripped[0] != " " else 0
            segments.append(TextSegment(
                segment_id=f"seg_{seq:04d}", span_start=start + offset,
                span_end=start + len(raw.rstrip()), text=stripped, block_type=block_type))
            seq += 1
        if not segments:
            raise CompilationError(E_COMPILER_INVALID_EVIDENCE, "no substantive segments")
        return segments

    @staticmethod
    def _looks_like_heading(text: str) -> bool:
        return (len(text) <= 40 and not text.endswith(("。", ".", ";", "；"))
                and (re.match(r"^([0-9]+[.、]|[第][一二三四五六七八九十]+[章节条])", text)
                     is not None))


class SemanticNormalizer:
    """L2：N-01..N-08 顺序固定；纯函数；原文不动；rules_applied 可追溯。"""

    def normalize(self, segment: TextSegment) -> NormalizedSegment:
        try:
            text = segment.text
            applied: list[str] = []
            # N-01 Unicode NFC
            t = unicodedata.normalize("NFC", text)
            applied.append("N-01")
            # N-02 whitespace 归一
            t = re.sub(r"[ \t\r\f\v]+", " ", t).strip()
            t = re.sub(r" +", " ", t)
            applied.append("N-02")
            # N-03 段内控制字符清除（保留已分段的 \n 语义——段内不再有 \n）
            t = "".join(ch for ch in t if ch >= " " or ch == "\t")
            applied.append("N-03")
            # N-04 标点全角→半角
            t = t.translate(_WIDTH_MAP)
            applied.append("N-04")
            # N-05 数值归一（千分位去 + 规范 e 记号；不改变精度）
            t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
            t = re.sub(r"[×x]10\^?(-?\d+)", lambda m: f"e{m.group(1)}", t)
            applied.append("N-05")
            # N-06 单位归一（大小写敏感单位保持）
            for k, v in _UNIT_MAP.items():
                t = t.replace(k, v)
            applied.append("N-06")
            # N-07 日期归一 ISO-8601（相对表达保留原文由 Temporal Parser 处理）
            t = re.sub(r"(\d{4})年(\d{1,2})月(\d{1,2})日", r"\1-\2-\3", t)
            applied.append("N-07")
            # N-08 领域记号：V0.2 无 pack 注入时跳过（占位保持规则顺序完整）
            applied.append("N-08")
            return NormalizedSegment(segment_id=segment.segment_id, normalized_text=t,
                                     normalizer_version=NORMALIZER_VERSION,
                                     rules_applied=applied)
        except Exception as exc:  # 规则异常 → segment 级失败
            raise CompilationError(E_NORMALIZATION_FAILED, str(exc)) from exc