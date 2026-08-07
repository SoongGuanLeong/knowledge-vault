"""Unit tests for retrieval/models.py: SearchResult and SearchFilters (ticket #31).

Pure contract tests at the engine-agnostic seam — no backend, no SQLite, no
FTS5. Locks the frozen field shapes frozen in ticket #25's resolution.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from knowledge_vault.retrieval.models import SearchFilters, SearchResult

CONTRACT_FIELD_ORDER = ["chunk_uuid", "text", "source", "version", "path", "start_line", "end_line", "score"]


def _result() -> SearchResult:
    return SearchResult(
        chunk_uuid="uuid-abc",
        text="spark sql catalyst",
        source="spark",
        version="4.0.0",
        path="sql.md",
        start_line=3,
        end_line=5,
        score=1.5,
    )


def test_search_result_has_exact_contract_fields_in_order() -> None:
    result = _result()

    assert list(result.__dataclass_fields__) == CONTRACT_FIELD_ORDER
    assert result.chunk_uuid == "uuid-abc"
    assert result.text == "spark sql catalyst"
    assert result.source == "spark"
    assert result.version == "4.0.0"
    assert result.path == "sql.md"
    assert result.start_line == 3
    assert result.end_line == 5
    assert result.score == 1.5


def test_search_result_does_not_leak_storage_identifiers() -> None:
    result = _result()

    assert not hasattr(result, "document_id")
    assert not hasattr(result, "rank")
    assert not hasattr(result, "snippet")


def test_search_result_is_frozen() -> None:
    result = _result()

    with pytest.raises(FrozenInstanceError):
        # Intentionally assign to a frozen field; suppress the dataclass type error.
        result.score = 0.0  # type: ignore[misc]


def test_search_result_hash_matches_independently_constructed_equal_instance() -> None:
    assert hash(_result()) == hash(
        SearchResult(
            chunk_uuid="uuid-abc",
            text="spark sql catalyst",
            source="spark",
            version="4.0.0",
            path="sql.md",
            start_line=3,
            end_line=5,
            score=1.5,
        )
    )


def test_search_result_equality_compares_by_value() -> None:
    different = _result()
    different_uuid = SearchResult(
        chunk_uuid="uuid-xyz",
        text="spark sql catalyst",
        source="spark",
        version="4.0.0",
        path="sql.md",
        start_line=3,
        end_line=5,
        score=1.5,
    )

    assert _result() == _result()
    assert _result() != different_uuid
    assert different == _result()


def test_search_filters_default_to_none() -> None:
    filters = SearchFilters()

    assert filters.source is None
    assert filters.version is None


def test_search_filters_source_only() -> None:
    filters = SearchFilters(source="spark")

    assert filters.source == "spark"
    assert filters.version is None


def test_search_filters_version_only() -> None:
    filters = SearchFilters(version="4.0.0")

    assert filters.source is None
    assert filters.version == "4.0.0"


def test_search_filters_source_and_version() -> None:
    filters = SearchFilters(source="spark", version="4.0.0")

    assert filters.source == "spark"
    assert filters.version == "4.0.0"


def test_search_filters_is_frozen() -> None:
    filters = SearchFilters(source="spark")

    with pytest.raises(FrozenInstanceError):
        # Intentionally assign to a frozen field; suppress the dataclass type error.
        filters.source = "flink"  # type: ignore[misc]
