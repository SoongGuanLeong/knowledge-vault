"""Ingest orchestration: acquisition into bronze, docs pipeline into silver."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from knowledge_vault.config import SourceConfig, SourceError
from knowledge_vault.git import acquire, resolve_commit
from knowledge_vault.store import bronze_dir, silver_dir, version_from_tag


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def ingest(config: SourceConfig, store: Path) -> None:
    """Run the full ingest pipeline for *config* into *store*.

    Acquires the pinned snapshot into bronze, then copies the configured
    docs into silver, writing provenance manifests at both layers.

    Parameters
    ----------
    config : SourceConfig
        The source to ingest.
    store : Path
        Knowledge-store root.
    """
    version = version_from_tag(config.desired_tag)
    commit = resolve_commit(config.repo, config.desired_tag)

    b_dir = bronze_dir(store, config.name, version)
    s_dir = silver_dir(store, config.name, version)

    manifest_path = b_dir / "manifest.json"
    if manifest_path.is_file() and _read_json(manifest_path).get("commit") == commit:
        print(f"{config.name} already present at {config.desired_tag} ({commit})")
        return

    repo_dir = b_dir / "repo"
    b_dir.mkdir(parents=True, exist_ok=True)
    acquire(config.repo, config.desired_tag, commit, repo_dir)

    _write_json(
        manifest_path,
        {
            "name": config.name,
            "repo": config.repo,
            "requested_tag": config.desired_tag,
            "resolved_tag": config.desired_tag,
            "commit": commit,
            "retrieved_at": _now_iso(),
            "docs_path": config.docs_path,
        },
    )

    _copy_docs(config, repo_dir, s_dir, version, commit)


def _copy_docs(config: SourceConfig, repo_dir: Path, s_dir: Path, version: str, commit: str) -> None:
    src = repo_dir / config.docs_path
    if not src.is_dir():
        raise SourceError(f"docs_path {config.docs_path!r} not found in snapshot of {config.name}")
    dest = s_dir / "docs"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    files = sorted(str(f.relative_to(dest)) for f in dest.rglob("*") if f.is_file())

    _write_json(
        s_dir / "manifest.json",
        {
            "name": config.name,
            "version": version,
            "bronze": {"name": config.name, "version": version, "commit": commit},
            "file_count": len(files),
            "files": files,
            "extracted_at": _now_iso(),
        },
    )
    _write_json(
        s_dir / "lineage.json",
        {
            "silver": {"name": config.name, "version": version},
            "bronze": {"name": config.name, "version": version, "commit": commit},
        },
    )
