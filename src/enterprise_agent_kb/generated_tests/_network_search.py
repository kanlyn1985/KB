"""Network search and metadata extraction helpers used by golden-case generation.

This module isolates the "talk to the public internet" concern (DuckDuckGo HTML
search, arbitrary page fetching) from the rest of the generated-tests pipeline.
It deliberately contains no KB or LLM dependencies so it can be tested in
isolation with httpx.MockTransport.
"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

NETWORK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/124.0 Safari/537.36"
)
DUCKDUCKGO_ENDPOINT = "https://html.duckduckgo.com/html/"
NETWORK_TIMEOUT_SECONDS = 8.0
PAGE_FETCH_TIMEOUT_SECONDS = 6.0
MAX_HIT_COUNT = 8
MAX_PAGE_TEXT_CHARS = 5000


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _resolve_duckduckgo_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    parsed = urlparse(raw_url)
    if "duckduckgo.com" not in parsed.netloc:
        return raw_url
    uddg = parse_qs(parsed.query).get("uddg")
    if not uddg:
        return ""
    return unquote(uddg[0])


def search_duckduckgo(
    query: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[dict[str, str]]:
    """Return up to 8 DuckDuckGo HTML result hits for *query*.

    Network/timeout errors return an empty list instead of raising so the
    caller can degrade gracefully.
    """
    client_kwargs: dict[str, object] = {
        "params": {"q": query},
        "headers": {"User-Agent": NETWORK_USER_AGENT},
        "timeout": NETWORK_TIMEOUT_SECONDS,
        "follow_redirects": True,
    }
    try:
        if transport is not None:
            with httpx.Client(transport=transport) as client:
                response = client.get(DUCKDUCKGO_ENDPOINT, **client_kwargs)
        else:
            response = httpx.get(DUCKDUCKGO_ENDPOINT, **client_kwargs)
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.NetworkError):
        return []

    hits: list[dict[str, str]] = []
    title_matches = list(
        re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            response.text,
            re.S,
        )
    )
    snippet_matches = list(
        re.finditer(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>'
            r'|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>',
            response.text,
            re.S,
        )
    )

    for index, match in enumerate(title_matches[:MAX_HIT_COUNT]):
        raw_url = html.unescape(match.group(1))
        title = _strip_html(html.unescape(match.group(2)))
        snippet = ""
        if index < len(snippet_matches):
            body = snippet_matches[index].group(1) or snippet_matches[index].group(2) or ""
            snippet = _strip_html(html.unescape(body))
        url = _resolve_duckduckgo_url(raw_url)
        if url:
            hits.append({"title": title, "snippet": snippet, "url": url})
    return hits


def fetch_page_text(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Fetch *url* and return plain text, truncated to MAX_PAGE_TEXT_CHARS.

    Returns "" on any network/timeout/URL-shape error so the caller can
    fall back to local-only case generation.
    """
    if not url.startswith(("http://", "https://")):
        return ""
    client_kwargs: dict[str, object] = {
        "headers": {"User-Agent": NETWORK_USER_AGENT},
        "timeout": PAGE_FETCH_TIMEOUT_SECONDS,
        "follow_redirects": True,
    }
    try:
        if transport is not None:
            with httpx.Client(transport=transport) as client:
                response = client.get(url, **client_kwargs)
        else:
            response = httpx.get(url, **client_kwargs)
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.NetworkError):
        return ""

    return re.sub(r"\s+", " ", _strip_html(response.text)).strip()[:MAX_PAGE_TEXT_CHARS]


def _unique_matches(pattern: str, text: str, *, flags: int = 0) -> list[str]:
    seen: list[str] = []
    for match in re.finditer(pattern, text, flags):
        value = match.group(0).strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _extract_candidate_titles(text: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"<title[^>]*>(.*?)</title>", text, re.S | re.I):
        title = _strip_html(html.unescape(match.group(1)))
        if 4 <= len(title) <= 120:
            candidates.append(title)
    return candidates[:5]


def _extract_scope_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for match in re.finditer(
        r"[^。\n]{6,160}(?:范围|适用于|本标准)[^。\n]{0,80}",
        text,
    ):
        sentence = re.sub(r"\s+", " ", match.group(0)).strip()
        if sentence and sentence not in sentences:
            sentences.append(sentence)
    return sentences[:4]


def _extract_organizations(text: str) -> list[str]:
    seen: list[str] = []
    for match in re.finditer(
        r"[一-鿿]{2,12}(?:研究院|委员会|标准化|技术中心|发布|发布机构)",
        text,
    ):
        org = match.group(0).strip()
        if org and org not in seen:
            seen.append(org)
    return seen[:5]


def extract_network_metadata(text: str) -> dict[str, list[str]]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return {
        "standard_codes": _unique_matches(
            r"(?:GB/T|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[-—]\d{2,4})?",
            cleaned,
        ),
        "dates": _unique_matches(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", cleaned),
        "status": _unique_matches(
            r"(?:Status[:：]?\s*[A-Za-z]+|现行|有效|Valid)",
            cleaned,
            flags=re.I,
        ),
        "titles": _extract_candidate_titles(cleaned),
        "scope": _extract_scope_sentences(cleaned),
        "organizations": _extract_organizations(cleaned),
    }
