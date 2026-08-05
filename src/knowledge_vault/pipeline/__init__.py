"""Pipeline package: stage-based ingestion with stable boundaries."""

from __future__ import annotations

from knowledge_vault.pipeline.acquire import AcquireStage
from knowledge_vault.pipeline.chunk import ChunkStage
from knowledge_vault.pipeline.context import PipelineContext
from knowledge_vault.pipeline.index import IndexStage
from knowledge_vault.pipeline.silver import SilverStage

__all__ = ["AcquireStage", "ChunkStage", "IndexStage", "PipelineContext", "SilverStage"]
