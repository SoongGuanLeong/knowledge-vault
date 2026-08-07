"""Snippet generation for the kv search CLI (ticket #34).

Pure helpers: strings in, strings out. No SQLite, retrieval, CLI, or
filesystem dependencies — the CLI owns the query-to-search wiring and calls
these to turn a query plus chunk text into a human-readable snippet.
"""

from __future__ import annotations

import re

SNIPPET_WINDOW_CHARS = 200

_ANSI_BOLD = "\x1b[1m"
_ANSI_RESET = "\x1b[0m"

_FTS_OPERATORS = frozenset({"and", "or", "not", "near"})

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "if",
        "in",
        "into",
        "is",
        "it",
        "no",
        "not",
        "of",
        "on",
        "or",
        "such",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "will",
        "with",
    }
)


def extract_terms(query: str) -> list[str]:
    """Extract search terms from an FTS5 query string.

    Whitespace-tokenizes *query*, strips FTS5 syntax (quotes, parens,
    wildcards, ``^N`` boost suffixes), drops FTS5 operators (``AND``/``OR``/
    ``NOT``/``NEAR``) and English stopwords, lowercases, and deduplicates
    while preserving first-occurrence order.

    Parameters
    ----------
    query : str
        The raw query as typed by the user.

    Returns
    -------
    list[str]
        Cleaned terms used for snippet highlighting, ``[]`` when the query
        carries no meaningful terms.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for token in query.split():
        cleaned = _clean_token(token)
        if _is_syntax_noise(cleaned):
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            terms.append(cleaned)
    return terms


def make_snippet(
    text: str,
    terms: list[str],
    *,
    window_chars: int = SNIPPET_WINDOW_CHARS,
    highlight: bool = False,
) -> str:
    """Build a fixed-width snippet from *text* around the first term match.

    Collapses whitespace, then opens the window at the earliest occurrence of
    any *terms* term (falling back to the chunk start when none match).
    When *highlight* is true, wraps every in-window occurrence of a term in
    ANSI bold — the caller decides (e.g. only when stdout is a TTY).

    Parameters
    ----------
    text : str
        Chunk text to derive the snippet from.
    terms : list[str]
        Cleaned query terms (see :func:`extract_terms`).
    window_chars : int
        Maximum snippet length.
    highlight : bool
        Wrap term occurrences in ANSI bold when true.

    Returns
    -------
    str
        A snippet of at most *window_chars* characters.
    """
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return ""

    start = _first_term_position(collapsed, terms)
    window = collapsed[start : start + window_chars]

    if highlight:
        for term in terms:
            if not term:
                continue
            window = re.sub(
                re.escape(term),
                lambda match: f"{_ANSI_BOLD}{match.group(0)}{_ANSI_RESET}",
                window,
                flags=re.IGNORECASE,
            )
    return window


def _first_term_position(text: str, terms: list[str]) -> int:
    """Index of the earliest term occurrence in *text*, or 0 when none match."""
    positions = [text.lower().find(term.lower()) for term in terms if term]
    hits = [position for position in positions if position >= 0]
    return min(hits) if hits else 0


def _is_syntax_noise(cleaned: str) -> bool:
    """True when a cleaned token carries no usable search meaning."""
    return (
        not cleaned
        or cleaned in _FTS_OPERATORS
        or cleaned in _STOPWORDS
        or re.match(r"^near/\d+$", cleaned) is not None
        or cleaned.endswith(":")
    )


def _clean_token(token: str) -> str:
    """Lowercase *token* and strip FTS5 syntax, leaving a bare word.

    Order matters: parens and quotes must go first so ``^N`` boost suffixes
    on tokens inside parens (e.g. ``stream^3)``) are still removable.
    """
    cleaned = token.lower()
    cleaned = cleaned.strip('"(),')
    cleaned = re.sub(r"\^\d+$", "", cleaned)
    cleaned = cleaned.strip("*")
    return cleaned
