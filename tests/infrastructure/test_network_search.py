"""Unit tests for the extracted _network_search module.

Covers DuckDuckGo HTML search, page text fetch, and metadata extraction
using httpx.MockTransport so the tests run offline and deterministically.
"""
from __future__ import annotations

import httpx
import pytest

from enterprise_agent_kb.generated_tests._network_search import (
    DUCKDUCKGO_ENDPOINT,
    extract_network_metadata,
    fetch_page_text,
    search_duckduckgo,
    _resolve_duckduckgo_url,
    _strip_html,
)


SAMPLE_DDG_HTML = """
<html><body>
<a class="result__a" href="https://example.com/spec-a">Spec A Title</a>
<div class="result__snippet">A summary about GB/T 1234 standard</div>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fspec-b&amp;test=1">Spec B Title</a>
<a class="result__snippet">B summary mentioning ISO 9001</a>
</body></html>
"""


def _make_transport(handler):
    return httpx.MockTransport(handler)


def test_search_duckduckgo_parses_title_and_snippet() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(DUCKDUCKGO_ENDPOINT)
        return httpx.Response(200, text=SAMPLE_DDG_HTML)

    hits = search_duckduckgo("GB/T 1234", transport=_make_transport(handler))
    assert len(hits) == 2
    assert hits[0]["title"] == "Spec A Title"
    assert "GB/T 1234" in hits[0]["snippet"]
    assert hits[0]["url"] == "https://example.com/spec-a"
    # Second hit comes from a uddg redirect; should resolve to the encoded URL.
    assert hits[1]["url"] == "https://example.com/spec-b"


def test_search_duckduckgo_returns_empty_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated")

    assert search_duckduckgo("anything", transport=_make_transport(handler)) == []


def test_search_duckduckgo_returns_empty_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    assert search_duckduckgo("anything", transport=_make_transport(handler)) == []


def test_search_duckduckgo_returns_empty_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    assert search_duckduckgo("anything", transport=_make_transport(handler)) == []


def test_search_duckduckgo_handles_empty_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>no results</body></html>")

    assert search_duckduckgo("obscure", transport=_make_transport(handler)) == []


def test_resolve_duckduckgo_url_passthrough_for_non_ddg() -> None:
    assert _resolve_duckduckgo_url("https://example.com/page") == "https://example.com/page"


def test_resolve_duckduckgo_url_protocol_relative() -> None:
    url = _resolve_duckduckgo_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.example%2F")
    assert url == "https://a.example/"


def test_resolve_duckduckgo_url_missing_uddg() -> None:
    assert _resolve_duckduckgo_url("https://duckduckgo.com/l/?other=1") == ""


def test_fetch_page_text_returns_normalized_body() -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, text="<html><body>  <p>Hello  world</p>  </body></html>")

    text = fetch_page_text("https://example.com/page", transport=_make_transport(handler))
    assert text == "Hello world"
    assert captured_urls == ["https://example.com/page"]


def test_fetch_page_text_rejects_non_http_scheme() -> None:
    assert fetch_page_text("file:///etc/passwd") == ""
    assert fetch_page_text("not a url") == ""


def test_fetch_page_text_returns_empty_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    assert fetch_page_text("https://example.com/missing", transport=_make_transport(handler)) == ""


def test_fetch_page_text_returns_empty_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated")

    assert fetch_page_text("https://example.com/slow", transport=_make_transport(handler)) == ""


def test_fetch_page_text_truncates_long_content() -> None:
    long_text = "<html><body>" + ("a" * 10000) + "</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=long_text)

    text = fetch_page_text("https://example.com/huge", transport=_make_transport(handler))
    assert len(text) <= 5000


def test_extract_network_metadata_finds_standard_codes() -> None:
    text = "本标准为 GB/T 1234.5-2020 标准，参照 ISO 9001 要求。"
    metadata = extract_network_metadata(text)
    assert "GB/T 1234.5-2020" in metadata["standard_codes"]
    assert "ISO 9001" in metadata["standard_codes"]


def test_extract_network_metadata_finds_dates() -> None:
    text = "发布日期 2024-01-15，实施日期 2024-06-01。"
    metadata = extract_network_metadata(text)
    assert "2024-01-15" in metadata["dates"]
    assert "2024-06-01" in metadata["dates"]


def test_extract_network_metadata_finds_status_markers() -> None:
    text = "Status: Valid。 本标准为现行标准。"
    metadata = extract_network_metadata(text)
    status_blob = " ".join(metadata["status"])
    assert "Valid" in status_blob or "现行" in status_blob


def test_extract_network_metadata_finds_organizations() -> None:
    text = "全国汽车标准化技术委员会负责本标准的归口。"
    metadata = extract_network_metadata(text)
    assert any("委员会" in org for org in metadata["organizations"])


def test_extract_network_metadata_empty_input() -> None:
    metadata = extract_network_metadata("")
    assert all(values == [] for values in metadata.values())


def test_strip_html_removes_tags_and_collapses_whitespace() -> None:
    assert _strip_html("<p>Hello  <b>world</b></p>") == "Hello world"
    assert _strip_html("") == ""
    assert _strip_html(None or "  <span>x</span>  ") == "x"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://other.com/page", "https://other.com/page"),
        ("//duckduckgo.com/x?uddg=https%3A%2F%2Fa.example%2F", "https://a.example/"),
        ("https://duckduckgo.com/no-uddg", ""),
    ],
)
def test_resolve_duckduckgo_url_table(raw: str, expected: str) -> None:
    assert _resolve_duckduckgo_url(raw) == expected
