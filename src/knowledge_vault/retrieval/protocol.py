"""Engine-agnostic retrieval surface (ticket #25).

The protocol documents the shape of a search backend without revealing any
storage details: SQL, connections, and cursor types are owned by the backend
and never surface here. Lifecycle (``open``/``close``, schema gating) is
backend-specific and deliberately absent from the protocol.
"""

from __future__ import annotations

from typing import Protocol

from knowledge_vault.retrieval.models import SearchFilters, SearchResult


class SearchBackend(Protocol):
    """Structural contract for any knowledge.db search engine.

    Implementations expose exactly ``search``; callers depend on this protocol
    so a backend swap never changes the retrieval surface.
    """

    def search(
        self,
        query: str,
        *,
        k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[SearchResult]:
        """Keyword search over an indexed store.

        Parameters
        ----------
        query : str
            Search expression; interpreted backend-specifically.
        k : int
            Maximum number of hits to return. Must be >= 1.
        filters : SearchFilters | None
            Optional ``(source, version)`` constraints; ``None`` fields are
            unbounded, and unknown filter values yield an empty result rather
            than an error.

        Returns
        -------
        list[SearchResult]
            Hits best-first, or ``[]`` when nothing matches.

        Raises
        ------
        ValueError
            If ``query`` is blank or ``k < 1``.
        """
        ...
