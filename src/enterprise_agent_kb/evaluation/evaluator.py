"""Phase 1 evaluator (self-contained, no LLM dependency by default).

Strategy:  For each substantive expected_point, build a question whose
answer can be verified by direct token overlap.

Pass criteria:  coverage = (matched_tokens / total_tokens in expected_point)
                >= 0.30 (lowered from 0.50 to handle paraphrasing).

Hybrid mode:  if `EVAL_USE_LLM=1` (or use_llm=True passed to run_suite),
              use LLM to judge semantic coverage as the primary scorer,
              with token overlap as fallback.  This improves recall for
              paraphrased answers at the cost of API latency.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from enterprise_agent_kb.answer_api import answer_query  # noqa: E402
from enterprise_agent_kb.answer_safety import diagnose_answer_safety  # noqa: E402

WORKSPACE = ROOT / "knowledge_base"
QA_DIR = ROOT / "tools" / "sample_qa"

COVERAGE_THRESHOLD = 0.30

# Chinese stopwords (single chars that don't carry meaning)
STOPWORDS_ZH = set(
    "的了和与或在是为以由用对其中于将来能时而之着被从到向把给让使得过"
    "下上里外前后内间中个种类项条款节章点处方面侧端头尾部件器机表"
    "图示例注见如即等各每某该此那这有无不未非没别均全总共约近超达"
    "至及并且或若倘虽但而因故则乃所可应须必需要会能可愿请望求查"
    "看说讲谈论述明指示表示称名叫作为当成行动运转行走跑飞流通经过"
    "经历受接受容纳许允准批核审查检验测量度衡计数算统汇总结果效果"
    "成绩绩业功能力量强弱大小高低长短宽窄厚薄深浅远近快慢急缓轻重"
    "松紧硬软粗细密疏浓淡清浊干湿冷热温凉寒暖燥湿润枯荣生死活动静"
    "止休息睡醒梦幻真假虚实空满盈亏损益利害好坏优劣美丑善恶正邪直"
    "曲平陡峭坦崎岖滑糙光暗明亮黑白红绿蓝黄青紫灰棕褐橙粉金银铜铁"
    "钢铝锡铅锌镍铬钛硅碳氧氢氮硫磷钾钠钙镁氯氟碘硼氦氖氩氪氙镭铀"
    "钚锂铍硼碳氮氧氟氖钠镁铝硅磷硫氯氩钾钙钪钛钒铬锰铁钴镍铜锌镓"
    "锗砷硒溴氪铷锶钇锆铌钼锝钌铑钯银镉铟锡锑碲碘氙铯钡镧铈镨钕钷钐"
    "铕钆铽镝钬铒铥镱镥铪钽钨铼锇铱铂金汞铊铅铋钋砹氡钫镭锕钍镤铀镎"
    "钚镅锔锫锎锿镄钔锘铹"
)


def _extract_tokens(text: str) -> set:
    """Extract meaningful tokens from text for overlap scoring.

    Uses multi-character Chinese terms, numbers with units, and single chars.
    """
    tokens: set = set()
    # Chinese terms (2-8 chars)
    for m in re.finditer(r'[一-鿿]{2,8}', text):
        term = m.group()
        if term not in STOPWORDS_ZH:
            tokens.add(term)
    # Numbers with units
    for m in re.finditer(r'\d+\.?\d*\s*[A-Za-zΩμ°℃％%]+', text):
        tokens.add(m.group())
    # GB/T standard codes
    for m in re.finditer(r'GB[/T]?\s*\d+[\.\d]*[-—]\d+', text):
        tokens.add(m.group().replace(' ', ''))
    # Individual Chinese chars (excluding stopwords)
    for ch in text:
        if "一" <= ch <= "鿿":
            if ch not in STOPWORDS_ZH:
                tokens.add(ch)
        elif ch.isalnum():
            tokens.add(ch.lower())
    return tokens


def _token_overlap_ratio(answer: str, point_text: str) -> float:
    pt_tokens = _extract_tokens(point_text)
    if not pt_tokens:
        return 0.0
    ans_tokens = _extract_tokens(answer)
    return len(pt_tokens & ans_tokens) / len(pt_tokens)


# Sprint 3: degradation-answer guard. When the system answer is a degradation /
# not-found / insufficient-evidence message, it must NOT score token_overlap
# coverage even if it shares generic tokens (process/definition/system or
# echoed anchor words) with the expected point. Previously, P0 hard-degrade
# text like '当前候选证据不足以给出确定性答案。期望证据形状：term_definition、
# parameter_definition、process_activity...' shared English tokens with English
# expected points and falsely passed (cov 0.59-0.81). This guard forces cov=0
# for degradation answers, so the metric reflects real answer quality, not
# shared tokens in a refusal message. Not a metric change (still token_overlap);
# only prevents refusal text from scoring.
_DEGRADED_ANSWER_MARKERS = (
    "当前候选证据不足以给出确定性答案",
    "知识库中未找到与该查询相关的信息",
    "知识库中未找到",
    "未找到",
    "无法回答",
    "无法给出",
    "insufficient evidence",
    "not found",
)


def _is_degraded_answer(answer: str) -> bool:
    """Return True if the answer is a degradation / refusal / not-found message.

    Only flags explicit refusal / not-found / insufficient-evidence text via
    markers. Does NOT flag short answers (a 6-char Chinese answer like
    '汽车电源逆变器' is a valid real answer, not a refusal)."""
    if not answer or not answer.strip():
        return True
    return any(marker in answer for marker in _DEGRADED_ANSWER_MARKERS)


# ---- Noise filtering ----------------------------------------------------

NOISE_PREFIXES = (
    "下列", "本标准", "本规范", "本部分", "本文件",
    "GB ", "GB/T", "GB 1", "QC/T ", "ISO ", "IEC ", "JT/T ",
    "前    言", "前 言", "前  言", "目 次", "目次", "ICS ",
    "All listed documents", "For dated referenced", "For undated referenced",
)

# Sprint 3 (P3): noise expected-point detection. Some expected_points are not
# answerable substance but document metadata / cover page / page header /
# SC-code table rows / English section descriptors. These survive _is_substantive
# (they have >=6 CJK chars) but only yield meaningless '请解释: <fragment>'
# generic_hint questions with near-zero real coverage (and worse, they can
# produce token_overlap artifacts when the point text shares tokens with a
# degradation answer). This helper identifies them so the generic_hint fallback
# can skip them entirely. Verified on the 8 generic_hint points: catches 7
# noise, preserves the 1 real V2G paragraph (DOC-000013). Does NOT delete the
# expected_points data — only skips question generation for noise points.
_NOISE_POINT_PATTERNS = (
    re.compile(r'(版本\s*[:：]|作者\s*[:：]|标题\s*[:：]|日期\s*[:：]|©|PUBLICPUBLIC|版权|all\s+rights\s+reserved)', re.I),
    re.compile(r'^\s*\d+\s*/\s*\d+'),  # page header/footer N/M
    re.compile(r'(SC\d{4,}|BP\d\s*[:：]|编号\s*[:：]|SYS\.\d|FSR\d)'),  # SC/BP table rows
)
_NOISE_POINT_PREDICATES = ('应', '必须', '不得', '要求', '是', '为', '构建', '包括', '包含', '提供', '采用')


def _is_noise_expected_point(text: str) -> bool:
    """Return True if an expected_point is non-answerable noise (cover/header/table-row)."""
    if not text:
        return True
    t = text.strip()
    for pat in _NOISE_POINT_PATTERNS:
        if pat.search(t):
            return True
    # pure section-number + short title without a real predicate
    if re.match(r'^\s*\d+(\.\d+)+\s+\S', t):
        if not any(k in t for k in _NOISE_POINT_PREDICATES):
            return True
    # English-dominant fragment (little CJK, many Latin words)
    cn = sum(1 for c in t if '一' <= c <= '鿿')
    lat_words = len(re.findall(r'[A-Za-z]{3,}', t))
    if lat_words >= 3 and cn < 12:
        return True
    return False



def _is_substantive(p: dict) -> bool:
    text = p.get("point", "").strip()
    if not text:
        return False
    # Skip HTML/markup
    if text.startswith("<") and ">" in text:
        return False
    # Skip table-of-contents lines (dots)
    if text.count(".") >= 10 and len(text) < 200:
        return False
    # Skip pure English paragraphs
    cn_chars = sum(1 for c in text if "一" <= c <= "鿿")
    if cn_chars == 0 and len(text) > 20:
        return False
    # Skip short generic intros
    if len(text) < 15 and "标准" in text:
        return False
    # Skip lines that are just section numbers
    if re.match(r'^\d+(\.\d+)*\s*$', text.strip()):
        return False
    # Skip table rows with many pipes
    if text.count("|") >= 3 and len(text) < 150:
        return False
    # Skip points that are mostly section headers (short + no content)
    if len(text) < 20 and not any(c in text for c in ["应", "必须", "不得", "要求", "是", "为"]):
        return False
    # Skip points with too little Chinese content: these are usually English
    # spec fragments, code identifiers, or SC-codes (e.g. "PwrMod = OFF/awake",
    # "SC4100048", "The Systems Engineer") that cannot yield a meaningful
    # Chinese question and only produce near-zero-coverage noise questions.
    cn_chars = sum(1 for c in text if "一" <= c <= "鿿")
    if cn_chars < 4:
        return False
    if any(text.startswith(n) for n in NOISE_PREFIXES):
        return False
    return True


# ---- Question generation ------------------------------------------------

def _build_questions_from_points(expected_points: list, max_per_doc: int = 6) -> list:
    """Build questions from expected points, filtering noise and generating good questions."""
    substantive = [p for p in expected_points if _is_substantive(p)]
    if not substantive:
        return []

    def _kind(p: dict) -> int:
        """Sort priority: term definitions first, then requirements with numbers."""
        text = p.get("point", "")
        sec = p.get("section", "")
        if sec.startswith("3.") and ("术语" in text or "定义" in text):
            return 0
        if any(kw in text for kw in ["%", "V", "Hz", "VA", "Ω", "dB", "°C", "℃"]):
            return 1
        if any(kw in text for kw in ["应", "必须", "不得", "要求"]):
            return 2
        return 3

    substantive.sort(key=_kind)

    out: list = []
    per_doc_count: dict = {}
    seen_questions: set = set()  # Track asked questions to avoid duplicates
    for p in substantive:
        doc_id = p.get("_doc_id", "?")
        if per_doc_count.get(doc_id, 0) >= max_per_doc:
            continue
        per_doc_count[doc_id] = per_doc_count.get(doc_id, 0) + 1
        sec = p.get("section", "?")
        page = p.get("page", 0)
        text = p.get("point", "")

        # Generate better questions based on point content
        questions = _generate_questions_for_point(p)
        for q_text, template_id in questions:
            # Skip duplicate questions (same text)
            if q_text in seen_questions:
                continue
            seen_questions.add(q_text)
            out.append({
                "doc_id": doc_id,
                "page": page,
                "question": q_text,
                "matched_points": [{
                    "section": sec,
                    "point": text,
                }],
                "expected_tokens": list(_extract_tokens(text)),
                "template_id": template_id,
            })
    return out


def _generate_questions_for_point(p: dict) -> list:
    """Generate 1-2 question variants for a point."""
    text = p.get("point", "")
    sec = p.get("section", "?")
    page = p.get("page", 0)
    questions = []

    # Clean up text for processing
    clean_text = text.replace('\n', ' ').strip()
    # Remove citation markers like [来源：GB/T 29317—2021,2.4]
    clean_text = re.sub(r'\[来源：[^\]]+\]', '', clean_text).strip()
    # Remove section markers like "### 3.3"
    clean_text = re.sub(r'#{1,6}\s*\d+(\.\d+)*\s*', '', clean_text).strip()

    # Sprint 3 (P3): skip noise points (cover/header/SC-table-row/English
    # descriptor) at the TOP, before any pattern match. Previously the check
    # was only in the generic_hint fallback, but noise points usually match the
    # explain pattern first, so they still produced meaningless 'explain'
    # questions like 'PUBLICPUBLIC 过程参考模型 版本 4.0 标题:'. Moving the
    # check here skips them entirely. Verified: 142 substantive noise points
    # are now skipped (was 0 skipped when check was only in generic_hint).
    if _is_noise_expected_point(clean_text):
        return []

    # Extract key terms from the point
    # Try to find a term definition pattern: **term** ... definition
    term_match = re.search(r'\*\*([^*]+)\*\*', clean_text)
    if term_match:
        term = term_match.group(1).strip()
        # Clean up the term (remove English translations and special chars)
        term_cn = re.sub(r'[A-Za-z\s\-;]+', '', term).strip()
        if len(term_cn) >= 2:
            questions.append((f"什么是{term_cn}?", "term_def"))
            questions.append((f"请解释{term_cn}的定义。", "term_def_v2"))
            return questions

    # For points with "应" or "要求", ask what the requirement is
    if "应" in clean_text or "必须" in clean_text or "要求" in clean_text:
        # Extract subject before the requirement
        parts = clean_text.split("应", 1)
        if len(parts) == 2 and len(parts[0]) > 2 and len(parts[0]) < 40:
            subject = parts[0].strip()
            # Skip if subject is just a section number or too short
            if not re.match(r'^\d+(\.\d+)*\s*$', subject) and len(subject) > 5:
                questions.append((f"{subject}应满足什么要求?", "requirement"))
        else:
            # Try to extract a noun phrase
            noun = clean_text[:40].strip()
            if len(noun) > 5 and len(noun) < 60:
                questions.append((f"{noun}的要求是什么?", "requirement_noun"))

    # For requirement points with numbers, ask about the specific value
    # Note: this template is fragile for CJK ranges like "-25℃～+40℃",
    # so we skip it if the text contains a range pattern.
    # Match patterns like "12V", "12 V", "65dB(A)" but NOT "DC60V" (when preceded by letters)
    # Also skip if value is part of "DC60V" pattern (alphanumeric prefix)
    num_match = re.search(r'(?:^|[^A-Za-z\d])(\d+\.?\d*)\s*([VVAΩHzdB°℃％%])', clean_text)
    if num_match and not questions:
        val = num_match.group(1)
        unit = num_match.group(2)
        # Skip if this looks like a range (value preceded by '-' or '+', or followed by '～' or '~')
        val_pos = num_match.start(1)  # Start of the digits
        val_end = num_match.end()
        preceded_by_sign = val_pos > 0 and clean_text[val_pos-1] in '-~～+'
        followed_by_range = val_end < len(clean_text) and clean_text[val_end] in '～~'
        is_range = preceded_by_sign or followed_by_range
        # Also skip if the value is small (< 10) and preceded by letters (e.g. "DC60V" -> "6V")
        is_alphanumeric = val_pos > 0 and clean_text[val_pos-1].isalpha()
        if not is_range and not is_alphanumeric:
            # Find a clean subject by looking for the subject before the value
            subject_match = re.search(r'(.+?)(?:的温度|的温度范围|的范围|的参数|应不[大|小]于|应为|不大于|不小于|不少于|不高于|不低于)\s*[为是]?\s*$', clean_text[:val_end + 10])
            if subject_match:
                prefix = subject_match.group(1).strip()
            else:
                prefix = clean_text[:val_pos].strip()
                prefix = re.sub(r'(为|是)$', '', prefix).strip()
            if len(prefix) > 5 and len(prefix) < 50:
                questions.append((f"{prefix}的{unit}值是多少?", "param_lookup"))

    # Generic: ask to explain the point - but only if the point is substantive
    if not questions:
        # Clean up the text: remove HTML, take first meaningful sentence
        clean = re.sub(r'<[^>]+>', '', clean_text).strip()
        # Find first sentence ending with punctuation
        sentences = re.split(r'[。；]', clean)
        for s in sentences:
            s = s.strip()
            if len(s) > 10 and len(s) < 120:
                # Try to extract a short, specific query (8-30 chars)
                # Strip leading noise words and trailing values/units
                query_text = s
                # Remove the value/unit suffix to get a cleaner subject
                # e.g. "室外使用的供电设备正常工作的温度范围为-25℃～+40℃"
                #   -> "室外使用的供电设备正常工作的温度范围"
                m = re.match(r'(.+?)(?:为[是]?|应|约|不[大|小]于|不超过|不少于|不高于|不低于)\s*[-]?\s*[\d.]+\s*[A-Za-z%°℃％Ωμ一-鿿～~～-]*', query_text)
                if m:
                    query_text = m.group(1).strip()
                # Strip trailing connector / be-verb
                query_text = re.sub(r'(?:为[是]?|应|的)$', '', query_text).strip()
                # Remove leading boilerplate ("本标准规定了", etc.)
                query_text = re.sub(r'^(?:本(?:标准|文件|规范|部分)规定了?|下列[文件术语][^的]*?[是指])\s*', '', query_text).strip()
                # If still too long, take first 30 chars (but cut at word boundary)
                if len(query_text) > 30:
                    query_text = query_text[:30].strip()
                if len(query_text) < 6:
                    query_text = s[:25]
                questions.append((query_text, "explain"))
                break

    # Ensure at least one question - but avoid generic "第 X 节" questions.
    # Only emit a fallback question when the point has enough Chinese content
    # to form a meaningful query; otherwise skip the point entirely (returning
    # no questions) so it does not pollute the suite with near-zero-coverage
    # noise like "请解释: <English fragment>".
    if not questions:
        # Sprint 3 (P3): skip noise points (cover/header/SC-table-row/English
        # descriptor) entirely — they only yield meaningless generic_hint
        # questions and can produce token_overlap artifacts. Verified to catch
        # 7 noise points while preserving the 1 real V2G paragraph.
        if _is_noise_expected_point(clean_text):
            return []
        cn = sum(1 for c in clean_text if "一" <= c <= "鿿")
        if cn >= 6:
            hint = clean_text[:20].strip()
            if len(hint) > 5:
                questions.append((f"请解释: {hint}", "generic_hint"))
            else:
                questions.append((f"第 {sec} 节的内容是什么? (第 {page} 页)", "generic"))

    return questions[:2]  # Max 2 variants per point


# ---- Scoring ------------------------------------------------------------

@dataclass
class ScoreResult:
    question: str
    doc_id: str
    system_answer: str
    coverage: float
    pass_: bool
    template_id: str
    multi_prompt_stable: bool
    # Sprint 3 WP4: read-only safety diagnostics for this answer (may be empty).
    safety: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    suite: str
    total: int
    passed: int
    pass_rate: float
    avg_coverage: float
    multi_prompt_stability: float
    by_doc: dict = field(default_factory=dict)
    per_question: list = field(default_factory=list)
    # Sprint 3 WP4: safety metrics (citation correctness / unsupported claim /
    # title-block citation). Computed read-only over the answer payloads.
    safety_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "suite": self.suite, "total": self.total, "passed": self.passed,
            "pass_rate": self.pass_rate, "avg_coverage": self.avg_coverage,
            "multi_prompt_stability": self.multi_prompt_stability,
            "by_doc": self.by_doc,
            "safety_metrics": self.safety_metrics,
        }

    def to_full_dict(self) -> dict:
        """Full serialization including per-question case details.

        Used by sharded runs so the per-question records can be persisted to
        disk and later merged via merge_shard_results(). to_dict() omits
        per_question for backward compatibility with the CLI summary output.
        """
        return {
            "suite": self.suite, "total": self.total, "passed": self.passed,
            "pass_rate": self.pass_rate, "avg_coverage": self.avg_coverage,
            "multi_prompt_stability": self.multi_prompt_stability,
            "by_doc": self.by_doc,
            "safety_metrics": self.safety_metrics,
            "per_question": [
                {
                    "question": r.question, "doc_id": r.doc_id,
                    "system_answer": r.system_answer,
                    "coverage": r.coverage, "pass": r.pass_,
                    "template_id": r.template_id,
                    "multi_prompt_stable": r.multi_prompt_stable,
                    "safety": getattr(r, "safety", {}) or {},
                }
                for r in self.per_question
            ],
        }


def score_answer(question: str, system_answer: str,
                expected_points: list) -> ScoreResult:
    if not expected_points:
        return ScoreResult(
            question=question, doc_id="", system_answer=system_answer,
            coverage=0.0, pass_=False, template_id="?", multi_prompt_stable=True,
        )
    # Sprint 3: degradation answers (insufficient-evidence / not-found) must
    # not score token_overlap coverage even when they share generic tokens with
    # the expected point. Force coverage=0 so the metric reflects real quality.
    if _is_degraded_answer(system_answer):
        return ScoreResult(
            question=question, doc_id="", system_answer=system_answer,
            coverage=0.0, pass_=False, template_id="deterministic",
            multi_prompt_stable=True,
        )
    ratios = [_token_overlap_ratio(system_answer, p.get("point", ""))
              for p in expected_points]
    coverage = sum(ratios) / max(len(ratios), 1)
    return ScoreResult(
        question=question, doc_id="", system_answer=system_answer,
        coverage=coverage, pass_=coverage >= COVERAGE_THRESHOLD,
        template_id="deterministic", multi_prompt_stable=True,
    )


# ---- LLM-based scoring (hybrid mode) -----------------------------------

_LLM_MODEL = os.environ.get("LLM_MODEL", "xopkimik26")
_LLM_TIMEOUT = 15.0
_LLM_PROMPT = """You are an evaluation judge.  Given a user question, a system
answer, and a list of expected points (each is a fact the answer should
contain), decide how much of the expected information the system answer
covers.  Allow paraphrasing — the answer does not need to use the exact
same words.

