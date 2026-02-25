"""Background tasks using arq (Redis-based task queue).

Runs periodic subscription expiry checks:
- 24h before expiry: sends reminder to owner
- Past expiry: deactivates tenant, expires subscription, invalidates cache
"""

import logging

from arq import cron
from arq.connections import RedisSettings

from bot.config import settings
from bot.services.subscription_service import PLAN_PRICES, suggest_plan

logger = logging.getLogger(__name__)


async def check_subscription_expiry(ctx):
    """Hourly job: send reminders and deactivate expired subscriptions."""
    from bot import state

    if not state.subscription_repo or not state.tenant_repo:
        logger.warning("Worker: services not initialized, skipping")
        return

    # --- 24h reminders ---
    expiring = await state.subscription_repo.get_expiring(hours=24)
    for sub in expiring:
        owner_id = sub["owner_user_id"]
        project_name = sub["project_name"]
        tenant_id = sub["tenant_id"]

        total_chunks = await state.chunk_repo.count_by_tenant(tenant_id)
        suggested = suggest_plan(total_chunks)
        price = PLAN_PRICES.get(suggested, "?")

        if state.bot_instance:
            try:
                await state.bot_instance.send_message(
                    owner_id,
                    f"Подписка для проекта <b>{project_name}</b> истекает завтра.\n\n"
                    f"Ваша база: {total_chunks} фрагментов\n"
                    f"Подходящий план: <b>{suggested.title()}</b> — ${price}/мес\n\n"
                    f"Продлите подписку, чтобы бот продолжал работать.",
                )
            except Exception as e:
                logger.error("Failed to send expiry reminder to %d: %s", owner_id, e)

    # --- Deactivate expired ---
    expired = await state.subscription_repo.get_expired()
    for sub in expired:
        tenant_id = sub["tenant_id"]
        owner_id = sub["owner_user_id"]
        project_name = sub["project_name"]
        chat_id = sub["chat_id"]

        # Update statuses
        await state.tenant_repo.update_status(tenant_id, "expired")
        await state.subscription_repo.expire(sub["id"])

        # Invalidate cache
        if state.redis and chat_id:
            await state.redis.delete(f"tenant:chat:{chat_id}")

        # Notify owner
        if state.bot_instance:
            try:
                await state.bot_instance.send_message(
                    owner_id,
                    f"Подписка для проекта <b>{project_name}</b> истекла.\n"
                    f"Бот перестал отвечать в группе.\n\n"
                    f"Ваши документы сохранены. Продлите подписку для возобновления работы.",
                )
            except Exception as e:
                logger.error("Failed to notify expired tenant owner %d: %s", owner_id, e)

        logger.info("Expired tenant %s (%s)", tenant_id, project_name)


async def startup(ctx):
    """Worker startup: initialize DB, Redis, repos."""
    from bot.database.connection import Database
    from bot.database.redis import RedisManager
    from bot.database.repositories.chunk_repo import ChunkRepo
    from bot.database.repositories.subscription_repo import SubscriptionRepo
    from bot.database.repositories.tenant_repo import TenantRepo
    from bot import state

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    state.db = Database(settings.database_url)
    await state.db.initialize()

    state.redis = RedisManager(settings.redis_url)
    await state.redis.initialize()

    state.tenant_repo = TenantRepo(state.db)
    state.subscription_repo = SubscriptionRepo(state.db)
    state.chunk_repo = ChunkRepo(state.db)

    state.bot_instance = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    logger.info("Worker started")


async def shutdown(ctx):
    """Worker shutdown: clean up resources."""
    from bot import state

    if state.bot_instance:
        await state.bot_instance.session.close()
    if state.redis:
        await state.redis.close()
    if state.db:
        await state.db.close()

    logger.info("Worker stopped")


class WorkerSettings:
    """arq worker configuration."""
    functions = [check_subscription_expiry]
    cron_jobs = [cron(check_subscription_expiry, minute=0)]  # every hour at :00
    redis_settings = RedisSettings.from_dsn(settings.arq_redis_url)
    on_startup = startup
    on_shutdown = shutdown
