"""SQLite IndexStage: first index of ``chunks.jsonl`` into a fresh ``knowledge.db`` (ticket #41).

Writes the store-level ``gold/knowledge.db`` for one (source, version) slice,
consuming the row model from :mod:`knowledge_vault.retrieval.rows`. Fresh store
only: bootstraps the schema, rejects an incompatible schema (rebuild-not-migrate),
then inserts documents and chunks in chunks.jsonl order with stable ids, rebuilds
FTS, and records the ``indexed_sources`` registry row. All inserts happen in one
atomic transaction. Skip-on-unchanged (ticket #37) and replace-on-change
(ticket #38) are later additions.
"""

from __future__ import annotations

import hashlib
import sqlite3
import warnings

from knowledge_vault.pipeline.context import PipelineContext
from knowledge_vault.retrieval.rows import DocumentRow, parse_chunks
from knowledge_vault.retrieval.schema import (
    check_schema,
    connect_db,
    create_schema,
    knowledge_db_path,
)


class IndexStage:
    """Write the initial ``knowledge.db`` slice for a fresh store.

    Deterministic: identical chunks.jsonl input yields identical relational
    contents and search results across fresh stores (not byte-identical DBs).
    """

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Run indexing for *ctx*'s chunks artifact into the store-level database.

        Parameters
        ----------
        ctx : PipelineContext
            Immutable pipeline context carrying chunks_path, store.

        Returns
        -------
        PipelineContext
            The same context (indexing does not modify context).

        Raises
        ------
        FileNotFoundError
            If ``chunks.jsonl`` is missing.
        json.JSONDecodeError
            If any chunks.jsonl line is malformed.
        SchemaError
            If the database holds an incompatible schema version.
        """
        chunks_jsonl = ctx.chunks_path
        db_path = knowledge_db_path(ctx.store)

        if not chunks_jsonl.is_file():
            raise FileNotFoundError("Run ChunkStage before IndexStage.")

        content = chunks_jsonl.read_bytes()
        documents = parse_chunks(content.decode("utf-8"))
        chunks_sha256 = hashlib.sha256(content).hexdigest()

        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect_db(db_path)
        try:
            self._bootstrap(conn)
            self._insert_slice(conn, documents, ctx.config.name, ctx.version, chunks_sha256)
        finally:
            conn.close()

        if not documents:
            warnings.warn(
                f"{ctx.config.name}: empty chunks.jsonl, indexing zero chunks",
                stacklevel=2,
            )

        chunk_count = sum(len(document.chunks) for document in documents)
        print(
            f"{ctx.config.name} indexed v{ctx.version}: {len(documents)} documents, {chunk_count} chunks -> {db_path}"
        )
        return ctx

    def _bootstrap(self, conn: sqlite3.Connection) -> None:
        """Create the schema if absent and verify compatibility (rebuild-not-migrate)."""
        create_schema(conn)
        check_schema(conn)

    def _insert_slice(
        self,
        conn: sqlite3.Connection,
        documents: list[DocumentRow],
        source: str,
        version: str,
        chunks_sha256: str,
    ) -> None:
        """Insert one (source, version) slice in a single atomic transaction."""
        conn.execute("BEGIN")
        try:
            next_document_id = int(
                conn.execute("SELECT COALESCE(MAX(document_id), 0) + 1 FROM documents").fetchone()[0]
            )
            next_chunk_id = int(conn.execute("SELECT COALESCE(MAX(chunk_id), 0) + 1 FROM chunks").fetchone()[0])

            for document in documents:
                conn.execute(
                    "INSERT INTO documents (document_id, source, version, path, sha256) VALUES (?, ?, ?, ?, ?)",
                    (next_document_id, source, version, document.path, document.sha256),
                )
                for chunk in document.chunks:
                    conn.execute(
                        "INSERT INTO chunks (chunk_id, chunk_uuid, document_id, text, "
                        "start_line, end_line, sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            next_chunk_id,
                            chunk.chunk_uuid,
                            next_document_id,
                            chunk.text,
                            chunk.start_line,
                            chunk.end_line,
                            chunk.sha256,
                        ),
                    )
                    next_chunk_id += 1
                next_document_id += 1

            conn.execute("INSERT INTO fts_chunks (fts_chunks) VALUES ('rebuild')")
            conn.execute(
                "INSERT INTO indexed_sources (source, version, chunks_sha256, document_count, chunk_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, version, chunks_sha256, len(documents), sum(len(d.chunks) for d in documents)),
            )
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
