"""Language middleware — resolves user UI language and injects data['lang']."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message

logger = logging.getLogger(__name__)


class LanguageMiddleware(BaseMiddleware):
    """Resolves user language from user_settings and injects data['lang']."""

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery | InlineQuery,
        data: Dict[str, Any],
    ) -> Any:
        from bot import state

        lang = "ru"

        user = getattr(event, "from_user", None)
        user_id = user.id if user else None

        if user_id and state.user_settings_repo:
            # Try Redis cache first
            cache_key = f"user:lang:{user_id}"
            cached = None
            if state.redis:
                cached = await state.redis.get(cache_key)

            if cached:
                lang = cached
            else:
                user_lang = await state.user_settings_repo.get_language(user_id)
                if user_lang:
                    lang = user_lang
                if state.redis:
                    await state.redis.setex(cache_key, 300, lang)

        data["lang"] = lang
        return await handler(event, data)
