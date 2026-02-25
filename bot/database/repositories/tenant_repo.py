"""Tenant repository — CRUD operations for the tenants table."""

from uuid import UUID

from bot.database.connection import Database


class TenantRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        owner_user_id: int,
        project_name: str,
        chat_id: int,
        chat_title: str | None,
        openrouter_api_key: str,
        moderator_usernames: list[str] | None = None,
        persona_doc: str | None = None,
        status: str = "trial",
        rate_limit_per_minute: int = 5,
        rate_limit_per_day: int = 50,
    ):
        return await self.db.fetchrow(
            """
            INSERT INTO tenants (
                owner_user_id, project_name, chat_id, chat_title,
                openrouter_api_key, moderator_usernames, persona_doc, status,
                rate_limit_per_minute, rate_limit_per_day
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            owner_user_id, project_name, chat_id, chat_title,
            openrouter_api_key, moderator_usernames or [], persona_doc, status,
            rate_limit_per_minute, rate_limit_per_day,
        )

    async def get(self, tenant_id: UUID):
        return await self.db.fetchrow(
            "SELECT * FROM tenants WHERE id = $1", tenant_id
        )

    async def get_by_owner(self, owner_user_id: int):
        return await self.db.fetchrow(
            "SELECT * FROM tenants WHERE owner_user_id = $1", owner_user_id
        )

    async def get_by_chat_id(self, chat_id: int):
        return await self.db.fetchrow(
            "SELECT * FROM tenants WHERE chat_id = $1", chat_id
        )

    async def get_all_active(self):
        """Get tenants with active status that have documents."""
        return await self.db.fetch(
            """
            SELECT t.* FROM tenants t
            WHERE t.status IN ('trial', 'active')
              AND t.is_active = true
              AND EXISTS (SELECT 1 FROM documents d WHERE d.tenant_id = t.id)
            ORDER BY t.project_name
            """
        )

    async def update_status(self, tenant_id: UUID, status: str):
        await self.db.execute(
            "UPDATE tenants SET status = $1, updated_at = NOW() WHERE id = $2",
            status, tenant_id,
        )

    async def update_chat(self, tenant_id: UUID, chat_id: int, chat_title: str | None):
        await self.db.execute(
            "UPDATE tenants SET chat_id = $1, chat_title = $2, updated_at = NOW() WHERE id = $3",
            chat_id, chat_title, tenant_id,
        )

    async def update_moderators(self, tenant_id: UUID, usernames: list[str]):
        await self.db.execute(
            "UPDATE tenants SET moderator_usernames = $1, updated_at = NOW() WHERE id = $2",
            usernames, tenant_id,
        )

    async def update_persona(self, tenant_id: UUID, persona_doc: str | None):
        await self.db.execute(
            "UPDATE tenants SET persona_doc = $1, updated_at = NOW() WHERE id = $2",
            persona_doc, tenant_id,
        )

    async def update_api_key(self, tenant_id: UUID, encrypted_key: str):
        await self.db.execute(
            "UPDATE tenants SET openrouter_api_key = $1, updated_at = NOW() WHERE id = $2",
            encrypted_key, tenant_id,
        )

    async def update_rate_limits(self, tenant_id: UUID, per_minute: int, per_day: int):
        await self.db.execute(
            "UPDATE tenants SET rate_limit_per_minute = $1, rate_limit_per_day = $2, updated_at = NOW() WHERE id = $3",
            per_minute, per_day, tenant_id,
        )

    async def list_all(self):
        """List all tenants (for superadmin)."""
        return await self.db.fetch(
            "SELECT * FROM tenants ORDER BY created_at DESC"
        )

    async def count_all(self):
        return await self.db.fetchval("SELECT COUNT(*) FROM tenants")
