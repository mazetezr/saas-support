"""Knowledge base service with tenant-isolated pgvector search.

Replaces ChromaDB with PostgreSQL pgvector. Every operation requires tenant_id.
Uses intfloat/multilingual-e5-small embeddings with prefix convention:
- "passage: " for document chunks during ingestion
- "query: " for search queries
"""

import asyncio
import logging
from uuid import UUID

from sentence_transformers import SentenceTransformer

from bot.database.repositories.chunk_repo import ChunkRepo
from bot.database.repositories.document_repo import DocumentRepo
from bot.services.document_parser import DocumentParser
from bot.utils.text_splitter import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """Coordinates document ingestion and semantic search with tenant isolation."""

    def __init__(
        self,
        chunk_repo: ChunkRepo,
        document_repo: DocumentRepo,
        text_splitter: RecursiveCharacterTextSplitter,
        embedding_model: SentenceTransformer,
    ):
        self.chunk_repo = chunk_repo
        self.document_repo = document_repo
        self.splitter = text_splitter
        self.embedding_model = embedding_model

    async def ingest_document(
        self, tenant_id: UUID, filename: str, content: bytes, uploaded_by: int
    ) -> dict:
        """Ingest a document: parse, chunk, embed, store with tenant isolation.

        Returns dict with document_id, filename, chunk_count.
        Raises ValueError if document is empty or too short.
        """
        # 1. Parse document (blocking I/O)
        text = await asyncio.to_thread(DocumentParser.parse, filename, content)

        if not text or len(text.strip()) < 50:
            raise ValueError("Текст документа пуст или слишком короткий (минимум 50 символов)")

        # 2. Split into chunks
        chunks = self.splitter.split_text(text)
        if not chunks:
            raise ValueError("Документ не содержит текстовых фрагментов после разделения")

        # 3. Create document record
        doc = await self.document_repo.create(tenant_id, filename, uploaded_by)
        document_id = doc["id"]

        # 4. Generate embeddings with E5 "passage:" prefix
        prefixed = ["passage: " + c for c in chunks]
        embeddings = await asyncio.to_thread(
            self.embedding_model.encode, prefixed, normalize_embeddings=True
        )

        # 5. Store chunks with embeddings in pgvector
        await self.chunk_repo.create_many(
            document_id=document_id,
            tenant_id=tenant_id,
            chunks=chunks,
            embeddings=embeddings,
        )

        # 6. Update document status
        await self.document_repo.update_status(document_id, "ready", len(chunks))

        logger.info(
            "Ingested '%s' for tenant %s (doc=%s, chunks=%d)",
            filename, tenant_id, document_id, len(chunks),
        )

        return {
            "document_id": str(document_id),
            "filename": filename,
            "chunk_count": len(chunks),
        }

    async def search(
        self, query: str, tenant_id: UUID, n_results: int = 5
    ) -> list[dict]:
        """Semantic search scoped to a single tenant."""
        query_embedding = await asyncio.to_thread(
            self.embedding_model.encode,
            ["query: " + query],
            normalize_embeddings=True,
        )

        results = await self.chunk_repo.search(
            tenant_id=tenant_id,
            query_embedding=query_embedding[0],
            limit=n_results,
        )

        logger.debug("Search '%s' (tenant=%s): %d results", query[:50], tenant_id, len(results))
        return results

    async def search_for_context(
        self,
        query: str,
        tenant_id: UUID,
        threshold: float = 0.55,
        max_chunks: int = 5,
    ) -> list[dict]:
        """Search and filter by similarity threshold."""
        results = await self.search(query, tenant_id, n_results=max_chunks)
        filtered = [r for r in results if r["similarity"] >= threshold]
        logger.info(
            "KB search '%s' (tenant=%s): %d/%d above %.2f",
            query[:50], tenant_id, len(filtered), len(results), threshold,
        )
        return filtered

    async def list_documents(self, tenant_id: UUID) -> list:
        return await self.document_repo.list_by_tenant(tenant_id)

    async def delete_document(self, document_id: UUID, tenant_id: UUID) -> bool:
        """Delete a document and its chunks (CASCADE)."""
        doc = await self.document_repo.get(document_id)
        if not doc:
            raise ValueError("Документ не найден")
        if doc["tenant_id"] != tenant_id:
            raise ValueError("Нет доступа к этому документу")

        await self.document_repo.delete(document_id, tenant_id)
        logger.info("Deleted document %s for tenant %s", document_id, tenant_id)
        return True
