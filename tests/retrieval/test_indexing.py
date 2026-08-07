"""Unit tests for retrieval/indexing.py: IndexStage indexing and idempotent skip (tickets #41, #37)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import fts5_available

from knowledge_vault.config import SourceConfig
from knowledge_vault.pipeline.context import PipelineContext
from knowledge_vault.retrieval import SCHEMA_VERSION, SchemaError, connect_db, create_schema, knowledge_db_path
from knowledge_vault.retrieval.indexing import IndexStage

if not fts5_available():
    pytest.skip("FTS5 not available in this SQLite build", allow_module_level=True)


def _chunk_record(
    chunk_id: str,
    path: str,
    text: str,
    start_line: int = 1,
    end_line: int = 1,
) -> dict[str, str | int]:
    return {
        "chunk_id": chunk_id,
        "source": "test-source",
        "version": "1.0.0",
        "path": path,
        "text": text,
        "start_line": start_line,
        "end_line": end_line,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "parent_document": path,
    }


def _write_chunks(ctx: PipelineContext, records: list[dict[str, str | int]]) -> None:
    ctx.chunks_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    content = "\n".join(lines) + "\n" if lines else ""
    ctx.chunks_path.write_text(content, encoding="utf-8")


@pytest.fixture
def make_ctx(tmp_path: Path) -> Callable[..., PipelineContext]:
    """Factory producing an isolated PipelineContext under pytest's tmp_path.

    ``version`` selects the slice's version key; ``store`` overrides the store
    root so tests can index multiple versions into one store.
    """

    counter = 0

    def _make(version: str = "1.0.0", store: Path | None = None) -> PipelineContext:
        nonlocal counter
        counter += 1
        base = tmp_path / f"ctx-{counter}"
        config = SourceConfig(
            name="test-source",
            repo="file:///fake/repo",
            docs_path="docs",
            desired_tags=[f"v{version}"],
        )
        store = store if store is not None else base / "store"
        silver = base / "silver" / "test-source" / version
        bronze = base / "bronze" / "test-source" / version
        gold = base / "gold" / "test-source" / version
        return PipelineContext(
            store=store,
            config=config,
            tag=f"v{version}",
            version=version,
            commit="abc1234",
            bronze_path=bronze,
            silver_path=silver,
            gold_path=gold,
            chunks_path=silver / "chunks" / "chunks.jsonl",
            repo_dir=bronze / "repo",
            manifest_path=bronze / "manifest.json",
        )

    return _make


def test_missing_chunks_raises_exact_message(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()

    with pytest.raises(FileNotFoundError) as excinfo:
        IndexStage().execute(ctx)

    assert str(excinfo.value) == "Run ChunkStage before IndexStage."


def test_reingest_unchanged_slice_skips_without_touching_db(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(
        ctx,
        [
            _chunk_record("uuid-a", "intro.md", "alpha"),
            _chunk_record("uuid-b", "sql.md", "beta"),
        ],
    )

    IndexStage().execute(ctx)

    db_path = knowledge_db_path(ctx.store)
    before = db_path.read_bytes()
    os.utime(db_path, (1000, 1000))
    with sqlite3.connect(db_path) as conn:
        docs_before = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        chunks_before = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        fts_before = conn.execute("SELECT count(*) FROM fts_chunks").fetchone()[0]

    IndexStage().execute(ctx)

    assert db_path.read_bytes() == before
    assert db_path.stat().st_mtime_ns == 1000 * 1_000_000_000
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == docs_before
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == chunks_before
        assert conn.execute("SELECT count(*) FROM fts_chunks").fetchone()[0] == fts_before
        assert conn.execute("SELECT count(*) FROM indexed_sources").fetchone()[0] == 1


def test_reingest_skip_prints_verbatim_up_to_date_literal(
    make_ctx: Callable[[], PipelineContext],
    capsys,
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record("uuid-a", "intro.md", "alpha")])

    IndexStage().execute(ctx)
    capsys.readouterr()

    IndexStage().execute(ctx)
    out = capsys.readouterr().out

    assert "gold index up-to-date at v1.0.0" in out
    assert "test-source gold index" not in out
    assert "indexed v1.0.0" not in out


def test_skip_path_does_not_emit_empty_slice_warning(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [])

    with pytest.warns(UserWarning, match="zero chunks"):
        IndexStage().execute(ctx)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        IndexStage().execute(ctx)

    assert not any(issubclass(w.category, UserWarning) for w in caught)


def test_fresh_store_bootstraps_schema_and_populates(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record("uuid-a", "intro.md", "alpha")])

    result = IndexStage().execute(ctx)
    assert result is ctx

    db_path = knowledge_db_path(ctx.store)
    assert db_path.is_file()
    with sqlite3.connect(db_path) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"metadata", "documents", "chunks", "fts_chunks", "indexed_sources"} <= names
        assert conn.execute("SELECT schema_version FROM metadata WHERE id = 1").fetchone() == (SCHEMA_VERSION,)
        assert conn.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (1,)


def test_ids_assigned_in_chunks_jsonl_order(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    _write_chunks(
        ctx,
        [
            _chunk_record("uuid-a", "intro.md", "alpha"),
            _chunk_record("uuid-b", "intro.md", "beta"),
            _chunk_record("uuid-c", "sql.md", "gamma"),
            _chunk_record("uuid-d", "sql.md", "delta"),
        ],
    )

    IndexStage().execute(ctx)

    with sqlite3.connect(knowledge_db_path(ctx.store)) as conn:
        assert conn.execute("SELECT path, document_id FROM documents ORDER BY document_id").fetchall() == [
            ("intro.md", 1),
            ("sql.md", 2),
        ]
        assert conn.execute("SELECT chunk_id, chunk_uuid FROM chunks ORDER BY chunk_id").fetchall() == [
            (1, "uuid-a"),
            (2, "uuid-b"),
            (3, "uuid-c"),
            (4, "uuid-d"),
        ]


def test_document_sha256_derived_from_ordered_chunk_texts(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    _write_chunks(
        ctx,
        [
            _chunk_record("uuid-a", "intro.md", "alpha"),
            _chunk_record("uuid-b", "intro.md", "beta"),
        ],
    )

    IndexStage().execute(ctx)

    expected = hashlib.sha256(b"alpha\0beta").hexdigest()
    with sqlite3.connect(knowledge_db_path(ctx.store)) as conn:
        assert conn.execute("SELECT path, sha256 FROM documents ORDER BY document_id").fetchall() == [
            ("intro.md", expected),
        ]


def test_indexed_sources_registry_records_chunks_sha_and_counts(
    make_ctx: Callable[[], PipelineContext],
) -> None:
    ctx = make_ctx()
    _write_chunks(
        ctx,
        [
            _chunk_record("uuid-a", "intro.md", "alpha"),
            _chunk_record("uuid-b", "sql.md", "beta"),
        ],
    )

    IndexStage().execute(ctx)

    expected_sha = hashlib.sha256(ctx.chunks_path.read_bytes()).hexdigest()
    with sqlite3.connect(knowledge_db_path(ctx.store)) as conn:
        assert conn.execute(
            "SELECT source, version, chunks_sha256, document_count, chunk_count FROM indexed_sources"
        ).fetchall() == [("test-source", "1.0.0", expected_sha, 2, 2)]


def test_empty_chunks_warns_and_records_zero_counts(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [])

    with pytest.warns(UserWarning, match="zero chunks"):
        IndexStage().execute(ctx)

    with sqlite3.connect(knowledge_db_path(ctx.store)) as conn:
        assert conn.execute(
            "SELECT document_count, chunk_count FROM indexed_sources WHERE source = 'test-source' AND version = '1.0.0'"
        ).fetchone() == (0, 0)
        assert conn.execute("SELECT count(*) FROM documents").fetchone() == (0,)


def test_fts_rebuilt_and_searchable(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [_chunk_record("uuid-a", "intro.md", "broadcast spark engine")])

    IndexStage().execute(ctx)

    with sqlite3.connect(knowledge_db_path(ctx.store)) as conn:
        assert conn.execute("SELECT rowid FROM fts_chunks WHERE fts_chunks MATCH 'spark'").fetchall() == [(1,)]


def test_new_rows_append_after_existing_rows(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    db_path = knowledge_db_path(ctx.store)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_db(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO documents (document_id, source, version, path, sha256) VALUES (1, 'other', '0.1.0', 'a.md', 'x')"
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, chunk_uuid, document_id, text, start_line, end_line, sha256) "
        "VALUES (1, 'other-uuid', 1, 'text', 1, 1, 'y')"
    )
    conn.commit()
    conn.close()

    _write_chunks(ctx, [_chunk_record("uuid-a", "intro.md", "alpha")])
    IndexStage().execute(ctx)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT document_id, path FROM documents ORDER BY document_id").fetchall() == [
            (1, "a.md"),
            (2, "intro.md"),
        ]
        assert conn.execute("SELECT chunk_id, chunk_uuid FROM chunks ORDER BY chunk_id").fetchall() == [
            (1, "other-uuid"),
            (2, "uuid-a"),
        ]


def test_incompatible_schema_raises(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    db_path = knowledge_db_path(ctx.store)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_db(db_path)
    create_schema(conn)
    conn.execute("UPDATE metadata SET schema_version = 999 WHERE id = 1")
    conn.commit()
    conn.close()

    _write_chunks(ctx, [_chunk_record("uuid-a", "intro.md", "alpha")])
    with pytest.raises(SchemaError):
        IndexStage().execute(ctx)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM indexed_sources").fetchone() == (0,)


def test_malformed_line_aborts_without_partial_database(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    _write_chunks(ctx, [])
    ctx.chunks_path.write_text(
        '{"chunk_id": "1", "path": "a.md", "text": "ok", "start_line": 1, "end_line": 1, "sha256": "x"}\n'
        "this is not json\n",
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        IndexStage().execute(ctx)

    assert not knowledge_db_path(ctx.store).exists()


def test_mid_insert_failure_rolls_back_whole_slice(make_ctx: Callable[[], PipelineContext]) -> None:
    ctx = make_ctx()
    db_path = knowledge_db_path(ctx.store)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_db(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO documents (document_id, source, version, path, sha256) "
        "VALUES (1, 'test-source', '1.0.0', 'dup.md', 'x')"
    )
    conn.commit()
    conn.close()

    _write_chunks(
        ctx,
        [
            _chunk_record("uuid-a", "ok.md", "alpha"),
            _chunk_record("uuid-b", "dup.md", "beta"),
        ],
    )
    with pytest.raises(sqlite3.IntegrityError):
        IndexStage().execute(ctx)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM fts_chunks").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM indexed_sources").fetchone() == (0,)


def test_deterministic_across_fresh_stores(make_ctx: Callable[[], PipelineContext]) -> None:
    records = [
        _chunk_record("uuid-a", "intro.md", "alpha"),
        _chunk_record("uuid-b", "intro.md", "beta"),
        _chunk_record("uuid-c", "sql.md", "gamma"),
    ]

    ctx_a = make_ctx()
    _write_chunks(ctx_a, records)
    IndexStage().execute(ctx_a)

    ctx_b = make_ctx()
    _write_chunks(ctx_b, records)
    IndexStage().execute(ctx_b)

    def dump(
        ctx: PipelineContext,
    ) -> tuple[
        list[tuple[object, ...]],
        list[tuple[object, ...]],
        list[tuple[object, ...]],
    ]:
        with sqlite3.connect(knowledge_db_path(ctx.store)) as conn:
            return (
                conn.execute(
                    "SELECT document_id, source, version, path, sha256 FROM documents ORDER BY document_id"
                ).fetchall(),
                conn.execute(
                    "SELECT chunk_id, chunk_uuid, document_id, text, start_line, end_line, sha256 "
                    "FROM chunks ORDER BY chunk_id"
                ).fetchall(),
                conn.execute(
                    "SELECT source, version, chunks_sha256, document_count, chunk_count "
                    "FROM indexed_sources ORDER BY source, version"
                ).fetchall(),
            )

    assert dump(ctx_a) == dump(ctx_b)


def test_same_chunk_uuid_across_versions_is_allowed(make_ctx: Callable[..., PipelineContext]) -> None:
    record = _chunk_record("uuid-shared", "intro.md", "alpha")

    ctx_v1 = make_ctx()
    _write_chunks(ctx_v1, [record])
    IndexStage().execute(ctx_v1)

    ctx_v2 = make_ctx(version="2.0.0", store=ctx_v1.store)
    _write_chunks(ctx_v2, [record])
    IndexStage().execute(ctx_v2)

    with sqlite3.connect(knowledge_db_path(ctx_v1.store)) as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone() == (2,)
        assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (2,)
        assert conn.execute("SELECT chunk_uuid, count(*) FROM chunks GROUP BY chunk_uuid").fetchall() == [
            ("uuid-shared", 2)
        ]
