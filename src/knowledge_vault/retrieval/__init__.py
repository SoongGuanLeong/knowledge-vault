"""Retrieval package: gold knowledge.db surface.

Engine-agnostic search API (Project 0.5) plus the SQLite ``knowledge.db``
schema module shared by the IndexStage (write) and backend (read).
"""

from __future__ import annotations

from knowledge_vault.retrieval.rows import (
    CHUNK_SEPARATOR,
    ChunkRow,
    DocumentRow,
    parse_chunks,
)
from knowledge_vault.retrieval.schema import (
    SCHEMA_DDL,
    SCHEMA_VERSION,
    SchemaError,
    check_schema,
    connect_db,
    create_schema,
    knowledge_db_path,
)

__all__ = [
    "CHUNK_SEPARATOR",
    "ChunkRow",
    "DocumentRow",
    "SCHEMA_DDL",
    "SCHEMA_VERSION",
    "SchemaError",
    "check_schema",
    "connect_db",
    "create_schema",
    "knowledge_db_path",
    "parse_chunks",
]
