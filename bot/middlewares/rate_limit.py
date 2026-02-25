"""Per-user rate limiting middleware using tenant-configurable limits.

Each project owner sets their own limits during onboarding:
- Per user per minute (burst protection)
- Per user per day (daily abuse cap)

Only limits messages that will trigger LLM calls.
Commands (/start, /help, etc.) and FSM interactions are never limited.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.texts import t

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Rate-limits messages before they reach LLM handlers."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        from bot import state

        if not isinstance(event, Message) or not event.text:
            return await handler(event, data)

        # Skip commands — they don't trigger LLM
        if event.text.startswith("/"):
            return await handler(event, data)

        # Skip if user is in an FSM state (onboarding, settings)
        fsm_context = data.get("state")
        if fsm_context:
            current_state = await fsm_context.get_state()
            if current_state is not None:
                return await handler(event, data)

        tenant = data.get("tenant")
        if not tenant or not state.redis:
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        # Skip rate limiting for project owner
        if user_id == tenant.owner_user_id:
            return await handler(event, data)

        tid = str(tenant.tenant_id)
        per_minute = tenant.rate_limit_per_minute
        per_day = tenant.rate_limit_per_day

        # 1) Check daily limit FIRST (more important blocker)
        key_day = f"rl:u:{user_id}:t:{tid}:day"
        count_day = await state.redis.incr(key_day)
        if count_day == 1:
            await state.redis.expire(key_day, 86400)
        if count_day > per_day:
            logger.warning("Rate limit (daily user) hit: user=%d tenant=%s", user_id, tid)
            lang = data.get("lang", "ru")
            await event.answer(t("rate_limit_daily", lang, per_day=per_day))
            return

        # 2) Per-user per-minute burst limit
        key_minute = f"rl:u:{user_id}:t:{tid}:min"
        count_min = await state.redis.incr(key_minute)
        if count_min == 1:
            await state.redis.expire(key_minute, 60)
        if count_min > per_minute:
            logger.warning("Rate limit (per-minute) hit: user=%d tenant=%s", user_id, tid)
            lang = data.get("lang", "ru")
            await event.answer(t("rate_limit_minute", lang, per_minute=per_minute))
            return

        return await handler(event, data)
