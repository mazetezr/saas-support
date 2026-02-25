"""Document repository — CRUD for documents table with tenant isolation."""

from uuid import UUID

from bot.database.connection import Database


class DocumentRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, tenant_id: UUID, filename: str, uploaded_by: int):
        return await self.db.fetchrow(
            """
            INSERT INTO documents (tenant_id, filename, uploaded_by, status)
            VALUES ($1, $2, $3, 'processing')
            RETURNING *
            """,
            tenant_id, filename, uploaded_by,
        )

    async def update_status(self, document_id: UUID, status: str, chunk_count: int = 0):
        await self.db.execute(
            "UPDATE documents SET status = $1, chunk_count = $2 WHERE id = $3",
            status, chunk_count, document_id,
        )

    async def get(self, document_id: UUID):
        return await self.db.fetchrow(
            "SELECT * FROM documents WHERE id = $1", document_id
        )

    async def list_by_tenant(self, tenant_id: UUID):
        return await self.db.fetch(
            """
            SELECT * FROM documents
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            """,
            tenant_id,
        )

    async def delete(self, document_id: UUID, tenant_id: UUID):
        """Delete document (CASCADE deletes chunks too)."""
        await self.db.execute(
            "DELETE FROM documents WHERE id = $1 AND tenant_id = $2",
            document_id, tenant_id,
        )

    async def count_by_tenant(self, tenant_id: UUID) -> int:
        return await self.db.fetchval(
            "SELECT COUNT(*) FROM documents WHERE tenant_id = $1",
            tenant_id,
        ) or 0
