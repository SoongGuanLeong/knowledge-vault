"""Unit tests for retrieval/sqlite_backend.py: SQLiteFTSBackend (ticket #30).

Integration tests at the public seam: ``SQLiteFTSBackend`` against a real
temporary ``knowledge.db`` seeded through the ``IndexStage`` write path.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import fts5_available

from knowledge_vault.config import SourceConfig
from knowledge_vault.pipeline.context import PipelineContext
from knowledge_vault.retrieval import (
    SCHEMA_VERSION,
    SearchBackend,
    SearchBackendError,
    SearchFilters,
    SearchResult,
    SQLiteFTSBackend,
    connect_db,
    create_schema,
    knowledge_db_path,
)
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

    ``source``/``version`` select the slice's keys; ``store`` overrides the
    store root so tests can index multiple slices into one store.
    """

    counter = 0

    def _make(source: str = "test-source", version: str = "1.0.0", store: Path | None = None) -> PipelineContext:
        nonlocal counter
        counter += 1
        base = tmp_path / f"ctx-{counter}"
        config = SourceConfig(
            name=source,
            repo="file:///fake/repo",
            docs_path="docs",
            desired_tags=[f"v{version}"],
        )
        store = store if store is not None else base / "store"
        silver = base / "silver" / source / version
        bronze = base / "bronze" / source / version
        return PipelineContext(
            store=store,
            config=config,
            tag=f"v{version}",
            version=version,
            commit="abc1234",
            bronze_path=bronze,
            silver_path=silver,
            chunks_path=silver / "chunks" / "chunks.jsonl",
            repo_dir=bronze / "repo",
            manifest_path=bronze / "manifest.json",
        )

    return _make


def _index(
    make_ctx: Callable[..., PipelineContext],
    store: Path,
    source: str,
    version: str,
    records: list[dict[str, str | int]],
) -> None:
    ctx = make_ctx(source=source, version=version, store=store)
    _write_chunks(ctx, records)
    IndexStage().execute(ctx)


@pytest.fixture
def corpus(tmp_path: Path, make_ctx: Callable[..., PipelineContext]) -> Path:
    """A store with three slices across two sources and two versions."""
    store = tmp_path / "store"
    _index(
        make_ctx,
        store,
        "spark",
        "4.0.0",
        [
            _chunk_record("uuid-a", "intro.md", "broadcast spark engine", 1, 3),
            _chunk_record("uuid-b", "sql.md", "spark sql catalyst optimizer", 1, 2),
        ],
    )
    _index(make_ctx, store, "spark", "3.5.0", [_chunk_record("uuid-c", "intro.md", "legacy spark rdd", 1, 4)])
    _index(
        make_ctx, store, "flink", "1.17.0", [_chunk_record("uuid-d", "streams.md", "streaming dataflow engine", 1, 2)]
    )
    return store


@pytest.fixture
def relevance_store(tmp_path: Path, make_ctx: Callable[..., PipelineContext]) -> Path:
    """A store with one hot chunk, one cold chunk, and two identical chunks."""
    store = tmp_path / "relevance-store"
    _index(
        make_ctx,
        store,
        "spark",
        "4.0.0",
        [
            _chunk_record("uuid-hot", "hot.md", "spark spark spark spark", 1, 1),
            _chunk_record("uuid-cold", "cold.md", "spark appears once", 1, 1),
            _chunk_record("uuid-ident-j", "a.md", "spark identical text", 1, 1),
            _chunk_record("uuid-ident-k", "b.md", "spark identical text", 1, 1),
        ],
    )
    return store


def _open_backend(store: Path) -> SQLiteFTSBackend:
    backend = SQLiteFTSBackend(knowledge_db_path(store))
    backend.open()
    return backend


