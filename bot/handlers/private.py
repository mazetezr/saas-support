"""Tenant-aware private message handler.

For regular users: project selection + RAG pipeline.
For owners: handled by menu.py (this router is lower priority).
Onboarding is handled by onboarding.py (higher priority).
"""

import asyncio
import hashlib
import logging
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.chat_action import ChatActionSender

from bot.config import settings
from bot.core.tenant import TenantContext
from bot.services.llm import FALLBACK_MESSAGE
from bot.texts import t
from bot.utils.formatting import safe_reply

logger = logging.getLogger(__name__)

router = Router(name="private")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

MAX_RESPONSE_LENGTH = 4096
PROJECTS_PER_PAGE = 10


def build_system_prompt(chunks: list[dict], tenant: TenantContext) -> str:
    """Build system prompt with tenant context."""
    if not chunks:
        context_block = (
            "ДОКУМЕНТАЦИЯ: Ничего не найдено.\n"
            "ИНСТРУКЦИЯ: Ответь пользователю, что в документации нет информации по этому вопросу. "
            "НЕ ПЫТАЙСЯ ответить на вопрос самостоятельно."
        )
    else:
        formatted = [chunk["chunk_text"] for chunk in chunks]
        context_block = "ДОКУМЕНТАЦИЯ:\n\n" + "\n\n---\n\n".join(formatted)

    persona = ""
    if tenant.persona_doc:
        persona = f"\n\nСтиль общения:\n{tenant.persona_doc}\n"

    return (
        f"Ты -- AI-ассистент технической поддержки проекта {tenant.project_name}.\n"
        f"{persona}\n"
        f"ПРАВИЛА:\n"
        f"1. Отвечай ТОЛЬКО на основе раздела ДОКУМЕНТАЦИЯ ниже. "
        f"Если информация есть в документации — используй её для ответа, даже если она разбросана по нескольким фрагментам.\n"
        f"2. Если в документации СОВСЕМ НЕТ информации по теме вопроса — ответь: "
        f"\"В документации нет информации по этому вопросу.\".\n"
        f"3. НЕ выдумывай факты, числа, названия или механики, которых нет в документации.\n"
        f"4. Давай ПОЛНЫЙ ответ — перечисляй ВСЕ пункты и детали из документации.\n"
        f"5. НЕ ссылайся на файлы или разделы документации.\n"
        f"6. Учитывай контекст предыдущего диалога.\n"
        f"7. ВСЕГДА отвечай на том языке, на котором пользователь задал вопрос. "
        f"Документация может быть на другом языке — переводи.\n\n"
        f"{context_block}"
    )


async def show_project_selector(message: Message, page: int = 0, lang: str = "ru"):
    """Show paginated list of active projects for user to select."""
    from bot import state

    tenants = await state.tenant_repo.get_all_active()
    if not tenants:
        await message.answer(t("no_projects", lang))
        return

    total = len(tenants)
    total_pages = (total + PROJECTS_PER_PAGE - 1) // PROJECTS_PER_PAGE
    page = max(0, min(page, total_pages - 1))

    start = page * PROJECTS_PER_PAGE
    end = start + PROJECTS_PER_PAGE
    page_tenants = tenants[start:end]

    # Build buttons — 2 per row
    buttons = []
    row = []
    for tn in page_tenants:
        row.append(InlineKeyboardButton(
            text=tn["project_name"],
            callback_data=f"select_project:{tn['id']}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀", callback_data=f"projects_page:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶", callback_data=f"projects_page:{page + 1}"))
        buttons.append(nav)

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(t("choose_project", lang), reply_markup=kb)


# --- /switch command ---

@router.message(Command("switch"))
async def handle_switch(message: Message, lang: str = "ru"):
    """Reset project selection and show selector."""
    from bot import state

    user_id = message.from_user.id
    await state.user_settings_repo.clear_tenant(user_id)
    await show_project_selector(message, lang=lang)


# --- /help command ---

@router.message(Command("help"))
async def handle_help(message: Message, lang: str = "ru"):
    await message.answer(t("help_text", lang))


# --- Project selection callbacks ---

@router.callback_query(F.data.startswith("select_project:"))
async def handle_select_project(callback: CallbackQuery, lang: str = "ru"):
    from bot import state

    await callback.answer()

    tenant_id_str = callback.data.split(":", 1)[1]
    try:
        tenant_id = UUID(tenant_id_str)
    except ValueError:
        return

    user_id = callback.from_user.id

    tenant = await state.tenant_repo.get(tenant_id)
    if not tenant:
        await callback.message.answer(t("project_not_found", lang))
        return

    await state.user_settings_repo.set_tenant(user_id, tenant_id)
    await callback.message.answer(
        t("project_selected", lang, project_name=tenant["project_name"])
    )


@router.callback_query(F.data.startswith("projects_page:"))
async def handle_projects_page(callback: CallbackQuery, lang: str = "ru"):
    await callback.answer()
    page = int(callback.data.split(":", 1)[1])
    await show_project_selector(callback.message, page, lang=lang)


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery):
    await callback.answer()


# --- Main message handler ---

@router.message(F.text)
async def handle_private_message(message: Message, bot: Bot, tenant: TenantContext | None = None, lang: str = "ru"):
    """Handle private text messages with tenant-aware RAG pipeline."""
    from bot import state

    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text

    # If no tenant selected — show project selector
    if not tenant:
        await show_project_selector(message, lang=lang)
        return

    # Check tenant is active
    if tenant.status not in ("trial", "active"):
        await message.answer(t("project_unavailable", lang))
        return

    try:
        # Search KB with tenant isolation
        chunks = await state.kb_service.search_for_context(
            query=text,
            tenant_id=tenant.tenant_id,
            threshold=settings.relevance_threshold,
            max_chunks=settings.max_context_chunks,
        )

        # Get conversation history
        history = await state.conv_service.get_context(user_id, chat_id, tenant.tenant_id)

        # Build system prompt
        system_prompt = build_system_prompt(chunks, tenant)

        logger.info(
            "User %d (tenant=%s): %d chunks, %d history",
            user_id, tenant.tenant_id, len(chunks), len(history),
        )

        # Generate response
        async with ChatActionSender.typing(chat_id=chat_id, bot=bot):
            answer = await state.llm_service.generate_response(
                tenant=tenant,
                user_message=text,
                system_prompt=system_prompt,
                history=history,
            )

        await safe_reply(message, answer)

        # Save assistant response
        if answer != FALLBACK_MESSAGE and answer != "NO_ANSWER":
            msg_id = await state.conv_service.save_message(
                tenant_id=tenant.tenant_id,
                user_id=user_id,
                chat_id=chat_id,
                chat_type="private",
                role="assistant",
                content=answer,
            )

            # FAQ candidate
            if "?" in text or len(text.split()) >= 3:
                try:
                    await state.conv_service.add_faq_candidate(
                        tenant_id=tenant.tenant_id,
                        question=text,
                        answer=answer,
                        message_id=msg_id or 0,
                    )
                except Exception:
                    logger.debug("FAQ candidate save failed", exc_info=True)

            # Auto-compaction
            count = await state.conv_service.count_uncompacted_messages(
                user_id, chat_id, tenant.tenant_id
            )
            if count >= settings.compact_after_messages:
                asyncio.create_task(
                    state.conv_service.compact_conversation(
                        user_id, chat_id, tenant.tenant_id, tenant, state.llm_service
                    )
                )

    except Exception as e:
        logger.exception("Error in private handler for user %d: %s", user_id, e)
        await message.answer(t("processing_error", lang))
