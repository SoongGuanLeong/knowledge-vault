"""Ingest orchestration: acquisition into bronze, docs pipeline into silver."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_vault.config import SourceConfig, SourceError
from knowledge_vault.git import acquire, resolve_commit
from knowledge_vault.store import bronze_dir, silver_dir, version_from_tag


class IngestResult:
    """Outcome of ingesting one version."""

    def __init__(self, name: str, version: str, tag: str, status: str) -> None:
        self.name = name
        self.version = version
        self.tag = tag
        self.status = status


@dataclass
class IngestReport:
    """Aggregated result of ingesting all declared versions."""

    name: str
    created: list[str]
    skipped: list[str]
    failed: list[str]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ingest_single(config: SourceConfig, tag: str, store: Path) -> bool:
    """Ingest a single *tag* version of *config*. Returns True if created, False if skipped."""
    version = version_from_tag(tag)
    commit = resolve_commit(config.repo, tag)

    b_dir = bronze_dir(store, config.name, version)
    s_dir = silver_dir(store, config.name, version)

    manifest_path = b_dir / "manifest.json"
    if manifest_path.is_file() and _read_json(manifest_path).get("commit") == commit:
        print(f"{config.name} already present at {tag} ({commit})")
        return False

    repo_dir = b_dir / "repo"
    b_dir.mkdir(parents=True, exist_ok=True)
    acquire(config.repo, tag, commit, repo_dir)

    _write_json(
        manifest_path,
        {
            "name": config.name,
            "repo": config.repo,
            "requested_tag": tag,
            "resolved_tag": tag,
            "commit": commit,
            "retrieved_at": _now_iso(),
            "docs_path": config.docs_path,
        },
    )

    _copy_docs(config, repo_dir, s_dir, version, commit)
    print(f"{config.name} ingested {tag} ({commit})")
    return True


def ingest(config: SourceConfig, store: Path, tag_override: str | None = None) -> IngestReport:
    """Run the full ingest pipeline for *config* into *store*.

    Ingests every tag in ``config.desired_tags`` unless *tag_override* is given,
    in which case only that single tag is ingested.

    Parameters
    ----------
    config : SourceConfig
        The source to ingest.
    store : Path
        Knowledge-store root.
    tag_override : str | None
        If provided, ingest only this tag instead of all declared tags.

    Returns
    -------
    IngestReport
        Summary of created, skipped, and failed versions.
    """
    tags = [tag_override] if tag_override is not None else list(config.desired_tags)
    report = IngestReport(name=config.name, created=[], skipped=[], failed=[])

    for tag in tags:
        try:
            created = _ingest_single(config, tag, store)
        except Exception as exc:
            report.failed.append(f"{tag}: {exc}")
            print(f"error: {config.name} at {tag}: {exc}", file=sys.stderr)
        else:
            if created:
                report.created.append(version_from_tag(tag))
            else:
                report.skipped.append(version_from_tag(tag))

    return report


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
