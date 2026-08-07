"""Retrieval result and filter models (ticket #25)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    """A single retrieval hit.

    ``chunk_uuid`` is the external chunk identity (schema ``chunk_uuid``, not
    the SQLite rowid alias). ``score`` is higher = more relevant; backends
    normalize the storage convention (FTS5's ``bm25`` is negated). Deliberately
    has no ``rank`` (list position is the rank) and no ``snippet`` (the CLI
    derives it from ``text`` + query terms, ticket #27).
    """

    chunk_uuid: str
    text: str
    source: str
    version: str
    path: str
    start_line: int
    end_line: int
    score: float


@dataclass(frozen=True)
class SearchFilters:
    """Optional retrieval constraints.

    ``None`` fields are unbounded: both ``None`` searches all slices,
    ``source`` only searches every version of that source, and both set is an
    exact (source, version) match. Unknown filter values yield an empty result,
    not an error — validation of typos is the caller's (CLI) job.
    """

    source: str | None = None
    version: str | None = None
