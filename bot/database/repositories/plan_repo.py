"""Plan repository — read-only access to subscription plans."""

from bot.database.connection import Database


class PlanRepo:
    def __init__(self, db: Database):
        self.db = db

    async def get_all(self):
        return await self.db.fetch(
            "SELECT * FROM plans ORDER BY price_usd ASC"
        )

    async def get_by_name(self, name: str):
        return await self.db.fetchrow(
            "SELECT * FROM plans WHERE name = $1", name
        )

    async def get_by_id(self, plan_id: int):
        return await self.db.fetchrow(
            "SELECT * FROM plans WHERE id = $1", plan_id
        )
