"""Ingest orchestration: acquisition into bronze, docs pipeline into silver."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from knowledge_vault.config import SourceConfig
from knowledge_vault.git import resolve_commit
from knowledge_vault.pipeline import AcquireStage, ChunkStage, PipelineContext, SilverStage
from knowledge_vault.retrieval.indexing import IndexStage
from knowledge_vault.store import bronze_dir, silver_dir, version_from_tag


@dataclass
class IngestReport:
    """Aggregated result of ingesting all declared versions.

    Attributes
    ---------
    name : str
        Source name.
    created : list[str]
        Versions that were newly acquired.
    skipped : list[str]
        Versions that were already present (idempotent no-op).
    failed : list[str]
        Versions that failed, with error details.
    """

    name: str
    created: list[str]
    skipped: list[str]
    failed: list[str]


def _build_context(config: SourceConfig, tag: str, store: Path) -> PipelineContext:
    """Construct the immutable PipelineContext for a single tag."""
    version = version_from_tag(tag)
    commit = resolve_commit(config.repo, tag)
    b_dir = bronze_dir(store, config.name, version)
    return PipelineContext(
        store=store,
        config=config,
        tag=tag,
        version=version,
        commit=commit,
        bronze_path=b_dir,
        silver_path=silver_dir(store, config.name, version),
        chunks_path=silver_dir(store, config.name, version) / "chunks" / "chunks.jsonl",
        repo_dir=b_dir / "repo",
        manifest_path=b_dir / "manifest.json",
    )


def _ingest_single(
    config: SourceConfig,
    tag: str,
    store: Path,
    acquire_stage: AcquireStage,
    silver_stage: SilverStage,
    chunk_stage: ChunkStage,
    index_stage: IndexStage,
) -> bool:
    """Ingest a single *tag* version of *config*. Returns True if created, False if skipped."""
    ctx = _build_context(config, tag, store)

    created = acquire_stage.execute(ctx)
    if not created:
        return False

    silver_stage.execute(ctx)
    chunk_stage.execute(ctx)
    index_stage.execute(ctx)
    print(f"{config.name} ingested {tag} ({ctx.commit})")
    return True


def ingest(config: SourceConfig, store: Path, tag_override: str | None = None) -> IngestReport:
    """Run the full pipeline for *config* into *store*.

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

    acquire_stage = AcquireStage()
    silver_stage = SilverStage()
    chunk_stage = ChunkStage()
    index_stage = IndexStage()

    for tag in tags:
        try:
            created = _ingest_single(config, tag, store, acquire_stage, silver_stage, chunk_stage, index_stage)
        except Exception as exc:
            report.failed.append(f"{tag}: {exc}")
            print(f"error: {config.name} at {tag}: {exc}", file=sys.stderr)
        else:
            if created:
                report.created.append(version_from_tag(tag))
            else:
                report.skipped.append(version_from_tag(tag))

    return report
