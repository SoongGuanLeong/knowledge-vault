"""Search backend error type (ticket #25, #30)."""

from __future__ import annotations


class SearchBackendError(Exception):
    """Raised when a search backend cannot perform its job.

    Signifies a backend-side failure (missing/corrupt database, incompatible
    schema, backend not open). ``ValueError`` is used instead for caller bugs
    (blank query, ``k < 1``) and is never wrapped.
    """
