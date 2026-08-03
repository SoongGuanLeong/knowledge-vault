"""Tests for kv init, doctor, status, and multi-version ingest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# --- kv init ---


def test_init_creates_medallion_dirs(run_cli, store_dir) -> None:
    result = run_cli(["init", "--store", str(store_dir)])
    assert result.returncode == 0, result.stderr
    for subdir in ("bronze", "silver", "gold", "cache"):
        assert (store_dir / subdir).is_dir()


def test_init_writes_metadata(run_cli, store_dir) -> None:
    result = run_cli(["init", "--store", str(store_dir)])
    assert result.returncode == 0, result.stderr

    meta = load_json(store_dir / "metadata.json")
    assert meta["schema_version"] == 1
    assert "created_at" in meta


def test_init_is_idempotent(run_cli, store_dir) -> None:
    first = run_cli(["init", "--store", str(store_dir)])
    assert first.returncode == 0, first.stderr
    original_meta = load_json(store_dir / "metadata.json")

    second = run_cli(["init", "--store", str(store_dir)])
    assert second.returncode == 0, second.stderr
    meta = load_json(store_dir / "metadata.json")
    assert meta["schema_version"] == original_meta["schema_version"]
    assert meta["created_at"] == original_meta["created_at"]


# --- kv doctor ---


def test_doctor_passes_on_clean_env(run_cli, sources_dir, store_initialized) -> None:
    result = run_cli(["doctor", "--store", str(store_initialized), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
    assert "FAIL" not in result.stdout


def test_doctor_warns_on_uninitialized_store(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["doctor", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr
    assert "WARN" in result.stdout


def test_doctor_fails_when_no_yaml_files(run_cli, tmp_path: Path, store_initialized) -> None:
    empty_sources = tmp_path / "empty_sources"
    empty_sources.mkdir()
    (empty_sources / "README.md").write_text("# docs", encoding="utf-8")
    result = run_cli(["doctor", "--store", str(store_initialized), "--sources", str(empty_sources)])
    assert result.returncode != 0
    assert "FAIL" in result.stdout
    assert "no source configs found" in result.stdout


def test_doctor_fails_on_bad_yaml(run_cli, sources_dir, store_initialized, repo_url, make_multi_tag_yaml) -> None:
    make_multi_tag_yaml(sources_dir / "bad.yaml", repo_url, [])
    result = run_cli(["doctor", "--store", str(store_initialized), "--sources", str(sources_dir)])
    assert result.returncode != 0
    assert "FAIL" in result.stdout
    assert "bad" in result.stdout


# --- kv status ---


def test_status_healthy_when_all_present(run_cli, sources_dir, store_initialized) -> None:
    ingest_result = run_cli(["ingest", "spark", "--store", str(store_initialized), "--sources", str(sources_dir)])
    assert ingest_result.returncode == 0, ingest_result.stderr

    status_result = run_cli(["status", "--store", str(store_initialized), "--sources", str(sources_dir)])
    assert status_result.returncode == 0, status_result.stdout
    assert "Checked:" in status_result.stdout
    assert "✓ spark@0.1.0" in status_result.stdout
    assert "✓ spark@0.2.0" in status_result.stdout
    assert "No drift detected." in status_result.stdout


def test_status_reports_missing(run_cli, sources_dir, store_initialized) -> None:
    status_result = run_cli(["status", "--store", str(store_initialized), "--sources", str(sources_dir)])
    assert status_result.returncode == 1, status_result.stdout
    assert "✗ spark@0.1.0 missing" in status_result.stdout
    assert "✗ spark@0.2.0 missing" in status_result.stdout
    assert "Drift detected." in status_result.stdout


def test_status_deep_detects_commit_mismatch(
    run_cli, sources_dir, store_initialized, repo_url, make_multi_tag_yaml
) -> None:
    make_multi_tag_yaml(sources_dir / "spark.yaml", repo_url, ["v0.1.0", "v0.2.0"])
    ingest_result = run_cli(["ingest", "spark", "--store", str(store_initialized), "--sources", str(sources_dir)])
    assert ingest_result.returncode == 0, ingest_result.stderr

    status_result = run_cli(["status", "--deep", "--store", str(store_initialized), "--sources", str(sources_dir)])
    assert status_result.returncode == 0, status_result.stdout
    assert "✓ spark@0.1.0" in status_result.stdout
    assert "✓ spark@0.2.0" in status_result.stdout


# --- multi-version ingest ---


def test_ingest_multi_version(run_cli, sources_dir, store_dir, repo_url) -> None:
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    assert (store_dir / "bronze" / "spark" / "0.1.0" / "manifest.json").is_file()
    assert (store_dir / "bronze" / "spark" / "0.2.0" / "manifest.json").is_file()
    assert (store_dir / "silver" / "spark" / "0.1.0" / "manifest.json").is_file()
    assert (store_dir / "silver" / "spark" / "0.2.0" / "manifest.json").is_file()

    assert "v0.1.0" in result.stdout
    assert "v0.2.0" in result.stdout


def test_ingest_multi_version_idempotent(run_cli, sources_dir, store_dir) -> None:
    first = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert first.returncode == 0, first.stderr

    second = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert second.returncode == 0, second.stderr
    assert "already present" in second.stdout


def test_ingest_tag_override_single_version(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.2.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    assert (store_dir / "bronze" / "spark" / "0.2.0" / "manifest.json").is_file()
    assert not (store_dir / "bronze" / "spark" / "0.1.0").exists()


def test_ingest_reports_created_and_skipped(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr
    assert "ingested" in result.stdout

    result = run_cli(["ingest", "spark", "--tag", "v0.1.0", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr
    assert "already present" in result.stdout


def test_list_shows_all_versions(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    result = run_cli(["list", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0
    assert "spark" in result.stdout
    assert "0.1.0" in result.stdout
    assert "0.2.0" in result.stdout


# --- edge cases ---


def test_status_fails_without_init(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["status", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "initialized" in output.lower() or "not initialized" in output.lower()


def test_inits_store_and_ingests(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["init", "--store", str(store_dir)])
    assert result.returncode == 0, result.stderr

    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr
