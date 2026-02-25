"""Conversation service with tenant isolation.

All operations require tenant_id. Provides message logging, context retrieval,
LLM-based compaction, and FAQ candidate management.
"""

import logging
from uuid import UUID
from typing import TYPE_CHECKING

from bot.database.repositories.message_repo import MessageRepo

if TYPE_CHECKING:
    from bot.services.llm import LLMService
    from bot.core.tenant import TenantContext

logger = logging.getLogger(__name__)


class ConversationService:
    """Manages conversation history with tenant isolation."""

    def __init__(self, message_repo: MessageRepo):
        self.repo = message_repo

    async def save_message(
        self,
        tenant_id: UUID,
        user_id: int,
        chat_id: int,
        chat_type: str,
        role: str,
        content: str,
    ) -> int:
        """Save a message. Returns message ID."""
        return await self.repo.save(tenant_id, user_id, chat_id, chat_type, role, content)

    async def get_context(
        self, user_id: int, chat_id: int, tenant_id: UUID, limit: int = 10
    ) -> list[dict]:
        """Build conversation context: summary + recent messages."""
        return await self.repo.get_context(user_id, chat_id, tenant_id, limit)

    async def count_uncompacted_messages(
        self, user_id: int, chat_id: int, tenant_id: UUID
    ) -> int:
        return await self.repo.count_uncompacted(user_id, chat_id, tenant_id)

    async def compact_conversation(
        self,
        user_id: int,
        chat_id: int,
        tenant_id: UUID,
        tenant: "TenantContext",
        llm_service: "LLMService",
        keep_recent: int = 10,
    ) -> bool:
        """Summarize old messages via LLM and store the summary.

        Returns True on success, False on failure.
        """
        to_summarize, from_id, to_id = await self.repo.get_for_compaction(
            user_id, chat_id, tenant_id, keep_recent
        )

        if not to_summarize:
            logger.debug("Not enough messages to compact for user %d", user_id)
            return False

        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in to_summarize
        )

        summarization_prompt = (
            "Сделай краткое содержание диалога между пользователем и ассистентом поддержки. "
            "Сохрани ключевые вопросы, ответы, решения и важные детали. "
            "Пиши кратко, но не теряй важную информацию. Ответ на русском языке."
        )

        try:
            from bot.services.llm import FALLBACK_MESSAGE

            summary = await llm_service.generate_response(
                tenant=tenant,
                user_message=f"Диалог для суммаризации:\n\n{conversation_text}",
                system_prompt=summarization_prompt,
            )

            if summary == FALLBACK_MESSAGE or summary == "NO_ANSWER":
                logger.warning("Compaction failed: LLM returned fallback for user %d", user_id)
                return False

            await self.repo.save_summary(
                user_id, chat_id, tenant_id, summary, from_id, to_id
            )

            logger.info(
                "Compacted %d messages for user %d tenant %s (ids %d-%d)",
                len(to_summarize), user_id, tenant_id, from_id, to_id,
            )
            return True

        except Exception as e:
            logger.error("Compaction failed for user %d: %s", user_id, e)
            return False

    async def add_faq_candidate(
        self, tenant_id: UUID, question: str, answer: str, message_id: int
    ):
        await self.repo.add_faq_candidate(tenant_id, question, answer, message_id)

    async def get_faq_candidates(self, tenant_id: UUID, limit: int = 20):
        return await self.repo.get_faq_candidates(tenant_id, limit)
