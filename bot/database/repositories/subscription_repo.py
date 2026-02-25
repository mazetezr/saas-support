"""Subscription repository — CRUD for subscriptions table."""

from datetime import timedelta
from uuid import UUID

from bot.database.connection import Database


class SubscriptionRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create_trial(self, tenant_id: UUID, days: int = 7):
        """Create a 7-day trial subscription."""
        return await self.db.fetchrow(
            """
            INSERT INTO subscriptions (tenant_id, plan_id, status, expires_at)
            VALUES ($1, NULL, 'active', NOW() + $2::interval)
            RETURNING *
            """,
            tenant_id, timedelta(days=days),
        )

    async def create_pending(self, tenant_id: UUID, plan_id: int, invoice_id: str, amount: float):
        """Create a pending subscription awaiting payment."""
        return await self.db.fetchrow(
            """
            INSERT INTO subscriptions (
                tenant_id, plan_id, status, expires_at,
                payment_invoice_id, payment_amount
            ) VALUES ($1, $2, 'pending', NOW() + INTERVAL '30 days', $3, $4)
            RETURNING *
            """,
            tenant_id, plan_id, invoice_id, amount,
        )

    async def activate(self, invoice_id: str, days: int = 30):
        """Activate a pending subscription by invoice ID."""
        return await self.db.fetchrow(
            """
            UPDATE subscriptions
            SET status = 'active',
                started_at = NOW(),
                expires_at = NOW() + $1::interval
            WHERE payment_invoice_id = $2 AND status = 'pending'
            RETURNING *
            """,
            timedelta(days=days), invoice_id,
        )

    async def get_active(self, tenant_id: UUID):
        """Get current active subscription for a tenant."""
        return await self.db.fetchrow(
            """
            SELECT s.*, p.name as plan_name, p.max_chunks, p.price_usd
            FROM subscriptions s
            LEFT JOIN plans p ON s.plan_id = p.id
            WHERE s.tenant_id = $1 AND s.status = 'active'
            ORDER BY s.expires_at DESC
            LIMIT 1
            """,
            tenant_id,
        )

    async def get_by_invoice(self, invoice_id: str):
        return await self.db.fetchrow(
            "SELECT * FROM subscriptions WHERE payment_invoice_id = $1",
            invoice_id,
        )

    async def get_expiring(self, hours: int = 24):
        """Get subscriptions expiring within N hours (for reminders)."""
        return await self.db.fetch(
            """
            SELECT s.*, t.owner_user_id, t.project_name, t.chat_id
            FROM subscriptions s
            JOIN tenants t ON s.tenant_id = t.id
            WHERE s.status = 'active'
              AND s.expires_at BETWEEN NOW() AND NOW() + $1::interval
            """,
            timedelta(hours=hours),
        )

    async def get_expired(self):
        """Get subscriptions past their expiry date."""
        return await self.db.fetch(
            """
            SELECT s.*, t.owner_user_id, t.project_name, t.chat_id
            FROM subscriptions s
            JOIN tenants t ON s.tenant_id = t.id
            WHERE s.status = 'active'
              AND s.expires_at < NOW()
            """
        )

    async def expire(self, subscription_id: UUID):
        await self.db.execute(
            "UPDATE subscriptions SET status = 'expired' WHERE id = $1",
            subscription_id,
        )

    async def get_revenue(self, days: int = 30):
        """Get total revenue for a period (for superadmin)."""
        return await self.db.fetchval(
            """
            SELECT COALESCE(SUM(payment_amount), 0)
            FROM subscriptions
            WHERE status IN ('active', 'expired')
              AND payment_amount IS NOT NULL
              AND started_at >= NOW() - $1::interval
            """,
            timedelta(days=days),
        )
