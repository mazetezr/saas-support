"""Chunk repository — vector storage and search with tenant isolation.

Replaces ChromaDB with PostgreSQL pgvector.
Critical: every search query MUST include tenant_id filter.
"""

from uuid import UUID

import numpy as np

from bot.database.connection import Database


class ChunkRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        document_id: UUID,
        tenant_id: UUID,
        chunk_index: int,
        content: str,
        embedding: list[float] | np.ndarray,
    ):
        """Store a chunk with its embedding vector."""
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding, dtype=np.float32)
        await self.db.execute(
            """
            INSERT INTO chunks (document_id, tenant_id, chunk_index, content, embedding)
            VALUES ($1, $2, $3, $4, $5)
            """,
            document_id, tenant_id, chunk_index, content, embedding,
        )

    async def create_many(
        self,
        document_id: UUID,
        tenant_id: UUID,
        chunks: list[str],
        embeddings: list[list[float]] | np.ndarray,
    ):
        """Batch insert chunks with embeddings."""
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings, dtype=np.float32)
        args = [
            (document_id, tenant_id, i, text, embeddings[i])
            for i, text in enumerate(chunks)
        ]
        await self.db.executemany(
            """
            INSERT INTO chunks (document_id, tenant_id, chunk_index, content, embedding)
            VALUES ($1, $2, $3, $4, $5)
            """,
            args,
        )

    async def search(
        self,
        tenant_id: UUID,
        query_embedding: list[float] | np.ndarray,
        limit: int = 5,
    ) -> list[dict]:
        """Cosine similarity search scoped to a single tenant.

        Returns list of dicts with: content, similarity, document_id, chunk_index.
        """
        if not isinstance(query_embedding, np.ndarray):
            query_embedding = np.array(query_embedding, dtype=np.float32)
        rows = await self.db.fetch(
            """
            SELECT
                c.content,
                1 - (c.embedding <=> $1) AS similarity,
                c.document_id,
                c.chunk_index,
                d.filename
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.tenant_id = $2
            ORDER BY c.embedding <=> $1
            LIMIT $3
            """,
            query_embedding, tenant_id, limit,
        )
        return [
            {
                "chunk_text": row["content"],
                "similarity": float(row["similarity"]),
                "document_id": str(row["document_id"]),
                "chunk_index": row["chunk_index"],
                "filename": row["filename"],
            }
            for row in rows
        ]

    async def count_by_tenant(self, tenant_id: UUID) -> int:
        return await self.db.fetchval(
            "SELECT COUNT(*) FROM chunks WHERE tenant_id = $1",
            tenant_id,
        ) or 0

    async def delete_by_document(self, document_id: UUID):
        await self.db.execute(
            "DELETE FROM chunks WHERE document_id = $1", document_id
        )
