"""Application entry point — Dispatcher setup, startup/shutdown lifecycle.

Initializes all infrastructure (PostgreSQL, Redis, embedding model),
creates service instances, registers middlewares and routers,
and runs both Telegram polling and the webhook server.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web
from sentence_transformers import SentenceTransformer

from bot import state
from bot.config import settings
from bot.database.connection import Database
from bot.database.redis import RedisManager
from bot.database.repositories.chunk_repo import ChunkRepo
from bot.database.repositories.document_repo import DocumentRepo
from bot.database.repositories.message_repo import MessageRepo
from bot.database.repositories.plan_repo import PlanRepo
from bot.database.repositories.subscription_repo import SubscriptionRepo
from bot.database.repositories.tenant_repo import TenantRepo
from bot.database.repositories.user_settings_repo import UserSettingsRepo
from bot.handlers import group, menu, onboarding, private, subscription, superadmin
from bot.middlewares.language import LanguageMiddleware
from bot.middlewares.logging import MessageLoggingMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.middlewares.tenant import TenantMiddleware
from bot.services.conversation import ConversationService
from bot.services.knowledge_base import KnowledgeBaseService
from bot.services.llm import LLMService
from bot.utils.text_splitter import RecursiveCharacterTextSplitter
from bot.webhook.server import create_webhook_app

logger = logging.getLogger(__name__)

# --- Dispatcher setup ---

storage = RedisStorage.from_url(settings.redis_url)
dp = Dispatcher(storage=storage)

# Middlewares (order matters: tenant first, then language, then rate limit, then logging)
dp.message.outer_middleware(TenantMiddleware())
dp.callback_query.outer_middleware(TenantMiddleware())
dp.message.outer_middleware(LanguageMiddleware())
dp.callback_query.outer_middleware(LanguageMiddleware())
dp.message.outer_middleware(RateLimitMiddleware())
dp.message.outer_middleware(MessageLoggingMiddleware())

# Routers (order matters: more specific first)
dp.include_router(onboarding.router)
dp.include_router(superadmin.router)
dp.include_router(menu.router)
dp.include_router(subscription.router)
dp.include_router(private.router)
dp.include_router(group.router)


@dp.startup()
async def on_startup(bot: Bot):
    """Initialize all resources on bot startup."""
    logger.info("Starting SaaS Support Bot...")

    # 1. PostgreSQL
    state.db = Database(settings.database_url)
    await state.db.initialize()

    # 2. Redis
    state.redis = RedisManager(settings.redis_url)
    await state.redis.initialize()

    # 3. Repositories
    state.tenant_repo = TenantRepo(state.db)
    state.subscription_repo = SubscriptionRepo(state.db)
    state.document_repo = DocumentRepo(state.db)
    state.chunk_repo = ChunkRepo(state.db)
    state.message_repo = MessageRepo(state.db)
    state.user_settings_repo = UserSettingsRepo(state.db)
    state.plan_repo = PlanRepo(state.db)

    # 4. Embedding model
    logger.info("Loading embedding model: %s", settings.embedding_model)
    state.embedding_model = await asyncio.to_thread(
        SentenceTransformer, settings.embedding_model
    )

    # 5. Services
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    state.kb_service = KnowledgeBaseService(
        chunk_repo=state.chunk_repo,
        document_repo=state.document_repo,
        text_splitter=text_splitter,
        embedding_model=state.embedding_model,
    )
    state.conv_service = ConversationService(state.message_repo)
    state.llm_service = LLMService()
    await state.llm_service.start()

    # 6. Bot references
    state.bot_instance = bot
    bot_info = await bot.get_me()
    state.bot_username = bot_info.username

    # 7. Bot description for users
    await bot.set_my_short_description(
        "AI-powered support assistant for your SaaS project"
    )
    await bot.set_my_description(
        "Smart AI customer support bot.\n\n"
        "Upload your docs — the bot will answer customer questions "
        "in your project's group chat.\n\n"
        "Get started → /start"
    )

    logger.info("Bot @%s started successfully", state.bot_username)


@dp.shutdown()
async def on_shutdown():
    """Clean up resources on bot shutdown."""
    logger.info("Shutting down...")
    if state.llm_service:
        await state.llm_service.close()
    if state.redis:
        await state.redis.close()
    if state.db:
        await state.db.close()
    logger.info("Shutdown complete")


async def main():
    """Run Telegram polling and webhook server concurrently."""
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Start webhook server for Cryptocloud payments
    webhook_app = create_webhook_app()
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    logger.info("Webhook server started on %s:%d", settings.webhook_host, settings.webhook_port)

    try:
        # Start Telegram polling
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
