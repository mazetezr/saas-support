"""Subscription lifecycle management.

Plan limits, pricing, plan suggestion, and subscription activation.
"""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

PLAN_LIMITS = {"lite": 20, "standard": 50, "pro": 100, "business": 200}
PLAN_PRICES = {"lite": 5, "standard": 9, "pro": 19, "business": 39}


def suggest_plan(total_chunks: int) -> str:
    """Recommend the minimum plan that fits the current chunk count."""
    for name in ("lite", "standard", "pro", "business"):
        if total_chunks <= PLAN_LIMITS[name]:
            return name
    return "business"


def get_plan_info(plan_name: str) -> dict | None:
    """Get plan details by name."""
    if plan_name not in PLAN_LIMITS:
        return None
    return {
        "name": plan_name,
        "max_chunks": PLAN_LIMITS[plan_name],
        "price_usd": PLAN_PRICES[plan_name],
    }


async def activate_subscription(
    tenant_id: UUID, invoice_id: str, tenant_repo, subscription_repo, redis_manager, chat_id: int | None
):
    """Activate a paid subscription after successful payment.

    Updates subscription status, tenant status, and invalidates cache.
    """
    # Activate the subscription record
    sub = await subscription_repo.activate(invoice_id, days=30)
    if not sub:
        logger.error("No pending subscription found for invoice %s", invoice_id)
        return False

    # Update tenant status
    await tenant_repo.update_status(tenant_id, "active")

    # Invalidate Redis cache
    if redis_manager and chat_id:
        await redis_manager.delete(f"tenant:chat:{chat_id}")

    logger.info("Activated subscription for tenant %s (invoice=%s)", tenant_id, invoice_id)
    return True
