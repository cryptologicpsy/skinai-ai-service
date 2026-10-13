"""Embedding generation interface (no provider wired up yet).

This module defines the contract a future embedding provider (e.g. an
OpenAI-backed API client or a self-hosted model server) must implement. It
exists so the database schema (pgvector columns, see app/models) and the
rest of the service layer can be built against a stable interface now,
without committing to a specific provider or downloading/calling anything
during application startup.

`get_embedding_service()` is safe to call at import or startup time: it
only returns a placeholder that raises `NotImplementedError` if actually
used. No network calls or model loads happen anywhere in this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import get_settings


class EmbeddingService(ABC):
    """Contract for turning text into vector embeddings."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of vectors this service produces."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Embed a single piece of text."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one call."""


class NotConfiguredEmbeddingService(EmbeddingService):
    """Placeholder used until a real provider is implemented and configured.

    Raises on use rather than returning fake vectors, so callers fail
    loudly instead of silently writing meaningless embeddings.
    """

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError(
            "No embedding provider is configured. Implement an "
            "EmbeddingService subclass and return it from "
            "get_embedding_service()."
        )

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("No embedding provider is configured. See embed_text().")


def get_embedding_service() -> EmbeddingService:
    """Return the configured embedding service.

    Currently always returns the unconfigured placeholder. Swap this for a
    real implementation once a provider is chosen; the pgvector column
    dimension (settings.embedding_dimension) must match that provider's
    output size.
    """

    settings = get_settings()
    return NotConfiguredEmbeddingService(dimension=settings.embedding_dimension)
