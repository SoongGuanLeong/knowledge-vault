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


def remote_reachable(repo_url: str) -> bool:
    """Check whether *repo_url* is reachable via ``git ls-remote``.

    Parameters
    ----------
    repo_url : str
        Remote repository URL.

    Returns
    -------
    bool
        True if the remote responds, False otherwise.
    """
    completed = subprocess.run(["git", "ls-remote", "--exit-code", repo_url], capture_output=True, text=True)
    return completed.returncode == 0


def git_version_tuple() -> tuple[int, int, int]:
    """Return the installed git version as a (major, minor, patch) tuple.

    Returns
    -------
    tuple[int, int, int]
        Parsed version components.
    """
    output = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout
    parts = output.strip().split()
    version_str = parts[2] if len(parts) >= 3 and parts[1] == "version" else (parts[1] if len(parts) > 1 else "0.0.0")
    components = version_str.split(".")
    major = int(components[0]) if len(components) > 0 and components[0].isdigit() else 0
    minor = int(components[1]) if len(components) > 1 and components[1].isdigit() else 0
    patch = int(components[2]) if len(components) > 2 and components[2].isdigit() else 0
    return (major, minor, patch)


def supports_partial_clone() -> bool:
    """Check whether the installed git supports partial clone (``--filter``).

    Returns
    -------
    bool
        True if git >= 2.17 (partial clone became usable in 2.17).
    """
    return git_version_tuple() >= (2, 17, 0)


def remote_commit_resolves(repo_url: str, tag: str, expected_commit: str) -> bool:
    """Verify that *tag* in *repo_url* still resolves to *expected_commit*.

    Parameters
    ----------
    repo_url : str
        Remote repository URL.
    tag : str
        Tag name to check.
    expected_commit : str
        The commit SHA the tag is expected to point at.

    Returns
    -------
    bool
        True if the tag resolves to the expected commit, False otherwise.
    """
    try:
        resolved = resolve_commit(repo_url, tag)
    except GitError:
        return False
    return resolved == expected_commit


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