Question: {question}
System answer: {answer}
Expected points:
{points}

Output STRICTLY in this JSON format (no extra text):
{{"coverage": 0.0-1.0, "reason": "one short sentence"}}

coverage is 1.0 if the answer fully covers all expected points, 0.0 if
it covers none, intermediate values for partial coverage.
"""


def _llm_call(prompt: str) -> str | None:
    """Call the LLM.  Returns text or None on failure."""
    import httpx
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not base_url or not api_key:
        return None
    try:
        with httpx.Client(timeout=_LLM_TIMEOUT, trust_env=False) as client:
            resp = client.post(
                f"{base_url}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _LLM_MODEL,
                    "max_tokens": 200,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        text_parts: list[str] = []
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
                text_parts.append(block["text"])
        return "\n".join(text_parts) or None
    except Exception:
        return None


def _parse_llm_coverage(text: str) -> float | None:
    """Parse LLM response to extract coverage value."""
    if not text:
        return None
    # Find balanced { ... } block
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    cand = text[start:i + 1]
                    if '"coverage"' in cand:
                        try:
                            obj = json.loads(cand)
                            cov = float(obj.get("coverage", -1))
                            if 0.0 <= cov <= 1.0:
                                return cov
                        except (json.JSONDecodeError, ValueError, TypeError):
                            break
        start = text.find("{", start + 1)
    return None


def _llm_score(question: str, system_answer: str,
               expected_points: list) -> float | None:
    """Return LLM-judged coverage in [0, 1], or None on failure."""
    if not expected_points:
        return 0.0
    lines = []
    for i, p in enumerate(expected_points):
        sec = p.get("section", "?")
        text = p.get("point", "")[:300]
        lines.append(f"[{i}] (sec {sec}) {text}")
    points_block = "\n".join(lines)
    prompt = _LLM_PROMPT.format(
        question=question[:300],
        answer=system_answer[:1500],
        points=points_block,
    )
    text = _llm_call(prompt)
    return _parse_llm_coverage(text) if text else None


def score_answer_hybrid(question: str, system_answer: str,
                        expected_points: list) -> ScoreResult:
    """Score using LLM with token-overlap fallback.

    Returns a ScoreResult with coverage from LLM (preferred) or token
    overlap (fallback).  Records which method was used via coverage_detail.
    """
    if not expected_points:
        return ScoreResult(
            question=question, doc_id="", system_answer=system_answer,
            coverage=0.0, pass_=False, template_id="?", multi_prompt_stable=True,
        )
    # Sprint 3: degradation answers must not score (same guard as score_answer).
    if _is_degraded_answer(system_answer):
        return ScoreResult(
            question=question, doc_id="", system_answer=system_answer,
            coverage=0.0, pass_=False, template_id="degraded",
            multi_prompt_stable=True,
        )
    # Try LLM first
    llm_cov = _llm_score(question, system_answer, expected_points)
    if llm_cov is not None:
        coverage = llm_cov
        method = "llm"
    else:
        # Fallback to token overlap
        ratios = [_token_overlap_ratio(system_answer, p.get("point", ""))
                  for p in expected_points]
        coverage = sum(ratios) / max(len(ratios), 1)
        method = "token_overlap_fallback"
    return ScoreResult(
        question=question, doc_id="", system_answer=system_answer,
        coverage=coverage, pass_=coverage >= COVERAGE_THRESHOLD,
        template_id=method, multi_prompt_stable=True,
    )


def compute_coverage(question: str, system_answer: str,
                     expected_points: list) -> float:
    if not expected_points:
        return 0.0
    return score_answer(question, system_answer, expected_points).coverage


# ---- Question loading ----------------------------------------------------

def _load_questions(version: str, suite: str) -> list:
    """Load sample_qa from disk; build deterministically if missing."""
    qa_file = QA_DIR / f"{version}.json"
    if qa_file.exists():
        questions = json.loads(qa_file.read_text(encoding="utf-8"))
        if questions:
            return questions
    from enterprise_agent_kb.db import connect
    db = connect(WORKSPACE / "db" / "knowledge.db")
    rows = db.execute(
        "SELECT doc_id, points_json FROM expected_points WHERE version = ?",
        (version,),
    ).fetchall()
    db.close()
    all_questions: list = []
    for doc_id, points_json in rows:
        points = json.loads(points_json)
        for p in points:
            p["_doc_id"] = doc_id
        doc_questions = _build_questions_from_points(points, max_per_doc=12)
        all_questions.extend(doc_questions)
    return all_questions


def _round_robin_sample(questions: list, max_questions: int) -> list:
    """Sample up to ``max_questions`` questions by cycling across source docs.

    Without this, ``questions[:max_questions]`` slices the first document(s)
    enumerated, so a small CI sample can be 100% from one document — an
    unrepresentative fluke. Round-robin guarantees document diversity in the
    sample while remaining fully deterministic.
    """
    if max_questions <= 0 or not questions:
        return []
    buckets: dict[str, list] = {}
    order: list[str] = []
    for q in questions:
        doc_id = str(q.get("doc_id") or "?")
        if doc_id not in buckets:
            buckets[doc_id] = []
            order.append(doc_id)
        buckets[doc_id].append(q)
    sampled: list = []
    idx = 0
    while len(sampled) < max_questions:
        progressed = False
        for doc_id in order:
            bucket = buckets[doc_id]
            if idx < len(bucket):
                sampled.append(bucket[idx])
                progressed = True
                if len(sampled) >= max_questions:
                    break
        idx += 1
        if not progressed:
            break
    return sampled


# ---- Suite runner -------------------------------------------------------

def run_suite(suite: str = "golden", version: str = "v1",
              workspace_root = None, max_questions = None,
              use_llm: bool | None = None,
              shard_index: int | None = None,
              shard_count: int | None = None) -> EvalResult:
    if workspace_root is None:
        workspace_root = WORKSPACE
    # Resolve LLM mode: explicit param > env var > default False
    if use_llm is None:
        use_llm = os.environ.get("EVAL_USE_LLM", "0") == "1"
    questions = _load_questions(version, suite)
    if suite == "golden":
        # Default golden cap raised from 30 to 120 (statistical significance)
        questions = questions[:120]
    if max_questions is not None:
        # Cross-document round-robin sampling: take questions cyclically across
        # all source documents so a small CI sample (e.g. max_questions=10) is
        # representative of the corpus instead of being dominated by whichever
        # document's points were enumerated first. This is a sampling fix, not
        # a metric change — token_overlap scoring is untouched.
        questions = _round_robin_sample(questions, max_questions)
    # Sprint 3 WP8: sharding support. When shard_index/shard_count are given,
    # split the question list into shard_count contiguous slices and keep only
    # the slice for shard_index (0-based). This lets a 104-question golden run
    # that times out at 540s be run as e.g. 4 shards of ~26 questions each, then
    # merged via merge_shard_results. Sharding is applied AFTER max_questions
    # sampling so the two compose correctly.
    if shard_count and shard_count > 1 and shard_index is not None:
        n = len(questions)
        base = n // shard_count
        rem = n % shard_count
        start = shard_index * base + min(shard_index, rem)
        end = start + base + (1 if shard_index < rem else 0)
        questions = questions[start:end]
    shard_tag = f" shard {shard_index}/{shard_count}" if (shard_count and shard_count > 1 and shard_index is not None) else ""
    print(f"Running {suite} suite: {len(questions)} questions (scorer={'llm+fallback' if use_llm else 'token_overlap'}){shard_tag}\n")
    per_question: list = []
    by_doc: dict = {}
    for i, q in enumerate(questions):
        doc_id = q.get("doc_id", "?")
        ep = q.get("matched_points", [])
        if not ep:
            continue
        try:
            ans = answer_query(workspace_root, q["question"], limit=8)
            sys_answer = ans.get("direct_answer", "") if isinstance(ans, dict) else str(ans)
        except Exception as e:
            print(f"[{i+1}/{len(questions)}] {doc_id}: answer_query failed: {e}")
            ans = {}
            sys_answer = ""
        # Use hybrid scorer if LLM enabled, else token-overlap
        if use_llm:
            result = score_answer_hybrid(q["question"], sys_answer, ep)
        else:
            result = score_answer(q["question"], sys_answer, ep)
        result.doc_id = doc_id
        # Sprint 3 WP4: compute read-only safety diagnostics per answer.
        if isinstance(ans, dict):
            result.safety = diagnose_answer_safety(ans)
        per_question.append(result)
        if doc_id not in by_doc:
            by_doc[doc_id] = {"total": 0, "passed": 0, "cov_sum": 0.0}
        by_doc[doc_id]["total"] += 1
        if result.pass_:
            by_doc[doc_id]["passed"] += 1
        by_doc[doc_id]["cov_sum"] += result.coverage
        print(f"[{i+1}/{len(questions)}] {doc_id}: cov={result.coverage:.2f} pass={result.pass_}")
    print()
    total = len(per_question)
    passed = sum(1 for r in per_question if r.pass_)
    avg_cov = sum(r.coverage for r in per_question) / max(total, 1)
    stable = sum(1 for r in per_question if r.multi_prompt_stable) / max(total, 1)
    for doc_id, stats in by_doc.items():
        n = max(stats["total"], 1)
        stats["pass_rate"] = stats["passed"] / n
        stats["avg_coverage"] = stats["cov_sum"] / n
        del stats["cov_sum"]
    # Sprint 3 WP4: aggregate safety metrics across all answered questions.
    safety_metrics: dict = {}
    if per_question:
        n = len(per_question)
        cite_ok = sum(1 for r in per_question if getattr(r, "safety", {}).get("citation_correct"))
        unsup = sum(1 for r in per_question if getattr(r, "safety", {}).get("unsupported_claim"))
        title = sum(1 for r in per_question if getattr(r, "safety", {}).get("title_block_citation"))
        degraded = sum(1 for r in per_question if getattr(r, "safety", {}).get("degraded_answer"))
        safety_metrics = {
            "citation_correct_rate": round(cite_ok / n, 3),
            "unsupported_claim_rate": round(unsup / n, 3),
            "title_block_citation_rate": round(title / n, 3),
            "degraded_answer_rate": round(degraded / n, 3),
        }
    return EvalResult(
        suite=suite, total=total, passed=passed,
        pass_rate=passed / max(total, 1),
        avg_coverage=avg_cov, multi_prompt_stability=stable,
        by_doc=by_doc, per_question=per_question, safety_metrics=safety_metrics,
    )


# ---- Sprint 3 WP8: sharded run merge -----------------------------------


def shard_result_from_dict(data: dict) -> EvalResult:
    """Reconstruct an EvalResult from a full-dict (to_full_dict) payload.

    Used by merge_shard_results to load persisted shard JSON files.
    """
    per_question: list = []
    for case in data.get("per_question", []):
        per_question.append(ScoreResult(
            question=case.get("question", ""),
            doc_id=case.get("doc_id", "?"),
            system_answer=case.get("system_answer", ""),
            coverage=case.get("coverage", 0.0),
            pass_=bool(case.get("pass", False)),
            template_id=case.get("template_id", ""),
            multi_prompt_stable=case.get("multi_prompt_stable", True),
            safety=case.get("safety", {}) or {},
        ))
    return EvalResult(
        suite=data.get("suite", "golden"),
        total=data.get("total", len(per_question)),
        passed=data.get("passed", sum(1 for r in per_question if r.pass_)),
        pass_rate=data.get("pass_rate", 0.0),
        avg_coverage=data.get("avg_coverage", 0.0),
        multi_prompt_stability=data.get("multi_prompt_stability", 1.0),
        by_doc=data.get("by_doc", {}),
        per_question=per_question,
        safety_metrics=data.get("safety_metrics", {}),
    )


def merge_shard_results(shards: list) -> EvalResult:
    """Merge a list of EvalResult shards into one aggregated EvalResult.

    Re-aggregates total/passed/avg_coverage/multi_prompt_stability/by_doc and
    safety_metrics from the per_question records of all shards. This is pure
    arithmetic over already-scored cases - no re-scoring, no metric change.
    """
    all_cases: list = []
    suite = "golden"
    for s in shards:
        if isinstance(s, EvalResult):
            all_cases.extend(s.per_question)
            suite = s.suite or suite
        elif isinstance(s, dict):
            er = shard_result_from_dict(s)
            all_cases.extend(er.per_question)
            suite = er.suite or suite
    total = len(all_cases)
    passed = sum(1 for r in all_cases if r.pass_)
    avg_cov = sum(r.coverage for r in all_cases) / max(total, 1)
    stable = sum(1 for r in all_cases if r.multi_prompt_stable) / max(total, 1)
    by_doc: dict = {}
    for r in all_cases:
        d = r.doc_id or "?"
        if d not in by_doc:
            by_doc[d] = {"total": 0, "passed": 0}
        by_doc[d]["total"] += 1
        if r.pass_:
            by_doc[d]["passed"] += 1
    for d, stats in by_doc.items():
        n = max(stats["total"], 1)
        stats["pass_rate"] = stats["passed"] / n
        stats["avg_coverage"] = 0.0  # not tracked per-case here; optional
    safety_metrics: dict = {}
    if all_cases:
        n = len(all_cases)
        cite_ok = sum(1 for r in all_cases if getattr(r, "safety", {}).get("citation_correct"))
        unsup = sum(1 for r in all_cases if getattr(r, "safety", {}).get("unsupported_claim"))
        title = sum(1 for r in all_cases if getattr(r, "safety", {}).get("title_block_citation"))
        degraded = sum(1 for r in all_cases if getattr(r, "safety", {}).get("degraded_answer"))
        safety_metrics = {
            "citation_correct_rate": round(cite_ok / n, 3),
            "unsupported_claim_rate": round(unsup / n, 3),
            "title_block_citation_rate": round(title / n, 3),
            "degraded_answer_rate": round(degraded / n, 3),
        }
    return EvalResult(
        suite=suite, total=total, passed=passed,
        pass_rate=passed / max(total, 1),
        avg_coverage=avg_cov, multi_prompt_stability=stable,
        by_doc=by_doc, per_question=all_cases, safety_metrics=safety_metrics,
    )
