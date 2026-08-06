"""Unit tests for retrieval/schema.py: knowledge.db schema module (ticket #28)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from knowledge_vault.retrieval import (
    SCHEMA_VERSION,
    SchemaError,
    check_schema,
    connect_db,
    create_schema,
    knowledge_db_path,
)


def _fts5_available() -> bool:
    try:
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
    except sqlite3.OperationalError:
        return False
    return True


if not _fts5_available():
    pytest.skip("FTS5 not available in this SQLite build", allow_module_level=True)


@pytest.fixture
def db(tmp_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """An open connection to a schema-created knowledge.db."""
    conn = connect_db(tmp_path / "knowledge.db")
    create_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


def test_knowledge_db_path_resolves_to_store_gold(tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert knowledge_db_path(store) == store / "gold" / "knowledge.db"
    assert knowledge_db_path(store).parent == store / "gold"


def test_connect_db_enables_foreign_keys(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "knowledge.db")
    try:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
    finally:
        conn.close()
    assert row is not None and row[0] == 1


def test_create_schema_creates_all_tables(db: sqlite3.Connection) -> None:
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    assert {"metadata", "indexed_sources", "documents", "chunks", "fts_chunks"} <= names


def test_create_schema_is_idempotent(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "knowledge.db")
    try:
        create_schema(conn)
        create_schema(conn)
        count = conn.execute(
            "SELECT count(*) FROM metadata WHERE id = 1 AND schema_version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
    finally:
        conn.close()
    assert count is not None and count[0] == 1


def test_create_schema_seeds_metadata_singleton(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT id, schema_version FROM metadata").fetchall()
    assert rows == [(1, SCHEMA_VERSION)]


def test_metadata_enforces_single_row(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO metadata (id, schema_version) VALUES (2, 1)")


def test_check_schema_passes_on_current_schema(db: sqlite3.Connection) -> None:
    check_schema(db)


def test_check_schema_raises_on_empty_db(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "knowledge.db")
    try:
        with pytest.raises(SchemaError, match="missing or corrupt"):
            check_schema(conn)
    finally:
        conn.close()


def test_check_schema_raises_on_version_mismatch(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "knowledge.db")
    try:
        create_schema(conn)
        conn.execute("UPDATE metadata SET schema_version = ? WHERE id = 1", (SCHEMA_VERSION + 1,))
        conn.commit()
        with pytest.raises(SchemaError, match=str(SCHEMA_VERSION + 1)):
            check_schema(conn)
    finally:
        conn.close()


def test_create_schema_does_not_overwrite_existing_metadata(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "knowledge.db")
    try:
        create_schema(conn)
        conn.execute("UPDATE metadata SET schema_version = ? WHERE id = 1", (SCHEMA_VERSION + 1,))
        conn.commit()
        create_schema(conn)
        stored = conn.execute("SELECT schema_version FROM metadata WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert stored is not None and stored[0] == SCHEMA_VERSION + 1


def test_indexed_sources_unique_per_source_version(db: sqlite3.Connection) -> None:
    insert = (
        "INSERT INTO indexed_sources (source, version, chunks_sha256, document_count, chunk_count) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    db.execute(insert, ("spark", "4.0.0", "aaa", 1, 2))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(insert, ("spark", "4.0.0", "bbb", 3, 4))
    db.execute(insert, ("spark", "3.5.0", "ccc", 1, 1))


def test_documents_unique_per_source_version_path(db: sqlite3.Connection) -> None:
    insert = "INSERT INTO documents (document_id, source, version, path, sha256) VALUES (?, ?, ?, ?, ?)"
    db.execute(insert, (1, "spark", "4.0.0", "sql.md", "aaa"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(insert, (2, "spark", "4.0.0", "sql.md", "bbb"))
    db.execute(insert, (3, "spark", "3.5.0", "sql.md", "ccc"))


def test_chunk_insert_rejects_orphan_document(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO chunks (chunk_id, chunk_uuid, document_id, text, start_line, end_line, sha256) "
            "VALUES (1, 'uuid-1', 999, 'text', 1, 2, 'bbb')"
        )


def test_chunk_delete_cascades_from_document(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO documents (document_id, source, version, path, sha256) "
        "VALUES (1, 'spark', '4.0.0', 'sql.md', 'aaa')"
    )
    db.execute(
        "INSERT INTO chunks (chunk_id, chunk_uuid, document_id, text, start_line, end_line, sha256) "
        "VALUES (1, 'uuid-1', 1, 'text', 1, 2, 'bbb')"
    )
    db.execute("DELETE FROM documents WHERE document_id = 1")

    count = db.execute("SELECT count(*) FROM chunks").fetchone()
    assert count is not None and count[0] == 0


def test_chunk_uuid_unique_per_document_not_global(db: sqlite3.Connection) -> None:
    insert_doc = "INSERT INTO documents (document_id, source, version, path, sha256) VALUES (?, ?, ?, ?, ?)"
    insert_chunk = (
        "INSERT INTO chunks (chunk_id, chunk_uuid, document_id, text, start_line, end_line, sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    db.execute(insert_doc, (1, "spark", "0.1.0", "intro.md", "aaa"))
    db.execute(insert_doc, (2, "spark", "0.2.0", "intro.md", "bbb"))
    db.execute(insert_chunk, (1, "uuid-1", 1, "text", 1, 2, "ccc"))
    db.execute(insert_chunk, (2, "uuid-1", 2, "text", 1, 2, "ddd"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(insert_chunk, (3, "uuid-1", 1, "text", 1, 2, "eee"))


def test_fts_chunks_is_external_content_table(db: sqlite3.Connection) -> None:
    ddl = db.execute("SELECT sql FROM sqlite_master WHERE name = 'fts_chunks'").fetchone()
    assert ddl is not None
    assert "content=chunks" in ddl[0]
    assert "content_rowid=chunk_id" in ddl[0]


def test_fts_chunks_rebuild_indexes_chunk_text(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO documents (document_id, source, version, path, sha256) "
        "VALUES (1, 'spark', '4.0.0', 'sql.md', 'aaa')"
    )
    db.execute(
        "INSERT INTO chunks (chunk_id, chunk_uuid, document_id, text, start_line, end_line, sha256) "
        "VALUES (1, 'uuid-1', 1, 'broadcast spark engine', 1, 2, 'bbb')"
    )
    db.execute("INSERT INTO fts_chunks (fts_chunks) VALUES ('rebuild')")

    rows = db.execute("SELECT rowid FROM fts_chunks WHERE fts_chunks MATCH 'broadcast'").fetchall()
    assert rows == [(1,)]
