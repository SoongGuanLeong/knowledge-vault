"""Gold retrieval database schema: DDL, connection helpers, path plumbing.

Implements the frozen Project 0.5 ``knowledge.db`` contract (ticket #24) using
the FTS5 setup findings (research #23). Shared by the SQLite IndexStage (write)
and the SQLiteFTSBackend (read).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA_DDL: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS metadata (  id INTEGER PRIMARY KEY CHECK (id = 1),  schema_version INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS indexed_sources ("
    "  source TEXT NOT NULL,"
    "  version TEXT NOT NULL,"
    "  chunks_sha256 TEXT NOT NULL,"
    "  document_count INTEGER NOT NULL,"
    "  chunk_count INTEGER NOT NULL,"
    "  PRIMARY KEY (source, version)"
    ")",
    "CREATE TABLE IF NOT EXISTS documents ("
    "  document_id INTEGER PRIMARY KEY,"
    "  source TEXT NOT NULL,"
    "  version TEXT NOT NULL,"
    "  path TEXT NOT NULL,"
    "  sha256 TEXT NOT NULL,"
    "  UNIQUE (source, version, path)"
    ")",
    "CREATE TABLE IF NOT EXISTS chunks ("
    "  chunk_id INTEGER PRIMARY KEY,"
    "  chunk_uuid TEXT NOT NULL,"
    "  document_id INTEGER NOT NULL,"
    "  text TEXT NOT NULL,"
    "  start_line INTEGER,"
    "  end_line INTEGER,"
    "  sha256 TEXT NOT NULL,"
    "  FOREIGN KEY (document_id) REFERENCES documents (document_id)"
    "    ON DELETE CASCADE,"
    "  UNIQUE (document_id, chunk_uuid)"
    ")",
    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(  text,  content=chunks,  content_rowid=chunk_id)",
)


class SchemaError(Exception):
    """Raised when a database's schema is missing or incompatible."""


def knowledge_db_path(store: Path) -> Path:
    """The store-level gold retrieval database path.

    Parameters
    ----------
    store : Path
        Knowledge-store root.

    Returns
    -------
    Path
        ``<store>/gold/knowledge.db``.
    """
    return store / "gold" / "knowledge.db"


def connect_db(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection to *path* with foreign keys enforced.

    Parameters
    ----------
    path : Path
        Database file location.

    Returns
    -------
    sqlite3.Connection
        Open connection with ``PRAGMA foreign_keys = ON``.
    """
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the knowledge.db schema idempotently on *conn*.

    Existing tables are left untouched; the ``metadata`` singleton row is
    seeded only when absent, so a version bump is never silently overwritten
    (rebuild-not-migrate is the caller's job to enforce via
    :func:`check_schema`). The FTS index is not populated here — IndexStage
    inserts in id order and issues ``rebuild`` after loading data.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open connection to the database to create the schema on.
    """
    conn.execute("BEGIN")
    try:
        for statement in SCHEMA_DDL:
            conn.execute(statement)
        conn.execute(
            "INSERT OR IGNORE INTO metadata (id, schema_version) VALUES (1, ?)",
            (SCHEMA_VERSION,),
        )
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def check_schema(conn: sqlite3.Connection) -> None:
    """Verify *conn* holds the current knowledge.db schema.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open connection to a knowledge.db.

    Raises
    ------
    SchemaError
        If the metadata table is missing/unreadable or ``schema_version``
        differs from :data:`SCHEMA_VERSION`.
    """
    try:
        row = conn.execute("SELECT schema_version FROM metadata WHERE id = 1").fetchone()
    except sqlite3.DatabaseError as exc:
        raise SchemaError("knowledge.db is missing or corrupt") from exc
    if row is None or row[0] != SCHEMA_VERSION:
        found = row[0] if row is not None else "missing"
        raise SchemaError(
            f"unsupported knowledge.db schema_version {found}; expected {SCHEMA_VERSION} (rebuild, do not migrate)"
        )
