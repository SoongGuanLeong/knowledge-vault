"""Index stage: deterministic gold-layer retrieval contract from chunks.jsonl."""

from __future__ import annotations

import hashlib
import json

from knowledge_vault.pipeline._io import write_json
from knowledge_vault.pipeline.chunk import ChunkRecord
from knowledge_vault.pipeline.context import PipelineContext

INDEX_SCHEMA_VERSION = 1


class IndexStage:
    """Build the gold index ``index/metadata.json`` from ``chunks.jsonl``.

    Deterministic: given identical ``chunks.jsonl`` input, output is
    byte-identical (no timestamp inside). Idempotent: skips when an existing
    index's ``chunks_sha256`` matches the current chunks artifact; rebuilds
    otherwise.

    Consumes only ``chunks.jsonl``. Missing chunks artifact raises
    :class:`FileNotFoundError` — no silent skip, no auto-creation.
    """

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Run indexing for *ctx*'s chunks artifact.

        Parameters
        ----------
        ctx : PipelineContext
            Immutable pipeline context carrying chunks_path, gold_path.

        Returns
        -------
        PipelineContext
            The same context (indexing does not modify context).
        """
        chunks_jsonl = ctx.chunks_path
        metadata_json = ctx.gold_path / "index" / "metadata.json"

        if not chunks_jsonl.is_file():
            raise FileNotFoundError(f"missing {chunks_jsonl}; Run ChunkStage before IndexStage.")

        chunks_sha256 = hashlib.sha256(chunks_jsonl.read_bytes()).hexdigest()

        if metadata_json.is_file():
            existing: dict[str, object]
            try:
                existing = json.loads(metadata_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
            if existing.get("chunks_sha256") == chunks_sha256:
                print(f"{ctx.config.name} gold index up-to-date at v{ctx.version}")
                return ctx

        records: list[ChunkRecord] = []
        content = chunks_jsonl.read_text(encoding="utf-8")
        if content:
            records = [json.loads(line) for line in content.splitlines()]

        chunks: dict[str, dict[str, str | int]] = {}
        for record in records:
            chunk_id = record["chunk_id"]
            chunks[chunk_id] = {
                "path": record["path"],
                "start_line": record["start_line"],
                "end_line": record["end_line"],
                "parent_document": record["parent_document"],
                "sha256": record["sha256"],
            }

        write_json(
            metadata_json,
            {
                "schema_version": INDEX_SCHEMA_VERSION,
                "chunks_sha256": chunks_sha256,
                "chunk_count": len(records),
                "chunks": chunks,
            },
        )

        print(f"{ctx.config.name} indexed v{ctx.version}: {len(records)} chunks -> {metadata_json}")
        return ctx
