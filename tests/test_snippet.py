"""Unit tests for knowledge_vault/snippet.py (ticket #34).

Pure string-in/string-out helpers. No SQLite, retrieval, CLI, or filesystem
dependencies — these tests are the isolated seam for snippet generation.
"""

from __future__ import annotations

from knowledge_vault.snippet import extract_terms, make_snippet

# --- extract_terms ---


def test_extract_terms_keeps_plain_words() -> None:
    assert extract_terms("spark sql") == ["spark", "sql"]


def test_extract_terms_lowercases() -> None:
    assert extract_terms("Spark SQL") == ["spark", "sql"]


def test_extract_terms_drops_ft5_phrase_quotes() -> None:
    assert extract_terms('"spark sql"') == ["spark", "sql"]


def test_extract_terms_strips_prefix_star() -> None:
    assert extract_terms("stream*") == ["stream"]


def test_extract_terms_drops_ft5_operators() -> None:
    assert extract_terms("spark AND sql OR catalyst NOT legacy NEAR engine") == [
        "spark",
        "sql",
        "catalyst",
        "legacy",
        "engine",
    ]


def test_extract_terms_drops_stopwords() -> None:
    assert extract_terms("the spark engine for data") == ["spark", "engine", "data"]


def test_extract_terms_drops_parens_and_boost() -> None:
    assert extract_terms("(spark^5 sql)") == ["spark", "sql"]


def test_extract_terms_strips_boost_inside_parens() -> None:
    assert extract_terms("(stream^3)") == ["stream"]


def test_extract_terms_drops_near_distance_syntax() -> None:
    assert extract_terms("spark NEAR/2 sql") == ["spark", "sql"]


def test_extract_terms_drops_column_filter_prefix() -> None:
    assert extract_terms("title: spark") == ["spark"]


def test_extract_terms_deduplicates_keeping_order() -> None:
    assert extract_terms("spark spark sql spark") == ["spark", "sql"]


def test_extract_terms_empty_and_blank_queries() -> None:
    assert extract_terms("") == []
    assert extract_terms("   ") == []
    assert extract_terms("the and or") == []


# --- make_snippet ---


def test_make_snippet_collapses_whitespace() -> None:
    assert make_snippet("a\n\nb\t c\n", []) == "a b c"


def test_make_snippet_no_terms_returns_window_from_start() -> None:
    text = "abcdefghij"
    assert make_snippet(text, [], window_chars=4) == "abcd"


def test_make_snippet_no_match_falls_back_to_chunk_start() -> None:
    text = "abcdefghij"
    assert make_snippet(text, ["zzz"], window_chars=4) == "abcd"


def test_make_snippet_window_starts_at_first_term_match() -> None:
    text = "the quick brown fox jumps over the lazy dog"
    result = make_snippet(text, ["fox"], window_chars=20)
    assert result == "fox jumps over the l"
    assert len(result) == 20


def test_make_snippet_uses_earliest_matching_term() -> None:
    text = "the quick brown fox jumps over the lazy dog"
    result = make_snippet(text, ["dog", "quick"], window_chars=6)
    assert result == "quick "


def test_make_snippet_window_does_not_exceed_text() -> None:
    text = "short"
    assert make_snippet(text, ["short"], window_chars=100) == "short"


def test_make_snippet_no_highlight_by_default() -> None:
    text = "the quick brown fox"
    result = make_snippet(text, ["fox"], window_chars=20)
    assert "\x1b[" not in result


def test_make_snippet_highlight_wraps_occurrences() -> None:
    text = "fox and fox again"
    result = make_snippet(text, ["fox"], window_chars=20, highlight=True)
    assert result.count("\x1b[1mfox\x1b[0m") == 2


def test_make_snippet_highlight_is_case_insensitive() -> None:
    text = "Fox and fox"
    result = make_snippet(text, ["fox"], window_chars=20, highlight=True)
    assert result.count("\x1b[1m") == 2
    plain = make_snippet(text, ["fox"], window_chars=20)
    assert plain == "Fox and fox"


def test_make_snippet_highlight_skips_empty_terms() -> None:
    text = "fox and fox"
    result = make_snippet(text, ["fox", ""], window_chars=20, highlight=True)
    assert result.count("\x1b[1mfox\x1b[0m") == 2


def test_make_snippet_empty_text() -> None:
    assert make_snippet("", ["spark"]) == ""
    assert make_snippet("", ["spark"], highlight=True) == ""


def test_make_snippet_default_window_is_positive() -> None:
    text = "spark " * 100
    assert 0 < len(make_snippet(text, ["spark"])) < len(text)


# --- constants contract ---


def test_snippet_module_has_window_constant() -> None:
    from knowledge_vault.snippet import SNIPPET_WINDOW_CHARS

    assert isinstance(SNIPPET_WINDOW_CHARS, int)
    assert SNIPPET_WINDOW_CHARS > 0
