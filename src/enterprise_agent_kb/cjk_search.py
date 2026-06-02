"""CJK (Chinese/Japanese/Korean) search optimization utilities.

Provides improved tokenization and search strategies for CJK text in SQLite FTS5.
"""

from __future__ import annotations

import re
from typing import Iterable


# CJK character ranges
CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0x20000, 0x2A6DF), # CJK Unified Ideographs Extension B
    (0x2A700, 0x2B73F), # CJK Unified Ideographs Extension C
    (0x2B740, 0x2B81F), # CJK Unified Ideographs Extension D
    (0x2B820, 0x2CEAF), # CJK Unified Ideographs Extension E
    (0x2CEB0, 0x2EBEF), # CJK Unified Ideographs Extension F
    (0x3000, 0x303F),   # CJK Symbols and Punctuation
    (0xFF00, 0xFFEF),   # Halfwidth and Fullwidth Forms
]


def is_cjk_char(char: str) -> bool:
    """Check if a character is in the CJK unicode ranges."""
    code = ord(char)
    for start, end in CJK_RANGES:
        if start <= code <= end:
            return True
    return False


def extract_cjk_chars(text: str) -> list[str]:
    """Extract CJK characters from text."""
    return [ch for ch in text if is_cjk_char(ch)]


def tokenize_cjk(text: str, bigram_only: bool = False) -> list[str]:
    """Tokenize CJK text using n-gram strategy.

    Args:
        text: Input text
        bigram_only: If True, only generate 2-grams (bigrams)

    Returns:
        List of tokens including n-grams
    """
    cjk_chars = extract_cjk_chars(text)
    tokens: list[str] = []

    # Generate n-grams
    if bigram_only or len(cjk_chars) < 3:
        # Only bigrams for short text
        for i in range(len(cjk_chars) - 1):
            tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    else:
        # Bigrams and trigrams for longer text
        for i in range(len(cjk_chars) - 1):
            tokens.append(cjk_chars[i] + cjk_chars[i + 1])
        for i in range(len(cjk_chars) - 2):
            tokens.append(cjk_chars[i] + cjk_chars[i + 1] + cjk_chars[i + 2])

    # Also include individual CJK chars for single-character queries
    tokens.extend(cjk_chars)

    return tokens


def build_cjk_search_terms(query: str) -> list[str]:
    """Build search terms for CJK query.

    Args:
        query: Search query string

    Returns:
        List of search terms including original, normalized, and n-grams
    """
    query = query.strip()
    if not query:
        return []

    terms: list[str] = []

    # Add original query
    terms.append(query)

    # Normalize whitespace
    normalized = re.sub(r"\s+", " ", query).strip().lower()
    if normalized != query:
        terms.append(normalized)

    # Extract CJK n-grams
    cjk_tokens = tokenize_cjk(query)
    terms.extend(cjk_tokens)

    return list(dict.fromkeys(terms))  # Deduplicate while preserving order


def build_cjk_like_pattern(query: str) -> str:
    """Build SQL LIKE pattern for CJK search with fallback.

    Creates a pattern that matches:
    - The full query
    - 2-character fragments
    - Individual characters for very short queries

    Args:
        query: Search query

    Returns:
        SQL LIKE pattern with % wildcards
    """
    query = query.strip()
    if not query:
        return "%"

    # For queries with CJK characters, build fragment pattern
    cjk_chars = extract_cjk_chars(query)
    if len(cjk_chars) >= 2:
        # Use the full query
        return f"%{query}%"

    # For single CJK char or non-CJK, return direct pattern
    return f"%{query}%"


def build_fts5_match_expr(query: str, max_terms: int = 10) -> str:
    """Build FTS5 match expression for CJK queries.

    FTS5 with unicode61 tokenizer splits CJK into individual characters.
    This function builds an optimized match expression using:
    - Phrases for multi-character terms
    - OR combinations for flexibility
    - N-gram fallback for CJK

    Args:
        query: Search query
        max_terms: Maximum number of terms in expression

    Returns:
        FTS5 match expression
    """
    query = query.strip()
    if not query:
        return '""'

    terms = build_cjk_search_terms(query)
    terms = terms[:max_terms]

    if not terms:
        return f'"{query}"'

    # Build OR expression for flexibility
    quoted_terms = [f'"{term}"' for term in terms if term]
    return " OR ".join(quoted_terms)


def build_ngram_index_text(text: str) -> str:
    """Build indexed text with n-grams for CJK search.

    This should be used when populating FTS5 searchable_text columns
    to improve CJK search recall.

    Args:
        text: Original text

    Returns:
        Text with n-grams appended for indexing
    """
    text = text.strip()
    if not text:
        return ""

    # Normalize
    normalized = re.sub(r"\s+", " ", text).strip().lower()

    # Extract tokens
    tokens = re.findall(r"[a-z0-9./-]+|[一-鿿]{1,}", normalized)

    # Generate CJK n-grams
    cjk_chars = extract_cjk_chars(normalized)
    ngrams: list[str] = []

    if len(cjk_chars) >= 2:
        # Bigrams
        for i in range(len(cjk_chars) - 1):
            ngrams.append(cjk_chars[i] + cjk_chars[i + 1])
        # Trigrams for longer text
        if len(cjk_chars) >= 3:
            for i in range(len(cjk_chars) - 2):
                ngrams.append(cjk_chars[i] + cjk_chars[i + 1] + cjk_chars[i + 2])

    # Combine all parts
    all_parts = [normalized, *tokens, *ngrams]
    return " ".join(dict.fromkeys(all_parts))  # Deduplicate


def cjk_relevance_boost(query: str, text: str) -> float:
    """Calculate relevance boost score for CJK matching.

    Args:
        query: Search query
        text: Text to match against

    Returns:
        Boost score (0.0 to 1.0)
    """
    if not query or not text:
        return 0.0

    query_lower = text.lower()
    text_lower = text.lower()

    # Exact match
    if query_lower in text_lower:
        return 1.0

    # Check CJK character overlap
    query_cjk = set(extract_cjk_chars(query))
    text_cjk = set(extract_cjk_chars(text))

    if not query_cjk:
        return 0.0

    # Calculate overlap ratio
    overlap = len(query_cjk & text_cjk)
    ratio = overlap / len(query_cjk)

    # Boost based on overlap
    if ratio >= 0.8:
        return 0.9
    elif ratio >= 0.6:
        return 0.7
    elif ratio >= 0.4:
        return 0.5
    elif ratio >= 0.2:
        return 0.3
    return 0.1


def optimize_cjk_query(query: str) -> str:
    """Optimize CJK query for better search results.

    Args:
        query: Original query

    Returns:
        Optimized query string
    """
    query = query.strip()

    # Remove common particles that don't add meaning
    particles = {"的", "了", "和", "与", "或", "及", "等", "等", "吗", "呢", "啊"}
    words = query.split()
    filtered = [w for w in words if w not in particles]

    return " ".join(filtered) if filtered else query
