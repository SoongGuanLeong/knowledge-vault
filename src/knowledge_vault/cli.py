"""Command-line interface for the kv knowledge ingestion tool."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from knowledge_vault import __version__
from knowledge_vault.config import SourceError, load_source
from knowledge_vault.git import GitError, list_tags
from knowledge_vault.ingest import ingest
from knowledge_vault.store import default_sources_dir, default_store


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the kv CLI.

    Returns
    -------
    argparse.ArgumentParser
        The configured parser.
    """
    parser = argparse.ArgumentParser(prog="kv", description="Reproducible knowledge ingestion.")
    parser.add_argument("--version", action="version", version=f"kv {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--store", help="knowledge-store root directory")
    common.add_argument("--sources", help="sources configuration directory")

    discover = subparsers.add_parser("discover", parents=[common], help="list available versions of a source")
    discover.add_argument("name", help="source name (e.g. spark)")
    discover.set_defaults(func=_cmd_discover)

    ingest_parser = subparsers.add_parser("ingest", parents=[common], help="ingest a pinned source snapshot")
    ingest_parser.add_argument("name", help="source name (e.g. spark)")
    ingest_parser.set_defaults(func=_cmd_ingest)

    list_parser = subparsers.add_parser("list", parents=[common], help="list ingested sources and versions")
    list_parser.set_defaults(func=_cmd_list)

    return parser


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    store = Path(args.store) if args.store else Path(os.environ.get("KV_STORE", str(default_store())))
    sources = Path(args.sources) if args.sources else Path(os.environ.get("KV_SOURCES", str(default_sources_dir())))
    return store, sources


def _cmd_discover(args: argparse.Namespace) -> None:
    _, sources = _resolve_paths(args)
    config = load_source(sources, args.name)
    for tag in list_tags(config.repo):
        print(tag)


def _cmd_ingest(args: argparse.Namespace) -> None:
    store, sources = _resolve_paths(args)
    config = load_source(sources, args.name)
    ingest(config, store)


def _cmd_list(args: argparse.Namespace) -> None:
    store, _ = _resolve_paths(args)
    for name_dir in sorted((store / "bronze").glob("*/")):
        for version_dir in sorted(name_dir.glob("*")):
            if (version_dir / "manifest.json").is_file():
                print(f"{name_dir.name} {version_dir.name}")


def main() -> int:
    """Entry point for the kv CLI.

    Returns
    -------
    int
        Process exit code.
    """
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (SourceError, GitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
