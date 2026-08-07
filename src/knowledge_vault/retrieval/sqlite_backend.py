"""SQLite FTS5 search backend: BM25 keyword search over ``fts_chunks`` (ticket #30).

Implements the engine-agnostic :class:`SearchBackend` protocol on top of the
``knowledge.db`` schema (ticket #24). All SQL — the FTS5 ``MATCH``, the joins
to ``chunks``/``documents`` for metadata, ``bm25()`` ranking, and the optional
source/version filters — lives here and is never exposed to callers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from knowledge_vault.retrieval.errors import IndexedSlicesError, SearchBackendError
from knowledge_vault.retrieval.models import IndexedSlices, SearchFilters, SearchResult
from knowledge_vault.retrieval.schema import SchemaError, check_schema, connect_db

_SEARCH_SQL = """
SELECT
    chunks.chunk_uuid,
    chunks.text,
    documents.source,
    documents.version,
    documents.path,
    chunks.start_line,
    chunks.end_line,
    bm25(fts_chunks) AS raw_score
FROM fts_chunks
JOIN chunks ON chunks.chunk_id = fts_chunks.rowid
JOIN documents ON documents.document_id = chunks.document_id
WHERE fts_chunks MATCH ?
"""


class SQLiteFTSBackend:
    """FTS5-backed :class:`SearchBackend` over a local ``knowledge.db``.

    Lifetime: construct with the database path, then either call
    :meth:`open`/:meth:`close` explicitly or use ``with SQLiteFTSBackend(path)
    as backend``. ``open()`` gates on the database's ``schema_version``,
    refusing incompatible databases (rebuild-not-migrate). ``search()`` is the
    only public retrieval surface; the connection and cursor stay private.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        """Open *db_path* and verify its schema is supported.

        Raises
        ------
        SearchBackendError
            If the database is missing/corrupt or holds an incompatible
            ``schema_version``. The original error is chained via ``from``.
        """
        try:
            conn = connect_db(self._db_path)
            check_schema(conn)
        except (SchemaError, sqlite3.DatabaseError) as exc:
            raise SearchBackendError(f"cannot open {self._db_path}") from exc
        self._conn = conn

    def close(self) -> None:
        """Close the underlying connection, if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> SQLiteFTSBackend:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def search(
        self,
        query: str,
        *,
        k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[SearchResult]:
        """Keyword search over chunk text.

        Runs ``query`` as an FTS5 ``MATCH`` expression, ranks with ``bm25()``
        ascending (negated to ``score`` so higher = more relevant), breaks ties
        deterministically by ``chunk_id``, and limits to ``k`` hits.

        Parameters
        ----------
        query : str
            FTS5 MATCH expression (e.g. ``"spark"``, ``"spark AND sql"``).
        k : int
            Maximum number of results. Must be >= 1.
        filters : SearchFilters | None
            Optional source/version constraints; unknown values yield ``[]``.

        Returns
        -------
        list[SearchResult]
            Hits best-first, or ``[]`` when nothing matches.

        Raises
        ------
        ValueError
            If ``query`` is blank/whitespace or ``k < 1``. Caller bugs, never
            wrapped.
        SearchBackendError
            If the backend is not open.
        """
        if not query.strip():
            raise ValueError("query must be a non-blank string")
        if k < 1:
            raise ValueError("k must be >= 1")
        if self._conn is None:
            raise SearchBackendError("search backend is not open; call open() first")

        sql = _SEARCH_SQL
        params: list[object] = [query]
        if filters is not None:
            if filters.source is not None:
                sql += " AND documents.source = ?"
                params.append(filters.source)
            if filters.version is not None:
                sql += " AND documents.version = ?"
                params.append(filters.version)
        sql += " ORDER BY bm25(fts_chunks) ASC, chunks.chunk_id ASC LIMIT ?"
        params.append(k)

        rows = self._conn.execute(sql, params).fetchall()

        return [
            SearchResult(
                chunk_uuid=row[0],
                text=row[1],
                source=row[2],
                version=row[3],
                path=row[4],
                start_line=row[5],
                end_line=row[6],
                score=-row[7],
            )
            for row in rows
        ]

    _INDEXED_SLICES_SQL = """
        SELECT source, version, chunks_sha256, document_count, chunk_count
        FROM indexed_sources
        ORDER BY source, version
        """

    def indexed_slices(self) -> IndexedSlices:
        """Return every (source, version) slice registered in the gold index.

        Runs without exposing a connection, cursor, or schema checks to the
        caller. An empty registry yields an empty :class:`IndexedSlices`.

        Returns
        -------
        IndexedSlices
            Typed answer over ``indexed_sources``; distinct sources and
            versions are derivable from the result without re-querying.

        Raises
        ------
        IndexedSlicesError
            If the database is missing, corrupt, or schema-incompatible. The
            original cause is chained via ``from``.
        """
        if self._conn is None:
            raise IndexedSlicesError("search backend is not open; call open() first")
        try:
            rows = self._conn.execute(self._INDEXED_SLICES_SQL).fetchall()
        except sqlite3.DatabaseError as exc:
            raise IndexedSlicesError(f"cannot read indexed slices from {self._db_path}") from exc
        return IndexedSlices.from_rows([tuple(row) for row in rows])
