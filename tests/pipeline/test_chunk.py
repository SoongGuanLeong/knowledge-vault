"""Unit tests for pipeline/chunk.py: recursive splitting, overlap, line index."""

from __future__ import annotations

import string

from knowledge_vault.pipeline import chunk


def _make_doc(paragraphs: int, para_chars: int) -> str:
    """Build a deterministic doc of *paragraphs* paragraphs, each *para_chars* chars."""
    words = string.ascii_lowercase
    body = "".join(words[i % len(words)] for i in range(para_chars))
    return "\n\n".join(body for _ in range(paragraphs))


def test_recursive_split_caps_chunks_at_chunk_size() -> None:
    text = _make_doc(paragraphs=5, para_chars=600)
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    assert chunks, "expected non-empty chunk list"
    assert max(len(c) for c in chunks) <= chunk.DEFAULT_CHUNK_SIZE


def test_recursive_split_preserves_content_on_join() -> None:
    text = _make_doc(paragraphs=5, para_chars=600)
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    assert "".join(chunks) == text


def test_recursive_split_short_text_is_single_chunk() -> None:
    assert chunk.recursive_split("short text", chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE) == ["short text"]


def test_recursive_split_empty_text_returns_empty() -> None:
    assert chunk.recursive_split("", chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE) == []


def test_recursive_split_uses_paragraph_breaks() -> None:
    text = "p1\n\np2\n\np3"
    # chunk_size smaller than text to force splitting on "\n\n"
    chunks = chunk.recursive_split(text, ["\n\n", "\n", " ", ""], 5)
    assert "".join(chunks) == text
    assert len(chunks) > 1
    # every chunk except the last ends on a paragraph break (separator retained)
    for c in chunks[:-1]:
        assert c.endswith("\n\n")


def test_recursive_split_is_deterministic() -> None:
    text = _make_doc(paragraphs=7, para_chars=700)
    args = (chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    assert chunk.recursive_split(text, *args) == chunk.recursive_split(text, *args)


def test_apply_overlap_prepends_suffix_of_previous_chunk() -> None:
    chunks = ["AAAA1234", "BBBB5678", "CCCC9012"]
    overlapped = chunk.apply_overlap(chunks, 4)
    assert overlapped[0] == "AAAA1234"
    assert overlapped[1] == "1234BBBB5678"
    assert overlapped[2] == "5678CCCC9012"


def test_apply_overlap_zero_or_single_chunk() -> None:
    assert chunk.apply_overlap(["only"], 150) == ["only"]
    assert chunk.apply_overlap(["a", "b"], 0) == ["a", "b"]
    assert chunk.apply_overlap([], 150) == []


def test_apply_overlap_stays_within_boundaries() -> None:
    short_prev = "ab"
    chunks = [short_prev, "CCCCCCCCCCCC"]
    overlapped = chunk.apply_overlap(chunks, 150)
    assert overlapped[1] == short_prev + "CCCCCCCCCCCC"


def test_apply_overlap_only_between_adjacent_chunks_in_same_document() -> None:
    doc_a = ["AAAA1111", "BBBB2222"]
    doc_b = ["CCCC3333", "DDDD4444"]
    over_a = chunk.apply_overlap(doc_a, 4)
    over_b = chunk.apply_overlap(doc_b, 4)
    assert over_a[0] == "AAAA1111"
    assert over_a[1] == "1111BBBB2222"
    assert over_b[0] == "CCCC3333"
    assert over_b[1] == "3333DDDD4444"
    # No bleed: doc_b first chunk never receives doc_a suffix.
    assert not over_b[0].startswith("1111")


def test_apply_overlap_is_deterministic() -> None:
    chunks = [f"chunk{i}" * 200 for i in range(4)]
    assert chunk.apply_overlap(chunks, 150) == chunk.apply_overlap(chunks, 150)


def test_apply_overlap_default_with_real_split() -> None:
    text = _make_doc(paragraphs=6, para_chars=400)
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, chunk.DEFAULT_CHUNK_SIZE)
    overlapped = chunk.apply_overlap(chunks, chunk.DEFAULT_CHUNK_OVERLAP)
    assert len(overlapped) == len(chunks)
    assert overlapped[0] == chunks[0]
    for i in range(1, len(chunks)):
        expected_prefix = chunks[i - 1][-chunk.DEFAULT_CHUNK_OVERLAP :]
        assert overlapped[i].startswith(expected_prefix)


def test_recursive_split_forces_character_level_with_small_chunk_size() -> None:
    text = "abcdefgh"
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, 3)
    assert chunks == ["abc", "def", "gh"]
    assert "".join(chunks) == text
    assert max(len(c) for c in chunks) <= 3


def test_recursive_split_separator_not_found_falls_through() -> None:
    text = "a b c d e f g h"  # spaces only; no newlines
    chunks = chunk.recursive_split(text, chunk.DEFAULT_SEPARATORS, 4)
    assert "".join(chunks) == text
    assert max(len(c) for c in chunks) <= 4


def test_line_start_index_offsets() -> None:
    text = "ab\ncd\nef"
    assert chunk.line_start_index(text) == [0, 3, 6]


def test_line_start_index_single_line() -> None:
    assert chunk.line_start_index("no newlines") == [0]


def test_line_start_index_empty() -> None:
    assert chunk.line_start_index("") == [0]


def test_line_start_index_trailing_newline() -> None:
    assert chunk.line_start_index("a\n") == [0, 2]


def test_line_start_index_is_one_indexed() -> None:
    text = "l1\nl2\nl3"
    starts = chunk.line_start_index(text)
    assert starts[0] == 0  # line 1
    assert text[starts[0] :] == "l1\nl2\nl3"
    assert text[starts[1] :] == "l2\nl3"
    assert text[starts[2] :] == "l3"
