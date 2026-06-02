"""Unit tests for pure closed-loop-store helpers.

These functions have no DB or I/O dependencies; they are tested in isolation.
"""
from __future__ import annotations

import json

import pytest

from enterprise_agent_kb.closed_loop_store._helpers import (
    _as_int,
    _clip,
    _json_list,
    _json_object,
    _mean_metric,
    _normalize_text,
    _optional_text,
    _pytest_output_counts,
    _ratio,
    _safe_float,
    _safe_json,
    _string_ids,
    _text_values,
    re_sub_whitespace,
)


# ---------- _ratio ----------


def test_ratio_normal() -> None:
    assert _ratio(3, 4) == 0.75


def test_ratio_zero_denominator_returns_zero() -> None:
    assert _ratio(5, 0) == 0.0


def test_ratio_negative_denominator_returns_zero() -> None:
    assert _ratio(5, -1) == 0.0


def test_ratio_rounds_to_six_decimals() -> None:
    assert _ratio(1, 3) == 0.333333


# ---------- _mean_metric ----------


def test_mean_metric_uses_key() -> None:
    items = [{"score": 1.0}, {"score": 3.0}, {"score": 5.0}]
    assert _mean_metric(items, "score") == 3.0


def test_mean_metric_skips_non_numeric() -> None:
    items = [{"score": 1.0}, {"score": "bad"}, {"score": 3.0}, {}]
    assert _mean_metric(items, "score") == 2.0


def test_mean_metric_empty_returns_zero() -> None:
    assert _mean_metric([], "score") == 0.0


def test_mean_metric_all_invalid_returns_zero() -> None:
    assert _mean_metric([{"score": "bad"}, {"score": None}], "score") == 0.0


# ---------- re_sub_whitespace / _normalize_text ----------


@pytest.mark.parametrize("input_val,expected", [
    ("", ""),
    ("   ", ""),
    ("hello   world", "hello world"),
    ("a\n\nb\tc", "a b c"),
    (None, ""),
])
def test_re_sub_whitespace(input_val, expected: str) -> None:
    assert re_sub_whitespace(input_val) == expected


def test_normalize_text_matches_re_sub_whitespace() -> None:
    assert _normalize_text("  a  b  ") == "a b"
    assert _normalize_text("") == ""


# ---------- _pytest_output_counts ----------


def test_pytest_output_counts_parses_standard_summary() -> None:
    output = "===== 5 passed, 2 failed, 1 skipped, 3 deselected in 1.20s ====="
    counts = _pytest_output_counts(output)
    assert counts["passed"] == 5
    assert counts["failed"] == 2
    assert counts["skipped"] == 1
    assert counts["deselected"] == 3
    assert counts["selected"] == 5 + 2 + 1  # 8
    assert counts["collected"] == 5 + 2 + 1 + 3  # 11


def test_pytest_output_counts_handles_empty() -> None:
    counts = _pytest_output_counts("")
    assert all(v == 0 for v in counts.values())


def test_pytest_output_counts_uses_last_match_per_key() -> None:
    output = "3 passed\nlater: 7 passed in 2s"
    counts = _pytest_output_counts(output)
    assert counts["passed"] == 7


def test_pytest_output_counts_handles_xfailed_xpassed() -> None:
    output = "1 xfailed, 2 xpassed"
    counts = _pytest_output_counts(output)
    assert counts["xfailed"] == 1
    assert counts["xpassed"] == 2


# ---------- _safe_json ----------


def test_safe_json_parses_valid_string() -> None:
    assert _safe_json('{"a": 1}', {}) == {"a": 1}


def test_safe_json_returns_fallback_on_non_string() -> None:
    assert _safe_json(None, "fallback") == "fallback"
    assert _safe_json(42, []) == []
    assert _safe_json("", []) == []


def test_safe_json_returns_fallback_on_invalid_json() -> None:
    assert _safe_json("not json", "fallback") == "fallback"


# ---------- _json_list ----------


def test_json_list_from_list_drops_blanks() -> None:
    result = _json_list(["a", "", None, "b"])
    assert json.loads(result) == ["a", "b"]


def test_json_list_from_none_is_empty() -> None:
    assert json.loads(_json_list(None)) == []


def test_json_list_from_scalar_wraps_in_list() -> None:
    assert json.loads(_json_list("solo")) == ["solo"]


def test_json_list_from_tuple() -> None:
    assert json.loads(_json_list(("a", "b"))) == ["a", "b"]


# ---------- _optional_text ----------


def test_optional_text_returns_text_when_present() -> None:
    assert _optional_text("  hello  ") == "hello"


def test_optional_text_returns_none_for_blank() -> None:
    assert _optional_text("") is None
    assert _optional_text("   ") is None
    assert _optional_text(None) is None
    assert _optional_text(0) is None


# ---------- _as_int ----------


def test_as_int_converts_valid() -> None:
    assert _as_int("42") == 42
    assert _as_int(3.7) == 3


def test_as_int_returns_none_for_invalid() -> None:
    assert _as_int(None) is None
    assert _as_int("not a number") is None
    assert _as_int([]) is None


# ---------- _safe_float ----------


def test_safe_float_converts_valid() -> None:
    assert _safe_float("3.14") == 3.14
    assert _safe_float(0) == 0.0


def test_safe_float_returns_zero_for_invalid() -> None:
    assert _safe_float(None) == 0.0
    assert _safe_float("not a number") == 0.0
    assert _safe_float([]) == 0.0


# ---------- _clip ----------


def test_clip_short_text_unchanged() -> None:
    assert _clip("hello", 10) == "hello"


def test_clip_long_text_keeps_tail() -> None:
    assert _clip("hello world", 5) == "world"


def test_clip_empty_text() -> None:
    assert _clip("", 5) == ""
    assert _clip(None, 5) == ""


def test_clip_exact_length() -> None:
    assert _clip("hello", 5) == "hello"


# ---------- _json_object ----------


def test_json_object_from_dict_returns_empty_due_to_str_coercion() -> None:
    # The implementation coerces via str(value) before json.loads, so a Python
    # dict input round-trips through str() and json.loads fails; this test
    # documents that behavior so any future change is intentional.
    assert _json_object({"a": 1}) == {}


def test_json_object_from_json_string() -> None:
    assert _json_object('{"a": 1}') == {"a": 1}


def test_json_object_returns_empty_for_invalid() -> None:
    assert _json_object(None) == {}
    assert _json_object("") == {}
    assert _json_object("not json") == {}
    assert _json_object("[]") == {}  # not a dict


# ---------- _string_ids ----------


def test_string_ids_from_list_dedupes() -> None:
    result = _string_ids(["a", "b", "a", " c "])
    assert result == ["a", "b", "c"]


def test_string_ids_from_string() -> None:
    assert _string_ids("hello") == ["hello"]


def test_string_ids_from_set() -> None:
    result = _string_ids({"a", "b"})
    assert set(result) == {"a", "b"}


def test_string_ids_from_none_or_unsupported() -> None:
    assert _string_ids(None) == []
    assert _string_ids(42) == []


# ---------- _text_values ----------


def test_text_values_from_list() -> None:
    assert _text_values(["a", "  b  ", ""]) == ["a", "b"]


def test_text_values_from_string() -> None:
    assert _text_values("hello") == ["hello"]
    assert _text_values("   ") == []


def test_text_values_from_tuple() -> None:
    assert _text_values(("a", "b")) == ["a", "b"]


def test_text_values_from_unsupported() -> None:
    assert _text_values(None) == []
    assert _text_values(42) == []
