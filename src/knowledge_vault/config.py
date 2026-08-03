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
    desired_tag: str


def _require_str(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or value == "":
        raise SourceError(f"invalid source config {path}: missing or non-string field {key!r}")
    return value


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
        desired_tag=_require_str(desired, "tag", path),
    )
