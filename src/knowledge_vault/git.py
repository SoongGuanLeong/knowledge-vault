"""Thin wrappers around git for remote tag discovery and snapshot acquisition."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""


def _run(args: list[str], *, cwd: Path | None = None) -> str:
    """Run git and return stdout, raising GitError on failure."""
    completed = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        raise GitError(detail or f"git {args[0]} failed")
    return completed.stdout


def _remote_tags(repo_url: str) -> dict[str, str]:
    """Map tag name to commit SHA, peeling annotated tags."""
    output = _run(["ls-remote", "--tags", repo_url])
    commits: dict[str, str] = {}
    for line in output.splitlines():
        sha, sep, ref = line.partition("\t")
        if not sep or not ref.startswith("refs/tags/"):
            continue
        tag = ref[len("refs/tags/") :]
        if tag.endswith("^{}"):
            commits[tag[:-3]] = sha
        else:
            commits.setdefault(tag, sha)
    return commits


def list_tags(repo_url: str) -> list[str]:
    """List tags advertised by the remote, sorted.

    Parameters
    ----------
    repo_url : str
        Remote repository URL.

    Returns
    -------
    list[str]
        Tag names advertised by the remote, sorted.
    """
    return sorted(_remote_tags(repo_url))


def resolve_commit(repo_url: str, tag: str) -> str:
    """Resolve *tag* on the remote to its commit SHA.

    Parameters
    ----------
    repo_url : str
        Remote repository URL.
    tag : str
        Tag name to resolve.

    Returns
    -------
    str
        Commit SHA the tag points at.

    Raises
    ------
    GitError
        If the tag does not exist on the remote.
    """
    commits = _remote_tags(repo_url)
    if tag not in commits:
        raise GitError(f"tag {tag!r} not found in remote {repo_url}")
    return commits[tag]


def acquire(repo_url: str, tag: str, commit: str, dest: Path) -> None:
    """Partial-clone *repo_url* and check out *commit* into *dest*.

    Parameters
    ----------
    repo_url : str
        Remote repository URL.
    tag : str
        Tag name, fetched to verify *commit* locally.
    commit : str
        Commit SHA to check out.
    dest : Path
        Destination directory for the clone.

    Raises
    ------
    GitError
        If the tag resolves to a different commit locally.
    """
    _run(["clone", "--filter=blob:none", "--no-checkout", repo_url, str(dest)])
    _run(["fetch", "origin", f"refs/tags/{tag}:refs/tags/{tag}"], cwd=dest)
    local_commit = _run(["rev-parse", f"{tag}^{{commit}}"], cwd=dest).strip()
    if local_commit != commit:
        raise GitError(f"tag {tag!r} resolved to {local_commit}, expected {commit}")
    _run(["checkout", commit], cwd=dest)
