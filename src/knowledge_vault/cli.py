"""Command-line interface for the kv knowledge ingestion tool."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from knowledge_vault import __version__
from knowledge_vault.config import SourceError, iter_source_names, load_source
from knowledge_vault.git import (
    GitError,
    git_version_tuple,
    list_tags,
    remote_commit_resolves,
    remote_reachable,
    supports_partial_clone,
)
from knowledge_vault.ingest import ingest
from knowledge_vault.retrieval import (
    SearchBackendError,
    SearchFilters,
    SQLiteFTSBackend,
    knowledge_db_path,
)
from knowledge_vault.snippet import extract_terms, make_snippet
from knowledge_vault.store import (
    StoreError,
    default_sources_dir,
    default_store,
    init_store,
    read_store_metadata,
    version_from_tag,
)


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

    ingest_parser = subparsers.add_parser("ingest", parents=[common], help="ingest pinned source snapshots")
    ingest_parser.add_argument("name", help="source name (e.g. spark)")
    ingest_parser.add_argument("--tag", help="ingest only this tag instead of all declared tags")
    ingest_parser.set_defaults(func=_cmd_ingest)

    list_parser = subparsers.add_parser("list", parents=[common], help="list ingested sources and versions")
    list_parser.set_defaults(func=_cmd_list)

    init_parser = subparsers.add_parser("init", parents=[common], help="initialize a knowledge store")
    init_parser.set_defaults(func=_cmd_init)

    status_parser = subparsers.add_parser("status", parents=[common], help="audit store against configs")
    status_parser.add_argument("--deep", action="store_true", help="verify remote commits still resolve")
    status_parser.set_defaults(func=_cmd_status)

    doctor_parser = subparsers.add_parser("doctor", parents=[common], help="pre-flight environment checks")
    doctor_parser.set_defaults(func=_cmd_doctor)

    search_parser = subparsers.add_parser("search", help="full-text search over indexed chunks")
    search_parser.add_argument("--store", help="knowledge-store root directory")
    search_parser.add_argument("query", help="FTS5 query string (e.g. 'spark', 'spark AND sql', 'stream*')")
    search_parser.add_argument("--source", help="restrict search to a source")
    search_parser.add_argument("--version", help="restrict search to a version (independent of --source)")
    search_parser.add_argument("--limit", type=int, default=10, help="maximum number of results (default 10)")
    search_parser.set_defaults(func=_cmd_search)

    return parser


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    store = Path(args.store) if args.store else Path(os.environ.get("KV_STORE", str(default_store())))
    sources = Path(args.sources) if args.sources else Path(os.environ.get("KV_SOURCES", str(default_sources_dir())))
    return store, sources


def _cmd_init(args: argparse.Namespace) -> None:
    store, _ = _resolve_paths(args)
    init_store(store)
    print(f"initialized store at {store}")
    meta = read_store_metadata(store)
    print(f"  schema_version: {meta['schema_version']}")
    print(f"  created_at: {meta['created_at']}")


def _cmd_discover(args: argparse.Namespace) -> None:
    _, sources = _resolve_paths(args)
    config = load_source(sources, args.name)
    for tag in list_tags(config.repo):
        print(tag)


def _cmd_ingest(args: argparse.Namespace) -> int:
    store, sources = _resolve_paths(args)
    config = load_source(sources, args.name)
    report = ingest(config, store, tag_override=args.tag)
    if report.failed:
        return 1
    return 0


def _cmd_list(args: argparse.Namespace) -> None:
    store, _ = _resolve_paths(args)
    bronze = store / "bronze"
    if not bronze.is_dir():
        return
    for name_dir in sorted(bronze.glob("*/"), key=lambda p: p.name):
        versions = sorted(d.name for d in name_dir.glob("*") if (d / "manifest.json").is_file())
        if not versions:
            continue
        print(name_dir.name)
        for v in versions:
            print(f"  {v}")


def _cmd_status(args: argparse.Namespace) -> int:
    store, sources = _resolve_paths(args)
    try:
        metadata = read_store_metadata(store)
    except StoreError:
        print(f"error: store at {store} is not initialized (run 'kv init')", file=sys.stderr)
        return 1

    schema_version = metadata.get("schema_version", 0)
    print(f"Store schema: {schema_version}")
    print("Checked:")

    drift = False
    declared_versions: set[tuple[str, str]] = set()
    store_versions: set[tuple[str, str]] = set()

    for name in iter_source_names(sources):
        try:
            config = load_source(sources, name)
        except SourceError as exc:
            print(f"error: {exc}", file=sys.stderr)
            drift = True
            continue
        for tag in config.desired_tags:
            version = version_from_tag(tag)
            declared_versions.add((name, version))
            manifest_path = store / "bronze" / name / version / "manifest.json"
            if not manifest_path.is_file():
                print(f"  ✗ {name}@{version} missing")
                drift = True
            else:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                store_versions.add((name, version))
                if args.deep:
                    commit = manifest.get("commit", "")
                    requested_tag = manifest.get("requested_tag", tag)
                    if not remote_commit_resolves(config.repo, requested_tag, commit):
                        print(f"  ✗ {name}@{version} stale (remote commit mismatch)")
                        drift = True
                    else:
                        print(f"  ✓ {name}@{version}")
                else:
                    print(f"  ✓ {name}@{version}")

    bronze = store / "bronze"
    if bronze.is_dir():
        for name_dir in bronze.glob("*/"):
            for version_dir in name_dir.glob("*"):
                if (version_dir / "manifest.json").is_file():
                    store_versions.add((name_dir.name, version_dir.name))

    for name, version in sorted(store_versions - declared_versions):
        print(f"  ~ {name}@{version} stale (in store but not declared)")
        drift = True

    if drift:
        print("Drift detected.")
    else:
        print("No drift detected.")
    return 1 if drift else 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Run a full-text search over the store's gold index.

    Validates ``--source``/``--version`` against the gold index's
    ``indexed_sources`` registry through the retrieval backend: unknown values
    are user typos -> exit 2, the backend owns all SQLite/schema knowledge, and
    the CLI holds neither a connection nor schema-check helpers. Searches with
    :class:`SQLiteFTSBackend` and renders human-readable result blocks. Exit
    codes per the CLI contract (#27): 0 = hits found, 1 = no results, 2 = error.
    """
    store = Path(args.store) if args.store else Path(os.environ.get("KV_STORE", str(default_store())))
    db_path = knowledge_db_path(store)

    if not db_path.is_file():
        print(f"error: gold index not found at {db_path}; run 'kv ingest'", file=sys.stderr)
        return 2

    if args.limit < 1:
        print("error: --limit must be >= 1", file=sys.stderr)
        return 2

    filters = SearchFilters(source=args.source, version=args.version)
    try:
        with SQLiteFTSBackend(db_path) as backend:
            if filters.source is not None or filters.version is not None:
                indexed = backend.indexed_slices()
                known_sources = set(indexed.sources)
                known_versions = set(indexed.versions)
                for label, value, known in (
                    ("source", filters.source, known_sources),
                    ("version", filters.version, known_versions),
                ):
                    if value is not None and value not in known:
                        print(f"error: unknown {label} '{value}'", file=sys.stderr)
                        return 2
            results = backend.search(args.query, k=args.limit, filters=filters)
    except SearchBackendError as exc:
        print(f"error: search failed: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not results:
        return 1

    highlight = sys.stdout.isatty()
    terms = extract_terms(args.query)
    for rank, hit in enumerate(results, start=1):
        snippet = make_snippet(hit.text, terms, highlight=highlight)
        print(f"{rank}. {hit.source}@{hit.version}  {hit.path}:{hit.start_line}-{hit.end_line}")
        print(f"   {snippet}")
        if rank < len(results):
            print()
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    store, sources = _resolve_paths(args)
    failures = 0

    def report(check: str, status: str, detail: str = "") -> None:
        line = f"{status}: {check}"
        if detail:
            line += f" — {detail}"
        print(line)

    git_ver = git_version_tuple()
    if git_ver == (0, 0, 0):
        report("git installed", "FAIL", "git not found")
        failures += 1
    else:
        report("git installed", "PASS", f"git {git_ver[0]}.{git_ver[1]}.{git_ver[2]}")

    if supports_partial_clone():
        report("partial-clone support", "PASS", f"git >= 2.17 (found {git_ver[0]}.{git_ver[1]}.{git_ver[2]})")
    else:
        report("partial-clone support", "FAIL", f"git < 2.17 (found {git_ver[0]}.{git_ver[1]}.{git_ver[2]})")
        failures += 1

    for name in iter_source_names(sources):
        try:
            load_source(sources, name)
            report(f"source config {name}", "PASS")
        except SourceError as exc:
            report(f"source config {name}", "FAIL", str(exc))
            failures += 1
    if not iter_source_names(sources):
        report("source configs", "FAIL", "no source configs found")
        failures += 1

    reachability_failures = 0
    for name in iter_source_names(sources):
        try:
            config = load_source(sources, name)
        except SourceError:
            continue
        if remote_reachable(config.repo):
            report(f"remote reachable {config.repo}", "PASS")
        else:
            report(f"remote reachable {config.repo}", "FAIL")
            reachability_failures += 1
    if reachability_failures > 0:
        failures += 1

    if store.is_dir() and store.stat().st_mode & 0o200 == 0:
        report(f"store writable {store}", "PASS")
    else:
        try:
            store.mkdir(parents=True, exist_ok=True)
            test_file = store / ".doctor_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            report(f"store writable {store}", "PASS")
        except OSError:
            report(f"store writable {store}", "FAIL")
            failures += 2

    try:
        metadata = read_store_metadata(store)
        schema_version = metadata.get("schema_version", 0)
        if schema_version == 1:
            report("store schema compat", "PASS", f"schema_version {schema_version}")
        else:
            report("store schema compat", "WARN", f"schema_version {schema_version}, expected 1")
    except StoreError:
        report("store schema compat", "WARN", "store not initialized (run 'kv init')")

    return 1 if failures > 0 else 0


def main() -> int:
    """Entry point for the kv CLI.

    Returns
    -------
    int
        Process exit code.
    """
    args = build_parser().parse_args()
    try:
        result = args.func(args)
        if isinstance(result, int):
            return result
    except (SourceError, GitError, StoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
