"""Shared fixtures for the kv CLI test suite."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from knowledge_vault.store import init_store


def run_git(cwd: Path, *args: str) -> None:
    """Run a git command in a directory, raising on failure."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """A local git repository with docs/ and image assets, tagged v0.1.0 and v0.2.0."""
    repo = tmp_path / "fixture-spark-repo"
    docs = repo / "docs"
    img = docs / "img"
    img.mkdir(parents=True)
    (docs / "intro.md").write_text("# Spark Intro\n\nIntroduction content.\n", encoding="utf-8")
    (docs / "sql.md").write_text("# SQL\n\n```sql\nSELECT 1;\n```\n", encoding="utf-8")
    (img / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes")
    (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")

    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")
    run_git(repo, "config", "uploadpack.allowFilter", "true")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "docs v0.1.0")
    run_git(repo, "tag", "v0.1.0")

    (docs / "streaming.md").write_text("# Streaming\n", encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "docs v0.2.0")
    run_git(repo, "tag", "v0.2.0")
    return repo


@pytest.fixture
def repo_url(fixture_repo: Path) -> str:
    """The file:// URL used in source configs to reach the fixture repo."""
    return f"file://{fixture_repo}"


def write_spark_yaml(path: Path, repo: str, tag: str) -> None:
    """Write a spark source config pointing at the given repo and tag."""
    path.write_text(f"name: spark\nrepo: {repo}\ndocs_path: docs\ndesired:\n  tag: {tag}\n", encoding="utf-8")


def write_multi_tag_yaml(path: Path, repo: str, tags: list[str]) -> None:
    """Write a source config with multiple desired tags."""
    tags_str = "\n".join(f"  - {t}" for t in tags)
    path.write_text(
        f"name: spark\nrepo: {repo}\ndocs_path: docs\ndesired:\n  tags:\n{tags_str}\n",
        encoding="utf-8",
    )


@pytest.fixture
def make_spark_yaml() -> Callable[[Path, str, str], None]:
    """Fixture exposing the helper that writes a spark source config."""
    return write_spark_yaml


@pytest.fixture
def make_multi_tag_yaml() -> Callable[[Path, str, list[str]], None]:
    """Fixture exposing the helper that writes a multi-tag source config."""
    return write_multi_tag_yaml


@pytest.fixture
def sources_dir(tmp_path: Path, repo_url: str) -> Path:
    """A temp sources dir with a default spark.yaml pointing at the fixture repo."""
    d = tmp_path / "sources"
    d.mkdir()
    write_multi_tag_yaml(d / "spark.yaml", repo_url, ["v0.1.0", "v0.2.0"])
    return d


@pytest.fixture
def store_initialized(store_dir: Path) -> Path:
    """A pre-initialized knowledge store."""
    init_store(store_dir)
    return store_dir


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    """A temp knowledge-store root."""
    return tmp_path / "store"


@pytest.fixture
def run_cli() -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run the kv CLI as a subprocess against a clean environment."""

    def _run(
        args: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        full_env = dict(os.environ)
        full_env.pop("KV_STORE", None)
        full_env.pop("KV_SOURCES", None)
        if env:
            full_env.update(env)
        return subprocess.run(
            [sys.executable, "-m", "knowledge_vault", *args],
            capture_output=True,
            text=True,
            env=full_env,
            cwd=cwd,
        )

    return _run
