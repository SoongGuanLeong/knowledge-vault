"""Pipeline context: immutable carrier passed between stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledge_vault.config import SourceConfig


@dataclass(frozen=True)
class PipelineContext:
    """Immutable context shared across pipeline stages.

    Attributes
    ----------
    store : Path
        Knowledge-store root directory.
    config : SourceConfig
        The source being ingested.
    tag : str
        The tag being processed in this pipeline run.
    version : str
        Version key derived from *tag* (leading 'v' stripped).
    commit : str
        Resolved commit SHA for *tag*.
    bronze_path : Path
        Computed bronze directory for this source+version.
    silver_path : Path
        Computed silver directory for this source+version.
    chunks_path : Path
        Computed chunks.jsonl artifact path produced by ChunkStage.
    repo_dir : Path
        Computed repository checkout path within bronze.
    manifest_path : Path
        Computed manifest.json path within bronze.
    """

    store: Path
    config: SourceConfig
    tag: str
    version: str
    commit: str
    bronze_path: Path
    silver_path: Path
    chunks_path: Path
    repo_dir: Path
    manifest_path: Path
