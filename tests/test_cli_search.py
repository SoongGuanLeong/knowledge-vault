"""E2E tests for `kv search` (ticket #34).

The CLI is the seam: ingest a fixture source into a temp store, then run
`kv search` as a subprocess and assert on exit codes, output blocks, filters,
and error handling per the frozen CLI contract (#27).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from conftest import fts5_available

skip_without_fts5 = pytest.mark.skipif(not fts5_available(), reason="FTS5 not available in this SQLite build")


def _ingest_all(run_cli, store_dir: Path, sources_dir: Path) -> None:
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr


def _search(run_cli, store_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_cli(["search", "--store", str(store_dir), *args])


def test_search_help_lists_query_and_flags(run_cli) -> None:
    result = run_cli(["search", "--help"])
    assert result.returncode == 0
    assert "query" in result.stdout
    for flag in ("--source", "--version", "--limit"):
        assert flag in result.stdout


def test_search_without_query_is_error(run_cli, store_dir) -> None:
    result = run_cli(["search", "--store", str(store_dir)])
    assert result.returncode == 2
    assert "query" in result.stderr.lower()


def test_search_missing_db_is_error(run_cli, store_dir, sources_dir) -> None:
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 2
    assert "gold index not found" in result.stderr


@skip_without_fts5
def test_search_corrupt_db_is_error(run_cli, store_dir, sources_dir) -> None:
    gold = store_dir / "gold"
    gold.mkdir(parents=True)
    (gold / "knowledge.db").write_bytes(b"not a sqlite database")
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 2
    assert "search failed" in result.stderr


@skip_without_fts5
def test_search_incompatible_schema_is_error(run_cli, store_dir, sources_dir) -> None:
    from knowledge_vault.retrieval import SCHEMA_VERSION, connect_db, create_schema

    gold = store_dir / "gold"
    gold.mkdir(parents=True)
    conn = connect_db(gold / "knowledge.db")
    create_schema(conn)
    conn.execute("UPDATE metadata SET schema_version = ? WHERE id = 1", (SCHEMA_VERSION + 1,))
    conn.commit()
    conn.close()
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 2
    assert "search failed" in result.stderr


@skip_without_fts5
def test_search_limit_zero_is_error(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark", "--limit", "0")
    assert result.returncode == 2
    assert "--limit" in result.stderr


@skip_without_fts5
def test_search_returns_ranked_blocks(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 0, result.stderr

    lines = result.stdout.strip().splitlines()
    assert lines[0].startswith("1. spark@0.1.0")
    assert "intro.md" in lines[0]
    assert re.search(r":\d+-\d+$", lines[0].split("  ")[-1])


@skip_without_fts5
def test_search_no_results_exit_1(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "zzznotpresent")
    assert result.returncode == 1
    assert result.stdout.strip() == ""


@skip_without_fts5
def test_search_unknown_source_is_error(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark", "--source", "nosuch")
    assert result.returncode == 2
    assert "source" in result.stderr.lower()
    assert "nosuch" in result.stderr


@skip_without_fts5
def test_search_unknown_version_is_error(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark", "--version", "9.9.9")
    assert result.returncode == 2
    assert "version" in result.stderr.lower()
    assert "9.9.9" in result.stderr


@skip_without_fts5
def test_search_source_filter_restricts(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    filtered = _search(run_cli, store_dir, "spark", "--source", "spark")
    assert filtered.returncode == 0, filtered.stderr
    assert "spark@0.1.0" in filtered.stdout


@skip_without_fts5
def test_search_version_filter_restricts(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    filtered = _search(run_cli, store_dir, "spark", "--version", "0.1.0")
    assert filtered.returncode == 0, filtered.stderr
    assert "spark@0.1.0" in filtered.stdout
    assert "spark@0.2.0" not in filtered.stdout


@skip_without_fts5
def test_search_span_all_sources_and_versions_by_default(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 0, result.stderr
    assert "spark@0.1.0" in result.stdout
    assert "spark@0.2.0" in result.stdout


@skip_without_fts5
def test_search_limit_restricts_result_count(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    unlimited = _search(run_cli, store_dir, "spark")
    limited = _search(run_cli, store_dir, "spark", "--limit", "1")
    assert unlimited.returncode == 0, unlimited.stderr
    assert limited.returncode == 0, limited.stderr
    assert len(unlimited.stdout.strip().splitlines()) > len(limited.stdout.strip().splitlines())
    assert len(limited.stdout.strip().splitlines()) == 2  # rank line + snippet line


@skip_without_fts5
def test_search_output_has_no_score(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 0, result.stderr
    assert "score" not in result.stdout.lower()


@skip_without_fts5
def test_search_snippet_includes_query_term(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    snippet_line = lines[1]
    assert snippet_line.startswith("   ")
    assert "Spark" in snippet_line or "spark" in snippet_line


@skip_without_fts5
def test_search_does_not_emit_ansi_when_captured(run_cli, store_dir, sources_dir) -> None:
    _ingest_all(run_cli, store_dir, sources_dir)
    result = _search(run_cli, store_dir, "spark")
    assert result.returncode == 0, result.stderr
    assert "\x1b[" not in result.stdout
