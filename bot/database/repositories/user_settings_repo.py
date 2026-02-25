"""User settings repository — tracks which project a regular user has selected."""

from uuid import UUID

from bot.database.connection import Database


class UserSettingsRepo:
    def __init__(self, db: Database):
        self.db = db

    async def get(self, user_id: int):
        return await self.db.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1", user_id
        )

    async def set_tenant(self, user_id: int, tenant_id: UUID):
        """Set or update the user's selected tenant (upsert)."""
        await self.db.execute(
            """
            INSERT INTO user_settings (user_id, current_tenant_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET current_tenant_id = $2
            """,
            user_id, tenant_id,
        )

    async def clear_tenant(self, user_id: int):
        """Clear user's project selection."""
        await self.db.execute(
            "UPDATE user_settings SET current_tenant_id = NULL WHERE user_id = $1",
            user_id,
        )

    async def get_language(self, user_id: int) -> str | None:
        """Get user's UI language. Returns None if not set."""
        return await self.db.fetchval(
            "SELECT language FROM user_settings WHERE user_id = $1", user_id
        )

    async def update_language(self, user_id: int, language: str):
        """Set or update user's UI language (upsert)."""
        await self.db.execute(
            """
            INSERT INTO user_settings (user_id, language)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET language = $2
            """,
            user_id, language,
        )
