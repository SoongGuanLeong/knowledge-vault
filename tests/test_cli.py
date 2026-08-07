"""CLI-level tests for the kv tool. The CLI is the single testing seam."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from conftest import fts5_available

from knowledge_vault.retrieval import SCHEMA_VERSION, connect_db, knowledge_db_path

skip_without_fts5 = pytest.mark.skipif(not fts5_available(), reason="FTS5 not available in this SQLite build")


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file as a dict."""
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_cli_introspection(run_cli) -> None:
    help_result = run_cli(["--help"])
    assert help_result.returncode == 0
    assert "usage" in help_result.stdout

    version_result = run_cli(["--version"])
    assert version_result.returncode == 0
    assert "0.1.0" in version_result.stdout


def test_unknown_source_fails_clearly(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["discover", "nosuch", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode != 0
    assert "nosuch" in result.stderr


def test_discover_lists_available_tags(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["discover", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr
    assert "v0.1.0" in result.stdout
    assert "v0.2.0" in result.stdout
    assert not (store_dir / "bronze").exists()


def test_ingest_creates_bronze_snapshot(run_cli, sources_dir, store_dir, repo_url) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    bronze = store_dir / "bronze" / "spark" / "0.1.0"
    assert (bronze / "repo").is_dir()

    manifest = load_json(bronze / "manifest.json")
    assert manifest["name"] == "spark"
    assert manifest["repo"] == repo_url
    assert manifest["requested_tag"] == "v0.1.0"
    assert manifest["resolved_tag"] == "v0.1.0"
    assert manifest["commit"]
    assert manifest["retrieved_at"]
    assert manifest["docs_path"] == "docs"


def test_bronze_is_full_repo_snapshot(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    bronze_repo = store_dir / "bronze" / "spark" / "0.1.0" / "repo"
    assert (bronze_repo / "README.md").is_file()
    assert (bronze_repo / "docs" / "intro.md").is_file()


def test_ingest_silver_is_selective(run_cli, sources_dir, store_dir, fixture_repo) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    silver = store_dir / "silver" / "spark" / "0.1.0" / "docs"
    source_docs = fixture_repo / "docs"
    assert (silver / "intro.md").read_bytes() == (source_docs / "intro.md").read_bytes()
    assert (silver / "sql.md").read_bytes() == (source_docs / "sql.md").read_bytes()
    # binary/non-doc files are excluded from silver
    assert not (silver / "img" / "logo.png").exists()
    # bronze remains the source of truth
    assert (store_dir / "bronze" / "spark" / "0.1.0" / "repo" / "docs" / "img" / "logo.png").exists()


def test_ingest_writes_silver_manifests(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    silver = store_dir / "silver" / "spark" / "0.1.0"
    manifest = load_json(silver / "manifest.json")
    assert manifest["name"] == "spark"
    assert manifest["version"] == "0.1.0"
    assert manifest["file_count"] == 2
    assert manifest["files"] == ["intro.md", "sql.md"]
    assert ".md" in manifest["extraction_patterns"]
    inventory = manifest["extraction_inventory"]
    assert inventory["total_files_discovered"] == 3
    assert inventory["included"].__len__() == 2
    assert inventory["skipped"].__len__() == 1
    assert inventory["skipped"][0]["reason"] == "binary_or_non_doc"

    lineage = load_json(silver / "lineage.json")
    assert lineage["silver"]["version"] == "0.1.0"
    assert lineage["bronze"]["commit"]


def test_ingest_is_idempotent(run_cli, sources_dir, store_dir) -> None:
    first = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert first.returncode == 0, first.stderr

    second = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert second.returncode == 0, second.stderr
    assert "already present" in second.stdout

    manifest = load_json(store_dir / "bronze" / "spark" / "0.1.0" / "manifest.json")
    assert manifest["commit"]


def test_list_shows_ingested_sources(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    result = run_cli(["list", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0
    assert "spark" in result.stdout
    assert "0.1.0" in result.stdout


def test_missing_tag_fails_clearly(run_cli, sources_dir, store_dir, repo_url, make_multi_tag_yaml) -> None:
    make_multi_tag_yaml(sources_dir / "spark.yaml", repo_url, ["v9.9.9"])
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode != 0
    assert "v9.9.9" in result.stderr


def test_store_flag_beats_env_var(run_cli, sources_dir, tmp_path) -> None:
    env_store = tmp_path / "env-store"
    flag_store = tmp_path / "flag-store"
    result = run_cli(
        ["ingest", "spark", "--tag", "v0.1.0", "--store", str(flag_store), "--sources", str(sources_dir)],
        env={"KV_STORE": str(env_store)},
    )
    assert result.returncode == 0, result.stderr
    assert (flag_store / "bronze" / "spark" / "0.1.0").is_dir()
    assert not (env_store / "bronze").exists()


def test_env_var_store_used_without_flag(run_cli, sources_dir, tmp_path) -> None:
    env_store = tmp_path / "env-store"
    result = run_cli(
        ["ingest", "spark", "--tag", "v0.1.0", "--sources", str(sources_dir)], env={"KV_STORE": str(env_store)}
    )
    assert result.returncode == 0, result.stderr
    assert (env_store / "bronze" / "spark" / "0.1.0").is_dir()


# --- selective extraction with comprehensive fixture ---


def test_ingest_silver_selective_all_extensions(run_cli, docs_sources_dir, store_dir, docs_repo) -> None:
    result = run_cli(["ingest", "docs", "--store", str(store_dir), "--sources", str(docs_sources_dir)])
    assert result.returncode == 0, result.stderr

    silver = store_dir / "silver" / "docs" / "1.0.0" / "docs"
    source_docs = docs_repo / "docs"

    expected_files = [
        "README.md",
        "Guide.Md",
        "guide.rst",
        "index.html",
        "notes.txt",
        "book.adoc",
        "nested/tutorial.md",
    ]
    for f in expected_files:
        assert (silver / f).is_file(), f"Expected {f} in silver"
        assert (silver / f).read_bytes() == (source_docs / f).read_bytes()

    excluded_files = [
        "image.png",
        "logo.svg",
        "style.css",
        "config.json",
        "nested/picture.jpg",
    ]
    for f in excluded_files:
        assert not (silver / f).exists(), f"Did not expect {f} in silver"

    for f in excluded_files:
        assert (store_dir / "bronze" / "docs" / "1.0.0" / "repo" / "docs" / f).is_file(), f"Bronze should retain {f}"


def test_ingest_silver_manifest_inventory(run_cli, docs_sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "docs", "--store", str(store_dir), "--sources", str(docs_sources_dir)])
    assert result.returncode == 0, result.stderr

    silver = store_dir / "silver" / "docs" / "1.0.0"
    manifest = load_json(silver / "manifest.json")

    assert manifest["name"] == "docs"
    assert manifest["version"] == "1.0.0"
    assert manifest["file_count"] == 7
    assert manifest["files"] == [
        "Guide.Md",
        "README.md",
        "book.adoc",
        "guide.rst",
        "index.html",
        "nested/tutorial.md",
        "notes.txt",
    ]
    assert manifest["extraction_patterns"] == [".md", ".mdx", ".rst", ".txt", ".adoc", ".html"]

    inventory = manifest["extraction_inventory"]
    assert inventory["total_files_discovered"] == 12
    assert len(inventory["included"]) == 7
    assert len(inventory["skipped"]) == 5

    skipped_sources = [s["source"] for s in inventory["skipped"]]
    assert "image.png" in skipped_sources
    assert "logo.svg" in skipped_sources
    assert "style.css" in skipped_sources
    assert "config.json" in skipped_sources
    assert "nested/picture.jpg" in skipped_sources

    for entry in inventory["skipped"]:
        assert entry["reason"] == "binary_or_non_doc"

    for entry in inventory["included"]:
        assert "checksum" in entry
        assert "source" in entry

    lineage = load_json(silver / "lineage.json")
    assert lineage["silver"]["version"] == "1.0.0"
    assert lineage["bronze"]["commit"]


# --- chunking end-to-end ---


def test_ingest_writes_chunks_structured(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    chunks_dir = store_dir / "silver" / "spark" / "0.1.0" / "chunks"
    assert (chunks_dir / "chunks.jsonl").is_file()
    assert (chunks_dir / "manifest.json").is_file()

    lines = (chunks_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line]
    assert records

    expected_fields = {
        "chunk_id",
        "source",
        "version",
        "path",
        "text",
        "start_line",
        "end_line",
        "sha256",
        "parent_document",
    }
    for record in records:
        assert set(record) == expected_fields
        assert record["source"] == "spark"
        assert record["version"] == "0.1.0"
        assert record["chunk_id"]
        assert record["text"]
        assert record["start_line"] >= 1
        assert record["end_line"] >= record["start_line"]

    keys = [(r["path"], r["start_line"]) for r in records]
    assert keys == sorted(keys)

    manifest = load_json(chunks_dir / "manifest.json")
    assert manifest["name"] == "spark"
    assert manifest["version"] == "0.1.0"
    assert manifest["bronze"] == {
        "name": "spark",
        "version": "0.1.0",
        "commit": load_json(store_dir / "bronze" / "spark" / "0.1.0" / "manifest.json")["commit"],
    }
    assert manifest["total_chunks"] == len(records)
    assert manifest["documents_chunked"] == 2
    assert manifest["chunk_size"] == 1000
    assert manifest["chunk_overlap"] == 150
    assert manifest["separators"] == ["\n\n", "\n", " ", ""]
    assert manifest["file_chunks"] == [
        {"path": "intro.md", "chunk_count": 1},
        {"path": "sql.md", "chunk_count": 1},
    ]
    assert manifest["generated_at"]
    assert manifest["chunks_sha256"] == hashlib.sha256((chunks_dir / "chunks.jsonl").read_bytes()).hexdigest()


def test_ingest_chunks_deterministic_across_runs(run_cli, sources_dir, tmp_path) -> None:
    store_a = tmp_path / "store-a"
    store_b = tmp_path / "store-b"
    args = ["ingest", "spark", "--tag", "v0.1.0", "--sources", str(sources_dir)]

    first = run_cli(args + ["--store", str(store_a)])
    assert first.returncode == 0, first.stderr
    second = run_cli(args + ["--store", str(store_b)])
    assert second.returncode == 0, second.stderr

    chunks_a = store_a / "silver" / "spark" / "0.1.0" / "chunks" / "chunks.jsonl"
    chunks_b = store_b / "silver" / "spark" / "0.1.0" / "chunks" / "chunks.jsonl"
    assert chunks_a.read_bytes() == chunks_b.read_bytes()


def test_ingest_chunks_idempotent_reingestion(run_cli, sources_dir, store_dir) -> None:
    args = ["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)]
    first = run_cli(args)
    assert first.returncode == 0, first.stderr

    chunks_jsonl = store_dir / "silver" / "spark" / "0.1.0" / "chunks" / "chunks.jsonl"
    before = chunks_jsonl.read_bytes()
    mtime_before = chunks_jsonl.stat().st_mtime_ns

    second = run_cli(args)
    assert second.returncode == 0, second.stderr
    assert "already present" in second.stdout
    assert chunks_jsonl.read_bytes() == before
    assert chunks_jsonl.stat().st_mtime_ns == mtime_before


# --- gold knowledge.db end-to-end ---


@skip_without_fts5
def test_ingest_writes_gold_db_structured(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    db_path = knowledge_db_path(store_dir)
    assert db_path.is_file()

    chunks_jsonl = store_dir / "silver" / "spark" / "0.1.0" / "chunks" / "chunks.jsonl"
    records = [json.loads(line) for line in chunks_jsonl.read_text(encoding="utf-8").splitlines() if line]
    assert records

    paths = sorted({r["path"] for r in records})
    with connect_db(db_path) as conn:
        assert conn.execute("SELECT schema_version FROM metadata WHERE id = 1").fetchone() == (SCHEMA_VERSION,)
        assert conn.execute("SELECT path FROM documents ORDER BY document_id").fetchall() == [(p,) for p in paths]
        assert conn.execute(
            "SELECT chunk_uuid, text, start_line, end_line, sha256 FROM chunks ORDER BY chunk_id"
        ).fetchall() == [(r["chunk_id"], r["text"], r["start_line"], r["end_line"], r["sha256"]) for r in records]
        expected_sha = hashlib.sha256(chunks_jsonl.read_bytes()).hexdigest()
        assert conn.execute(
            "SELECT source, version, chunks_sha256, document_count, chunk_count FROM indexed_sources"
        ).fetchall() == [("spark", "0.1.0", expected_sha, len(paths), len(records))]
        assert conn.execute("SELECT count(*) FROM fts_chunks WHERE fts_chunks MATCH 'spark'").fetchone() == (1,)


@skip_without_fts5
def test_ingest_gold_db_deterministic_across_runs(run_cli, sources_dir, tmp_path) -> None:
    store_a = tmp_path / "store-a"
    store_b = tmp_path / "store-b"
    args = ["ingest", "spark", "--tag", "v0.1.0", "--sources", str(sources_dir)]

    first = run_cli(args + ["--store", str(store_a)])
    assert first.returncode == 0, first.stderr
    second = run_cli(args + ["--store", str(store_b)])
    assert second.returncode == 0, second.stderr

    def dump(
        store: Path,
    ) -> tuple[
        list[tuple[object, ...]],
        list[tuple[object, ...]],
        list[tuple[object, ...]],
        list[tuple[object, ...]],
    ]:
        with connect_db(knowledge_db_path(store)) as conn:
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
                conn.execute("SELECT rowid FROM fts_chunks ORDER BY rowid").fetchall(),
            )

    assert dump(store_a) == dump(store_b)


@skip_without_fts5
def test_ingest_gold_db_idempotent_reingestion(run_cli, sources_dir, store_dir) -> None:
    args = ["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)]
    first = run_cli(args)
    assert first.returncode == 0, first.stderr

    db_path = knowledge_db_path(store_dir)
    before = db_path.read_bytes()
    mtime_before = db_path.stat().st_mtime_ns

    second = run_cli(args)
    assert second.returncode == 0, second.stderr
    assert "already present" in second.stdout
    assert db_path.read_bytes() == before
    assert db_path.stat().st_mtime_ns == mtime_before


@skip_without_fts5
def test_ingest_gold_db_skips_unchanged_slice_after_bronze_reacquire(run_cli, sources_dir, store_dir) -> None:
    args = ["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)]
    first = run_cli(args)
    assert first.returncode == 0, first.stderr

    bronze_slice = store_dir / "bronze" / "spark" / "0.1.0"
    shutil.rmtree(bronze_slice)

    db_path = knowledge_db_path(store_dir)
    before = db_path.read_bytes()
    mtime_before = db_path.stat().st_mtime_ns

    second = run_cli(args)
    assert second.returncode == 0, second.stderr
    assert "gold index up-to-date at v0.1.0" in second.stdout
    assert "spark gold index up-to-date at v0.1.0" not in second.stdout
    assert "acquired v0.1.0" in second.stdout
    assert db_path.read_bytes() == before
    assert db_path.stat().st_mtime_ns == mtime_before
