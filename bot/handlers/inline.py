"""Tenant-aware inline query handler.

Uses user_settings.current_tenant_id to scope searches.
If no project selected, returns an error result.
"""

import hashlib
import logging

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from bot.config import settings
from bot.core.tenant import TenantContext
from bot.services.llm import FALLBACK_MESSAGE
from bot.texts import t
from bot.utils.formatting import truncate_response

logger = logging.getLogger(__name__)

router = Router(name="inline")

MAX_INLINE_RESPONSE_LENGTH = 4096


def build_inline_system_prompt(chunks: list[dict], tenant: TenantContext) -> str:
    if not chunks:
        return ""
    formatted = [chunk["chunk_text"] for chunk in chunks]
    context_block = "ДОКУМЕНТАЦИЯ:\n\n" + "\n\n---\n\n".join(formatted)

    return (
        f"Ты -- AI-ассистент проекта {tenant.project_name}.\n\n"
        f"КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:\n"
        f"1. Используй ТОЛЬКО информацию из раздела ДОКУМЕНТАЦИЯ ниже. "
        f"НЕ используй собственные знания или догадки.\n"
        f"2. Если в документации НЕТ ответа — скажи \"В документации этой информации нет\". "
        f"НЕ ПЫТАЙСЯ угадать.\n"
        f"3. НИКОГДА не выдумывай факты, которых нет в документации.\n"
        f"4. Передавай информацию ДОСЛОВНО из документации.\n"
        f"5. НЕ ссылайся на файлы документации.\n"
        f"6. Отвечай на том же языке, на котором задан вопрос. Кратко и по делу.\n\n"
        f"{context_block}"
    )


@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery, lang: str = "ru"):
    """Handle inline queries with tenant isolation."""
    from bot import state

    query = inline_query.query.strip()
    if len(query) < 3:
        return

    user_id = inline_query.from_user.id

    # Resolve tenant from user settings
    user_settings = await state.user_settings_repo.get(user_id)
    if not user_settings or not user_settings["current_tenant_id"]:
        result = InlineQueryResultArticle(
            id=hashlib.md5(query.encode()).hexdigest(),
            title=t("inline_no_project_title", lang),
            description=t("inline_no_project_desc", lang),
            input_message_content=InputTextMessageContent(
                message_text=t("inline_no_project_text", lang),
            ),
        )
        await inline_query.answer([result], cache_time=10)
        return

    tenant_record = await state.tenant_repo.get(user_settings["current_tenant_id"])
    if not tenant_record or tenant_record["status"] not in ("trial", "active"):
        result = InlineQueryResultArticle(
            id=hashlib.md5(query.encode()).hexdigest(),
            title=t("inline_unavailable_title", lang),
            description=t("inline_unavailable_desc", lang),
            input_message_content=InputTextMessageContent(
                message_text=t("inline_unavailable_text", lang),
            ),
        )
        await inline_query.answer([result], cache_time=10)
        return

    tenant = TenantContext.from_record(tenant_record)

    logger.info("Inline query from user %d (tenant=%s): %s", user_id, tenant.tenant_id, query[:100])

    # Translate query for KB search if user writes in a different language
    search_query = query
    if not state.llm_service.is_cyrillic(query):
        from bot.core.encryption import decrypt_api_key
        api_key = decrypt_api_key(tenant.openrouter_api_key)
        translated = await state.llm_service.translate_for_search(query, "ru", api_key)
        if translated:
            search_query = translated

    # Search KB with tenant isolation
    chunks = await state.kb_service.search_for_context(
        query=search_query,
        tenant_id=tenant.tenant_id,
        threshold=settings.relevance_threshold,
        max_chunks=settings.max_context_chunks,
    )

    if not chunks:
        result = InlineQueryResultArticle(
            id=hashlib.md5(query.encode()).hexdigest(),
            title=t("inline_no_answer_title", lang),
            description=t("inline_no_answer_desc", lang),
            input_message_content=InputTextMessageContent(
                message_text=t("inline_no_answer_text", lang, query=query),
            ),
        )
        await inline_query.answer([result], cache_time=60)
        return

    # Generate response
    system_prompt = build_inline_system_prompt(chunks, tenant)
    answer = await state.llm_service.generate_response(
        tenant=tenant,
        user_message=query,
        system_prompt=system_prompt,
    )

    if answer == FALLBACK_MESSAGE or answer == "NO_ANSWER":
        result = InlineQueryResultArticle(
            id=hashlib.md5(query.encode()).hexdigest(),
            title=t("inline_error_title", lang),
            description=t("inline_error_desc", lang),
            input_message_content=InputTextMessageContent(
                message_text=FALLBACK_MESSAGE,
            ),
        )
        await inline_query.answer([result], cache_time=10)
        return

    answer = truncate_response(answer, MAX_INLINE_RESPONSE_LENGTH)

    result = InlineQueryResultArticle(
        id=hashlib.md5((query + answer[:50]).encode()).hexdigest(),
        title=t("inline_answer_title", lang, project_name=tenant.project_name),
        description=answer[:150],
        input_message_content=InputTextMessageContent(
            message_text=answer,
        ),
    )
    await inline_query.answer([result], cache_time=300)

    logger.info("Inline response for user %d: %d chars", user_id, len(answer))
