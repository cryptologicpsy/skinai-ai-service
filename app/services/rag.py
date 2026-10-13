"""Retrieval-augmented generation interface (not yet implemented).

Defines the future contract for retrieving relevant product/ingredient
context and generating grounded answers over it. No implementation is
wired up yet -- this exists so API and service boundaries are stable when
RAG is actually built, and so it's clear this is planned, not working,
functionality.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    source_type: str  # "product" | "ingredient"
    source_id: str
    content: str
    score: float


class RAGService(ABC):
    @abstractmethod
    async def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for a query."""

    @abstractmethod
    async def answer(self, query: str, *, top_k: int = 5) -> str:
        """Retrieve context and generate a grounded answer."""


class NotConfiguredRAGService(RAGService):
    """Placeholder that raises until retrieval/generation is implemented."""

    async def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        raise NotImplementedError("RAG retrieval is not implemented yet.")

    async def answer(self, query: str, *, top_k: int = 5) -> str:
        raise NotImplementedError("RAG answering is not implemented yet.")


def get_rag_service() -> RAGService:
    """Return the configured RAG service. Currently always a stub."""

    return NotConfiguredRAGService()
