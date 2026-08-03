"""Store layout helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STORE_SCHEMA_VERSION = 1
MEDALLION_DIRS = ("bronze", "silver", "gold", "cache")


def default_store() -> Path:
    """The default knowledge-store location, sibling of the project.

    Returns
    -------
    Path
        ``<project root>/../knowledge-store``.
    """
    return PROJECT_ROOT.parent / "knowledge-store"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def init_store(store: Path) -> None:
    """Create the medallion directory structure and metadata.json at *store*.

    Idempotent: if ``metadata.json`` already exists the directory layout is ensured
    but the file is not overwritten.

    Parameters
    ----------
    store : Path
        Knowledge-store root to initialise.
    """
    store.mkdir(parents=True, exist_ok=True)
    for subdir in MEDALLION_DIRS:
        (store / subdir).mkdir(exist_ok=True)
    meta_path = store / "metadata.json"
    if meta_path.exists():
        return
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": STORE_SCHEMA_VERSION,
                "created_at": _now_iso(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def read_store_metadata(store: Path) -> dict[str, object]:
    """Read and return the store-level ``metadata.json``.

    Parameters
    ----------
    store : Path
        Knowledge-store root.

    Returns
    -------
    dict[str, object]
        Parsed metadata.

    Raises
    ------
    StoreError
        If the metadata file is missing or unreadable.
    """
    meta_path = store / "metadata.json"
    if not meta_path.is_file():
        raise StoreError(f"store at {store} is not initialised (no metadata.json)")
    return json.loads(meta_path.read_text(encoding="utf-8"))


class StoreError(Exception):
    """Raised when a store operation fails."""


def default_sources_dir() -> Path:
    """The default sources directory within the project.

    Returns
    -------
    Path
        ``<project root>/sources``.
    """
    return PROJECT_ROOT / "sources"


def version_from_tag(tag: str) -> str:
    """Strip a leading 'v' from a tag to form the version key.

    Parameters
    ----------
    tag : str
        Tag as advertised by the remote.

    Returns
    -------
    str
        Version key with any leading 'v' removed.
    """
    return tag[1:] if tag.startswith("v") else tag


def bronze_dir(store: Path, name: str, version: str) -> Path:
    """The bronze directory for *name* at *version*.

    Parameters
    ----------
    store : Path
        Knowledge-store root.
    name : str
        Source name.
    version : str
        Version key.

    Returns
    -------
    Path
        ``<store>/bronze/<name>/<version>``.
    """
    return store / "bronze" / name / version


def silver_dir(store: Path, name: str, version: str) -> Path:
    """The silver directory for *name* at *version*.

    Parameters
    ----------
    store : Path
        Knowledge-store root.
    name : str
        Source name.
    version : str
        Version key.

    Returns
    -------
    Path
        ``<store>/silver/<name>/<version>``.
    """
    return store / "silver" / name / version
