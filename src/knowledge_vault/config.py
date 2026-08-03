"""Source configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


class SourceError(Exception):
    """Raised when a source config cannot be loaded."""


@dataclass(frozen=True)
class SourceConfig:
    """A configured knowledge source."""

    name: str
    repo: str
    docs_path: str
    desired_tags: list[str]


def _require_str(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or value == "":
        raise SourceError(f"invalid source config {path}: missing or non-string field {key!r}")
    return value


def _require_str_list(data: dict[str, Any], key: str, path: Path) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        raise SourceError(f"invalid source config {path}: field {key!r} must be a non-empty list of strings")
    items = cast(list[str], value)
    result: list[str] = []
    for item in items:
        if not item:
            raise SourceError(f"invalid source config {path}: field {key!r} must be a non-empty list of strings")
        result.append(item)
    return result


def load_source(sources_dir: Path, name: str) -> SourceConfig:
    """Load the source config for *name* from *sources_dir*.

    Parameters
    ----------
    sources_dir : Path
        Directory containing one YAML config per source.
    name : str
        Source name; resolves to ``<name>.yaml``.

    Returns
    -------
    SourceConfig
        The loaded source configuration.

    Raises
    ------
    SourceError
        If the config file is missing or malformed.
    """
    path = sources_dir / f"{name}.yaml"
    if not path.is_file():
        raise SourceError(f"unknown source {name!r}: no config at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SourceError(f"invalid source config {path}: expected a YAML mapping")
    config_data = cast(dict[str, Any], data)
    desired_raw = config_data.get("desired")
    if not isinstance(desired_raw, dict):
        raise SourceError(f"invalid source config {path}: missing 'desired' mapping")
    desired = cast(dict[str, Any], desired_raw)
    return SourceConfig(
        name=_require_str(config_data, "name", path),
        repo=_require_str(config_data, "repo", path),
        docs_path=_require_str(config_data, "docs_path", path),
        desired_tags=_require_str_list(desired, "tags", path),
    )


def iter_source_names(sources_dir: Path) -> list[str]:
    """List all source names found in *sources_dir*.

    Parameters
    ----------
    sources_dir : Path
        Directory containing ``*.yaml`` and ``*.yml`` source configs.

    Returns
    -------
    list[str]
        Sorted list of source names (file stems).
    """
    if not sources_dir.is_dir():
        return []
    paths = list(sources_dir.glob("*.yaml")) + list(sources_dir.glob("*.yml"))
    return sorted(p.stem for p in paths if p.is_file())
