"""Message logging middleware with tenant context.

Captures all incoming text messages to PostgreSQL for conversation history.
Runs as an outer middleware before handlers. Tenant-aware: includes tenant_id
in saved messages when available.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)


class MessageLoggingMiddleware(BaseMiddleware):
    """Logs every incoming text message to the messages table."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if event.text and event.from_user and not event.from_user.is_bot:
            from bot import state

            tenant = data.get("tenant")

            if state.message_repo and tenant:
                try:
                    await state.message_repo.save(
                        tenant_id=tenant.tenant_id,
                        user_id=event.from_user.id,
                        chat_id=event.chat.id,
                        chat_type=event.chat.type,
                        role="user",
                        content=event.text,
                    )
                except Exception as e:
                    logger.error("Failed to log message: %s", e)

        return await handler(event, data)
