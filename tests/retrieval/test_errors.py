"""Unit tests for retrieval/errors.py: SearchBackendError (ticket #31)."""

from __future__ import annotations

from knowledge_vault.retrieval.errors import SearchBackendError


def test_search_backend_error_is_an_exception() -> None:
    assert issubclass(SearchBackendError, Exception)


def test_search_backend_error_carries_message() -> None:
    error = SearchBackendError("cannot open /tmp/knowledge.db")

    assert str(error) == "cannot open /tmp/knowledge.db"
