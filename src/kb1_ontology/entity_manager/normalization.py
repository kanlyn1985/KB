"""Name normalization for entity canonical names.

The goal is that two strings representing the same conceptual thing
collapse to the same normalized form. For example:

    "ISO 14229-1—2013"      ─┐
    "ISO 14229-1:2013"       ├──►  "iso 14229-1"
    "ISO 14229-1"            ─┘
    "  iso   14229-1  "       ────►  "iso 14229-1"

The functions here are deliberately conservative: we do not
attempt fuzzy matching, transliteration, or translation. We
canonicalize only what we can do deterministically:
  - whitespace
  - case (to lowercase for matching only; canonical_name is preserved)
  - year suffix (4-digit year at the end)
  - punctuation separators (— : - → -)
"""
from __future__ import annotations

import re
import unicodedata

# Pattern: 4-digit year at the end of a string, possibly preceded
# by a separator ("—2013", ":2013", "-2013", " 2013").
# We restrict years to a reasonable range (1950-2099) to avoid
# false positives on standard numbers like "ISO 15118" (where
# 1511 is followed by 8 — mistaken as 1511+8=1519... actually
# the regex hits "1511" + "8" and strips both).
_TRAILING_YEAR = re.compile(
    r"(?:\s*[—:\-–]\s*|\s+)(?:19[5-9]\d|20\d{2})$"
)

# Trailing language/edition marker like "(E)" or "(英文版)" — drop.
_TRAILING_LANG_MARKER = re.compile(
    r"\s*\([^)]{1,8}\)\s*$"
)

# Unicode punctuation characters that act like dashes/colons.
_DASH_CHARS = ("–", "—", "―")  # en-dash, em-dash, horizontal bar


def normalize_canonical_name(name: str) -> str:
    """Return a canonical form of ``name`` for storage and equality.

    Rules (in order):
      1. Strip leading/trailing whitespace.
      2. Unicode normalize (NFKC) so that "ISO" fullwidth becomes
         "ISO" halfwidth, etc.
      3. Collapse internal whitespace runs to a single space.
      4. Drop a trailing "(E)" / "(英文版)" language marker.
      5. Replace unicode dash variants with ASCII "-".
      6. Drop a trailing 4-digit year in range 1950-2099.
      7. Strip a trailing ":" or "-".

    The result is what we put in the ``canonical_name`` column.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).strip()
    s = re.sub(r"\s+", " ", s)
    s = _TRAILING_LANG_MARKER.sub("", s)
    for ch in _DASH_CHARS:
        s = s.replace(ch, "-")
    s = _TRAILING_YEAR.sub("", s)
    s = s.rstrip(" :-")
    return s


def normalize_for_match(name: str) -> str:
    """Like ``normalize_canonical_name`` but lowercases for
    case-insensitive matching."""
    return normalize_canonical_name(name).lower()


# Self-test when run directly.
if __name__ == "__main__":
    cases = [
        ("ISO 14229-1—2013", "ISO 14229-1"),
        ("ISO 14229-1:2013", "ISO 14229-1"),
        ("ISO 14229-1", "ISO 14229-1"),
        ("  iso   14229-1  ", "iso 14229-1"),
        ("GB/T 18487.1—2023", "GB/T 18487.1"),
        ("GB/T 18487.1-2015", "GB/T 18487.1"),
        ("QC/T 1036—2016", "QC/T 1036"),
        ("ISO 14229-7:2015(E)", "ISO 14229-7"),
    ]
    for raw, expected in cases:
        got = normalize_canonical_name(raw)
        status = "OK" if got == expected else "FAIL"
        print(f"{status}: normalize_canonical_name({raw!r}) -> {got!r} "
              f"(expected {expected!r})")
