"""CLI-level tests for the kv tool. The CLI is the single testing seam."""

from __future__ import annotations

import json
from pathlib import Path


def load_json(path: Path) -> dict:
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
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
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
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    bronze_repo = store_dir / "bronze" / "spark" / "0.1.0" / "repo"
    assert (bronze_repo / "README.md").is_file()
    assert (bronze_repo / "docs" / "intro.md").is_file()


def test_ingest_silver_is_byte_identical(run_cli, sources_dir, store_dir, fixture_repo) -> None:
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    silver = store_dir / "silver" / "spark" / "0.1.0" / "docs"
    source_docs = fixture_repo / "docs"
    assert (silver / "intro.md").read_bytes() == (source_docs / "intro.md").read_bytes()
    assert (silver / "sql.md").read_bytes() == (source_docs / "sql.md").read_bytes()
    assert (silver / "img" / "logo.png").read_bytes() == (source_docs / "img" / "logo.png").read_bytes()


def test_ingest_writes_silver_manifests(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    silver = store_dir / "silver" / "spark" / "0.1.0"
    manifest = load_json(silver / "manifest.json")
    assert manifest["name"] == "spark"
    assert manifest["version"] == "0.1.0"
    assert manifest["file_count"] == 3
    assert manifest["files"] == ["img/logo.png", "intro.md", "sql.md"]

    lineage = load_json(silver / "lineage.json")
    assert lineage["silver"]["version"] == "0.1.0"
    assert lineage["bronze"]["commit"]


def test_ingest_is_idempotent(run_cli, sources_dir, store_dir) -> None:
    first = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert first.returncode == 0, first.stderr

    second = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert second.returncode == 0, second.stderr
    assert "already present" in second.stdout

    manifest = load_json(store_dir / "bronze" / "spark" / "0.1.0" / "manifest.json")
    assert manifest["commit"]


def test_list_shows_ingested_sources(run_cli, sources_dir, store_dir) -> None:
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0, result.stderr

    result = run_cli(["list", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode == 0
    assert "spark" in result.stdout
    assert "0.1.0" in result.stdout


def test_missing_tag_fails_clearly(run_cli, sources_dir, store_dir, repo_url, make_spark_yaml) -> None:
    make_spark_yaml(sources_dir / "spark.yaml", repo_url, "v9.9.9")
    result = run_cli(["ingest", "spark", "--store", str(store_dir), "--sources", str(sources_dir)])
    assert result.returncode != 0
    assert "v9.9.9" in result.stderr


def test_store_flag_beats_env_var(run_cli, sources_dir, tmp_path) -> None:
    env_store = tmp_path / "env-store"
    flag_store = tmp_path / "flag-store"
    result = run_cli(
        ["ingest", "spark", "--store", str(flag_store), "--sources", str(sources_dir)],
        env={"KV_STORE": str(env_store)},
    )
    assert result.returncode == 0, result.stderr
    assert (flag_store / "bronze" / "spark" / "0.1.0").is_dir()
    assert not (env_store / "bronze").exists()


def test_env_var_store_used_without_flag(run_cli, sources_dir, tmp_path) -> None:
    env_store = tmp_path / "env-store"
    result = run_cli(["ingest", "spark", "--sources", str(sources_dir)], env={"KV_STORE": str(env_store)})
    assert result.returncode == 0, result.stderr
    assert (env_store / "bronze" / "spark" / "0.1.0").is_dir()
