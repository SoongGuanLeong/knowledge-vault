"""Failure-path tests for the kv CLI (ticket #51).

The 6 deterministic, user-triggerable failure branches not yet exercised by
the E2E suite, all via the `run_cli` subprocess seam. Environment/infra
branches (doctor git-not-found, partial-clone unsupported, doctor
remote-unreachable, store-unwritable, the ``__main__`` guard) stay
documented-not-tested per ADR-0005.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import fts5_available

skip_without_fts5 = pytest.mark.skipif(not fts5_available(), reason="FTS5 not available in this SQLite build")


def _ingest_spark(run_cli, store_dir: Path, sources_dir: Path, *, tag: str | None = None) -> None:
    args = ["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)]
    if tag:
        args += ["--tag", tag]
    result = run_cli(args)
    assert result.returncode == 0, result.stderr


def test_list_skips_version_dir_without_manifest(run_cli, store_dir) -> None:
    version_dir = store_dir / "bronze" / "emptysource" / "0.1.0"
    version_dir.mkdir(parents=True)

    result = run_cli(["list", "--store", str(store_dir)])

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_status_bad_source_config_reports_error_and_drift(run_cli, tmp_path: Path, store_initialized) -> None:
    bad_sources = tmp_path / "bad_sources"
    bad_sources.mkdir()
    (bad_sources / "spark.yaml").write_text("name: spark\nrepo: /nonexistent\n", encoding="utf-8")

    result = run_cli(["status", "--store", str(store_initialized), "--sources", str(bad_sources)])

    assert result.returncode == 1
    assert "error: invalid source config" in result.stderr
    assert "spark.yaml" in result.stderr
    assert "Drift detected." in result.stdout


def test_status_reports_stale_not_declared(
    run_cli, sources_dir, store_initialized, make_multi_tag_yaml, repo_url
) -> None:
    _ingest_spark(run_cli, store_initialized, sources_dir)
    make_multi_tag_yaml(sources_dir / "spark.yaml", repo_url, ["v0.2.0"])

    result = run_cli(["status", "--store", str(store_initialized), "--sources", str(sources_dir)])

    assert result.returncode == 1
    assert "~ spark@0.1.0 stale (in store but not declared)" in result.stdout
    assert "Drift detected." in result.stdout


def test_status_deep_reports_stale_when_remote_commit_unresolvable(
    run_cli, sources_dir, store_initialized, fixture_repo
) -> None:
    _ingest_spark(run_cli, store_initialized, sources_dir, tag="v0.1.0")
    shutil.rmtree(fixture_repo)

    result = run_cli(["status", "--deep", "--store", str(store_initialized), "--sources", str(sources_dir)])

    assert result.returncode == 1
    assert "✗ spark@0.1.0 stale (remote commit mismatch)" in result.stdout
    assert "Drift detected." in result.stdout


@skip_without_fts5
def test_search_blank_query_is_error(run_cli, sources_dir, store_dir) -> None:
    _ingest_spark(run_cli, store_dir, sources_dir)

    result = run_cli(["search", "--store", str(store_dir), ""])

    assert result.returncode == 2
    assert "error: query must be a non-blank string" in result.stderr


def test_doctor_uninitialized_store_reports_schema_warn(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["doctor", "--store", str(store_dir), "--sources", str(sources_dir)])

    assert result.returncode == 0
    assert "WARN: store schema compat" in result.stdout
    assert "store not initialized (run 'kv init')" in result.stdout
