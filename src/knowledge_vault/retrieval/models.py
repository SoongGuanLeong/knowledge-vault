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


@dataclass(frozen=True)
class IndexedSlice:
    """A single (source, version) slice in the gold ``indexed_sources`` registry.

    ``IndexedSlices`` is the typed answer returned for "what's indexed?" —
    callers derive distinct sources and distinct versions without re-querying
    the database. Provenance (per-slice chunk/sha and counts) is read-only.
    """

    source: str
    version: str
    chunks_sha256: str
    document_count: int
    chunk_count: int


@dataclass(frozen=True)
class IndexedSlices:
    """The full set of indexed (source, version) slices.

    ``slices`` preserves registry insertion order; ``sources`` and
    ``versions`` expose the distinct values derivable from ``slices`` so a
    caller can answer "what's indexed?" once and reuse the answer.
    """

    slices: tuple[IndexedSlice, ...]
    sources: tuple[str, ...]
    versions: tuple[str, ...]

    @staticmethod
    def from_rows(rows: list[tuple[str, str, str, int, int]]) -> IndexedSlices:
        """Build an ``IndexedSlices`` from raw ``indexed_sources`` rows.

        Rows are expected as ``(source, version, chunks_sha256, document_count,
        chunk_count)`` tuples in registry order. Distinct sources and versions
        are derived preserving first-appearance order.
        """
        slices = tuple(
            IndexedSlice(
                source=src,
                version=ver,
                chunks_sha256=sha,
                document_count=doc_count,
                chunk_count=chunk_count,
            )
            for src, ver, sha, doc_count, chunk_count in rows
        )
        seen_sources: set[str] = set()
        seen_versions: set[str] = set()
        sources: list[str] = []
        versions: list[str] = []
        for s in slices:
            if s.source not in seen_sources:
                seen_sources.add(s.source)
                sources.append(s.source)
            if s.version not in seen_versions:
                seen_versions.add(s.version)
                versions.append(s.version)
        return IndexedSlices(
            slices=slices,
            sources=tuple(sources),
            versions=tuple(versions),
        )