def test_search_returns_results_with_contract_fields(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        results = backend.search("spark")
    finally:
        backend.close()

    uuids = [r.chunk_uuid for r in results]
    assert set(uuids) == {"uuid-a", "uuid-b", "uuid-c"}

    by_uuid = {r.chunk_uuid: r for r in results}
    a = by_uuid["uuid-a"]
    assert a.text == "broadcast spark engine"
    assert a.source == "spark"
    assert a.version == "4.0.0"
    assert a.path == "intro.md"
    assert a.start_line == 1
    assert a.end_line == 3
    assert isinstance(a.score, float)


def test_search_all_matches_are_typed_search_results(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        results = backend.search("spark")
    finally:
        backend.close()

    assert results
    assert all(isinstance(r, SearchResult) for r in results)


def test_search_no_filters_spans_sources_and_versions(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        results = backend.search("spark")
    finally:
        backend.close()

    uuids = [r.chunk_uuid for r in results]
    assert set(uuids) == {"uuid-a", "uuid-b", "uuid-c"}


def test_search_blank_query_raises_value_error(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        for blank in ("", "   "):
            with pytest.raises(ValueError):
                backend.search(blank)
    finally:
        backend.close()


def test_search_non_positive_k_raises_value_error(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        for bad_k in (0, -3):
            with pytest.raises(ValueError):
                backend.search("spark", k=bad_k)
    finally:
        backend.close()


def test_search_k_limits_results(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        assert len(backend.search("spark", k=1)) == 1
        assert len(backend.search("spark", k=2)) == 2
        assert len(backend.search("spark")) == 3
    finally:
        backend.close()


def test_search_source_filter_restricts_to_source(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        spark = backend.search("spark", filters=SearchFilters(source="spark"))
        flink = backend.search("spark", filters=SearchFilters(source="flink"))
    finally:
        backend.close()

    assert {r.chunk_uuid for r in spark} == {"uuid-a", "uuid-b", "uuid-c"}
    assert flink == []


def test_search_source_and_version_filter_is_exact(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        results = backend.search("spark", filters=SearchFilters(source="spark", version="4.0.0"))
    finally:
        backend.close()

    assert {r.chunk_uuid for r in results} == {"uuid-a", "uuid-b"}
    assert all(r.version == "4.0.0" for r in results)


def test_search_version_filter_without_source(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        results = backend.search("spark", filters=SearchFilters(version="3.5.0"))
    finally:
        backend.close()

    assert {r.chunk_uuid for r in results} == {"uuid-c"}


def test_search_unknown_filter_value_returns_empty(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        results = backend.search("spark", filters=SearchFilters(source="no-such-source"))
    finally:
        backend.close()

    assert results == []


def test_search_no_matches_returns_empty(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        results = backend.search("zzznotpresent")
    finally:
        backend.close()

    assert results == []


def test_search_scores_higher_for_more_relevant(relevance_store: Path) -> None:
    backend = _open_backend(relevance_store)
    try:
        results = backend.search("spark")
    finally:
        backend.close()

    assert [r.chunk_uuid for r in results] == ["uuid-hot", "uuid-cold", "uuid-ident-j", "uuid-ident-k"]
    assert results[0].score > results[1].score


def test_search_returns_scores_descending(relevance_store: Path) -> None:
    backend = _open_backend(relevance_store)
    try:
        results = backend.search("spark")
    finally:
        backend.close()

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_ties_broken_deterministically(relevance_store: Path) -> None:
    backend = _open_backend(relevance_store)
    try:
        first = [r.chunk_uuid for r in backend.search("spark")]
        second = [r.chunk_uuid for r in backend.search("spark")]
    finally:
        backend.close()

    assert first == second == ["uuid-hot", "uuid-cold", "uuid-ident-j", "uuid-ident-k"]


def test_search_bm25_prefers_shorter_documents_for_equal_term_frequency(
    tmp_path: Path, make_ctx: Callable[..., PipelineContext]
) -> None:
    store = tmp_path / "length-store"
    _index(
        make_ctx,
        store,
        "spark",
        "4.0.0",
        [
            _chunk_record("uuid-short", "short.md", "spark"),
            _chunk_record("uuid-long", "long.md", "spark " + "word " * 50),
        ],
    )

    backend = _open_backend(store)
    try:
        results = backend.search("spark")
    finally:
        backend.close()

    assert [r.chunk_uuid for r in results] == ["uuid-short", "uuid-long"]
    assert results[0].score > results[1].score


def test_search_unicode_latin_diacritics_match_folded_query(
    tmp_path: Path, make_ctx: Callable[..., PipelineContext]
) -> None:
    store = tmp_path / "unicode-store"
    _index(make_ctx, store, "spark", "4.0.0", [_chunk_record("uuid-uni", "intro.md", "Café naïve résumé déjà vu")])

    backend = _open_backend(store)
    try:
        folded = backend.search("cafe")
        as_written = backend.search("Café")
    finally:
        backend.close()

    assert [r.chunk_uuid for r in folded] == ["uuid-uni"]
    assert [r.chunk_uuid for r in as_written] == ["uuid-uni"]


def test_search_unicode_cjk_words_tokenize_on_whitespace(
    tmp_path: Path, make_ctx: Callable[..., PipelineContext]
) -> None:
    store = tmp_path / "cjk-store"
    _index(make_ctx, store, "spark", "4.0.0", [_chunk_record("uuid-cjk", "intro.md", "한국어 문서 검색 시스템")])

    backend = _open_backend(store)
    try:
        results = backend.search("한국어")
    finally:
        backend.close()

    assert [r.chunk_uuid for r in results] == ["uuid-cjk"]


def test_search_unicode_cjk_contiguous_run_needs_prefix(
    tmp_path: Path, make_ctx: Callable[..., PipelineContext]
) -> None:
    store = tmp_path / "cjk-run-store"
    _index(make_ctx, store, "spark", "4.0.0", [_chunk_record("uuid-run", "intro.md", "机器学习模型用于处理自然语言")])

    backend = _open_backend(store)
    try:
        substring = backend.search("机器学习")
        prefix = backend.search("机器学*")
    finally:
        backend.close()

    assert substring == []
    assert [r.chunk_uuid for r in prefix] == ["uuid-run"]


def test_search_phrase_requires_adjacent_terms(tmp_path: Path, make_ctx: Callable[..., PipelineContext]) -> None:
    store = tmp_path / "phrase-store"
    _index(make_ctx, store, "spark", "4.0.0", [_chunk_record("uuid-phrase", "sql.md", "spark sql catalyst optimizer")])

    backend = _open_backend(store)
    try:
        forward = backend.search('"spark sql"')
        reversed_ = backend.search('"sql spark"')
    finally:
        backend.close()

    assert [r.chunk_uuid for r in forward] == ["uuid-phrase"]
    assert reversed_ == []


def test_search_prefix_matches_word_prefix(tmp_path: Path, make_ctx: Callable[..., PipelineContext]) -> None:
    store = tmp_path / "prefix-store"
    _index(make_ctx, store, "spark", "4.0.0", [_chunk_record("uuid-prefix", "streams.md", "streaming dataflow engine")])

    backend = _open_backend(store)
    try:
        prefix = backend.search("stream*")
        non_prefix = backend.search("streamin")
    finally:
        backend.close()

    assert [r.chunk_uuid for r in prefix] == ["uuid-prefix"]
    assert non_prefix == []


def test_search_empty_index_returns_no_results(tmp_path: Path, make_ctx: Callable[..., PipelineContext]) -> None:
    store = tmp_path / "empty-store"
    _index(make_ctx, store, "spark", "4.0.0", [])

    backend = _open_backend(store)
    try:
        results = backend.search("anything")
    finally:
        backend.close()

    assert results == []


def test_open_on_missing_db_raises_search_backend_error(tmp_path: Path) -> None:
    backend = SQLiteFTSBackend(tmp_path / "does-not-exist" / "knowledge.db")
    with pytest.raises(SearchBackendError) as excinfo:
        backend.open()

    assert excinfo.value.__cause__ is not None


def test_open_on_incompatible_schema_raises_search_backend_error(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    conn = connect_db(db_path)
    create_schema(conn)
    conn.execute("UPDATE metadata SET schema_version = ? WHERE id = 1", (SCHEMA_VERSION + 1,))
    conn.commit()
    conn.close()

    backend = SQLiteFTSBackend(db_path)
    with pytest.raises(SearchBackendError):
        backend.open()


def test_open_on_corrupt_db_raises_search_backend_error(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.db"
    db_path.write_bytes(b"this is not a sqlite database")

    backend = SQLiteFTSBackend(db_path)
    with pytest.raises(SearchBackendError):
        backend.open()


def test_search_before_open_raises_search_backend_error(tmp_path: Path) -> None:
    backend = SQLiteFTSBackend(tmp_path / "knowledge.db")
    with pytest.raises(SearchBackendError):
        backend.search("spark")


def test_search_after_close_raises_search_backend_error(corpus: Path) -> None:
    backend = _open_backend(corpus)
    backend.close()
    with pytest.raises(SearchBackendError):
        backend.search("spark")


def test_backend_does_not_expose_connection_or_cursor(tmp_path: Path) -> None:
    backend = SQLiteFTSBackend(tmp_path / "knowledge.db")
    assert not hasattr(backend, "connection")
    assert not hasattr(backend, "cursor")


def test_backend_structural_subtype_of_search_backend_protocol(corpus: Path) -> None:
    backend = _open_backend(corpus)
    try:
        _assert_accepts_backend(backend)
    finally:
        backend.close()


def _assert_accepts_backend(backend: SearchBackend) -> None:
    assert isinstance(backend, SQLiteFTSBackend)


def test_context_manager_lifecycle(corpus: Path) -> None:
    with SQLiteFTSBackend(knowledge_db_path(corpus)) as backend:
        assert backend.search("spark") != []
    with pytest.raises(SearchBackendError):
        backend.search("spark")
