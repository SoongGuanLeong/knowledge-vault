"""Search backend error type (ticket #25, #30)."""

from __future__ import annotations


class SearchBackendError(Exception):
    """Raised when a search backend cannot perform its job.

    Signifies a backend-side failure (missing/corrupt database, incompatible
    schema, backend not open). ``ValueError`` is used instead for caller bugs
    (blank query, ``k < 1``) and is never wrapped.
    """


class IndexedSlicesError(SearchBackendError):
    """Raised when the indexed-slices lookup cannot return a typed answer.

    Wraps a registry failure (missing, corrupt, or schema-incompatible gold
    database) as a retrieval-layer exception. The original cause is chained via
    ``from``. Subclasses :class:`SearchBackendError` so callers handling
    backend failures also catch registry lookup failures.
    """
