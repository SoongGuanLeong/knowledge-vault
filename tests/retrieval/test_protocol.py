"""Unit tests for retrieval/protocol.py: the SearchBackend Protocol (ticket #31)."""

from __future__ import annotations

import inspect
from typing import Protocol

from knowledge_vault.retrieval.protocol import SearchBackend


def test_search_backend_is_a_typing_protocol() -> None:
    assert issubclass(SearchBackend, Protocol)


def test_search_backend_exposes_only_search() -> None:
    members = [name for name in dir(SearchBackend) if not name.startswith("_")]
    assert members == ["search"]


def test_search_signature_contract() -> None:
    sig = inspect.signature(SearchBackend.search)

    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["self", "query", "k", "filters"]

    query, k, filters = params[1], params[2], params[3]
    assert query.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert k.kind == inspect.Parameter.KEYWORD_ONLY
    assert filters.kind == inspect.Parameter.KEYWORD_ONLY
    assert k.default == 10
    assert filters.default is None
    assert sig.return_annotation == "list[SearchResult]"


def test_search_is_sync() -> None:
    assert not inspect.iscoroutinefunction(SearchBackend.search)
