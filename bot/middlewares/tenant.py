"""Tenant resolution middleware.

Resolves TenantContext from incoming messages:
- Group/supergroup: by chat_id (Redis cache -> PostgreSQL fallback)
- Private chat: by user_settings.current_tenant_id

Injects tenant into handler data as data["tenant"].
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from bot.core.tenant import TenantContext

logger = logging.getLogger(__name__)

TENANT_CACHE_TTL = 300  # 5 minutes


class TenantMiddleware(BaseMiddleware):
    """Resolves tenant context for every incoming message and callback."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        from bot import state

        tenant = None

        if isinstance(event, CallbackQuery):
            message = event.message
            user_id = event.from_user.id
        else:
            message = event
            user_id = event.from_user.id if event.from_user else None

        if message and message.chat:
            chat_type = message.chat.type
            chat_id = message.chat.id

            if chat_type in ("group", "supergroup"):
                tenant = await self._resolve_by_chat(chat_id)
            elif chat_type == "private" and user_id:
                tenant = await self._resolve_by_user(user_id)

        data["tenant"] = tenant
        return await handler(event, data)

    async def _resolve_by_chat(self, chat_id: int) -> TenantContext | None:
        """Resolve tenant from group chat_id with Redis caching."""
        from bot import state

        cache_key = f"tenant:chat:{chat_id}"

        # Try Redis cache first
        if state.redis:
            cached = await state.redis.get(cache_key)
            if cached:
                try:
                    return TenantContext.from_json(cached)
                except Exception:
                    logger.warning("Failed to deserialize cached tenant for chat %d", chat_id)

        # Fallback to PostgreSQL
        if state.tenant_repo:
            record = await state.tenant_repo.get_by_chat_id(chat_id)
            if record:
                tenant = TenantContext.from_record(record)
                # Cache for next time
                if state.redis:
                    try:
                        await state.redis.setex(cache_key, TENANT_CACHE_TTL, tenant.to_json())
                    except Exception:
                        pass
                return tenant

        return None

    async def _resolve_by_user(self, user_id: int) -> TenantContext | None:
        """Resolve tenant from user's selected project in private chat."""
        from bot import state

        if not state.user_settings_repo or not state.tenant_repo:
            return None

        user_settings = await state.user_settings_repo.get(user_id)
        if not user_settings or not user_settings["current_tenant_id"]:
            return None

        record = await state.tenant_repo.get(user_settings["current_tenant_id"])
        if record:
            return TenantContext.from_record(record)

        return None
