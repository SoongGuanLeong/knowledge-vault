"""Store layout helpers."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_store() -> Path:
    """The default knowledge-store location, sibling of the project.

    Returns
    -------
    Path
        ``<project root>/../knowledge-store``.
    """
    return PROJECT_ROOT.parent / "knowledge-store"


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
