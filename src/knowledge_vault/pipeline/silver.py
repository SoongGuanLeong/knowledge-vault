"""Silver stage: extract documentation artifacts from bronze into silver."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from knowledge_vault.config import SourceError
from knowledge_vault.pipeline._io import write_json
from knowledge_vault.pipeline.context import PipelineContext

DOC_EXTENSIONS: list[str] = [".md", ".mdx", ".rst", ".txt", ".adoc", ".html"]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _is_binary(path: Path) -> bool:
    """Detect binary files by checking for null bytes in the first 8 KiB."""
    chunk_size = 8192
    with path.open("rb") as f:
        chunk = f.read(chunk_size)
    return b"\x00" in chunk


def _discover_documents(src: Path) -> tuple[list[Path], list[Path]]:
    """Separate doc-extension files from binary files under *src*.

    Returns
    -------
    tuple[list[Path], list[Path]]
        (doc_files, binary_files) — both lists relative to *src*.
    """
    doc_files: list[Path] = []
    binary_files: list[Path] = []
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        if f.suffix.lower() in DOC_EXTENSIONS:
            if _is_binary(f):
                binary_files.append(rel)
            else:
                doc_files.append(rel)
        else:
            binary_files.append(rel)
    return doc_files, binary_files


class SilverStage:
    """Extract documentation from a bronze snapshot into the silver layer.

    Selective extraction: only files with documentation extensions are copied
    into silver, with checksums and an inventory of skipped files recorded.
    Bronze remains the source of truth — no data is permanently lost.
    """

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Extract documentation files from bronze into silver.

        Parameters
        ----------
        ctx : PipelineContext
            Immutable pipeline context.

        Returns
        -------
        PipelineContext
            The same context (silver extraction does not modify context).
        """
        src = ctx.repo_dir / ctx.config.docs_path
        if not src.is_dir():
            raise SourceError(f"docs_path {ctx.config.docs_path!r} not found in snapshot of {ctx.config.name}")

        dest = ctx.silver_path / "docs"
        if dest.exists():
            shutil.rmtree(dest)

        doc_files, skipped_files = _discover_documents(src)
        included: list[dict[str, str]] = []
        for rel in doc_files:
            dest_file = dest / rel
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, dest_file)
            included.append(
                {
                    "source": str(rel),
                    "destination": str(rel),
                    "checksum": _checksum(src / rel),
                }
            )

        skipped: list[dict[str, str]] = []
        for rel in skipped_files:
            skipped.append({"source": str(rel), "reason": "binary_or_non_doc"})

        write_json(
            ctx.silver_path / "manifest.json",
            {
                "name": ctx.config.name,
                "version": ctx.version,
                "bronze": {"name": ctx.config.name, "version": ctx.version, "commit": ctx.commit},
                "file_count": len(included),
                "files": [entry["source"] for entry in included],
                "extraction_patterns": DOC_EXTENSIONS,
                "extraction_inventory": {
                    "included": included,
                    "skipped": skipped,
                    "total_files_discovered": len(included) + len(skipped),
                },
                "extracted_at": _now_iso(),
            },
        )
        write_json(
            ctx.silver_path / "lineage.json",
            {
                "silver": {"name": ctx.config.name, "version": ctx.version},
                "bronze": {"name": ctx.config.name, "version": ctx.version, "commit": ctx.commit},
            },
        )
        return ctx
