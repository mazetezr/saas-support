"""Tenant-aware group chat handler.

Monitors group/supergroup messages, detects questions via heuristics,
and responds with RAG pipeline scoped to the tenant's documents.
Includes status checks, Redis rate limiting, and moderator tagging.
"""

import logging
import re

from aiogram import Bot, F, Router
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from bot.config import settings
from bot.core.tenant import TenantContext
from bot.services.llm import FALLBACK_MESSAGE
from bot.texts import t
from bot.utils.formatting import safe_reply

logger = logging.getLogger(__name__)

router = Router(name="group")

MAX_GROUP_RESPONSE_LENGTH = 4096
NO_ANSWER_MARKER = "NO_ANSWER"

# Question detection heuristics (from source)
_QUESTION_WORDS = re.compile(
    r"\b(как|что|где|когда|почему|зачем|сколько|какой|какая|какие|какое|"
    r"кто|чем|можно\s+ли|есть\s+ли|куда|откуда|чей|чья|чьё)\b",
    re.IGNORECASE,
)
_ERROR_KEYWORDS = re.compile(
    r"\b(ошибка|ошибку|error|не\s+работает|не\s+могу|проблема|баг|bug|fail|сломал|crash)\b",
    re.IGNORECASE,
)
_HELP_KEYWORDS = re.compile(
    r"\b(помощь|help|подскажите|подскажи|помогите|помоги)\b",
    re.IGNORECASE,
)
_FOLLOWUP_KEYWORDS = re.compile(
    r"\b(продолжи|дальше|дописал|не полностью|не дописал|не закончил|не весь|"
    r"обрезал|обрезано|покажи\s+ещё|покажи\s+еще|а\s+остальное|а\s+остальные|"
    r"ещё|еще|continue|go\s+on)\b",
    re.IGNORECASE,
)


def is_question(text: str, bot_username: str | None = None) -> bool:
    """Detect if a message is likely a question using heuristics."""
    if bot_username and f"@{bot_username}" in text:
        return True
    if "?" in text:
        return True
    if _QUESTION_WORDS.search(text):
        return True
    if _ERROR_KEYWORDS.search(text):
        return True
    if _HELP_KEYWORDS.search(text):
        return True
    if _FOLLOWUP_KEYWORDS.search(text):
        return True
    return False


def build_group_system_prompt(chunks: list[dict], tenant: TenantContext) -> str:
    """Build system prompt with tenant's project name and persona."""
    if not chunks:
        context_block = "ДОКУМЕНТАЦИЯ: Ничего не найдено."
    else:
        formatted = [chunk["chunk_text"] for chunk in chunks]
        context_block = "ДОКУМЕНТАЦИЯ:\n\n" + "\n\n---\n\n".join(formatted)

    persona = ""
    if tenant.persona_doc:
        persona = f"\n\nСтиль общения:\n{tenant.persona_doc}\n"

    return (
        f"Ты -- AI-ассистент технической поддержки проекта {tenant.project_name} "
        f"в групповом чате.\n"
        f"{persona}\n"
        f"ПРАВИЛА:\n"
        f"1. Отвечай ТОЛЬКО на основе раздела ДОКУМЕНТАЦИЯ ниже. "
        f"Если информация есть в документации — используй её для ответа, даже если она разбросана по нескольким фрагментам.\n"
        f"2. Ответь ровно одним словом NO_ANSWER только если в документации СОВСЕМ НЕТ информации по теме вопроса.\n"
        f"3. НЕ выдумывай факты, числа, названия или механики, которых нет в документации.\n"
        f"4. Давай ПОЛНЫЙ ответ — перечисляй ВСЕ пункты и детали из документации.\n"
        f"5. НЕ ссылайся на файлы документации.\n"
        f"6. Если пользователь реплаит на твоё сообщение — учитывай контекст.\n"
        f"7. ВСЕГДА отвечай на том языке, на котором пользователь задал вопрос. "
        f"Документация может быть на другом языке — переводи.\n\n"
        f"{context_block}"
    )


async def _get_reply_context(message: Message, bot: Bot) -> list[dict]:
    """Extract conversation context from reply chain."""
    context = []
    reply = message.reply_to_message
    if not reply or not reply.text:
        return context

    bot_info = await bot.get_me()

    if reply.from_user and reply.from_user.id == bot_info.id:
        if reply.reply_to_message and reply.reply_to_message.text:
            context.append({"role": "user", "content": reply.reply_to_message.text})
        context.append({"role": "assistant", "content": reply.text})
    else:
        context.append({"role": "user", "content": reply.text})

    return context


async def _is_bot_admin(bot: Bot, chat_id: int) -> bool:
    """Check if bot is admin in the group, with Redis caching (5 min TTL)."""
    from bot import state

    cache_key = f"bot:admin:{chat_id}"

    # Check cache
    if state.redis:
        cached = await state.redis.get(cache_key)
        if cached is not None:
            return cached == "1"

    # Query Telegram API
    try:
        member = await bot.get_chat_member(chat_id, bot.id)
        is_admin = member.status in ("administrator", "creator")
    except Exception:
        is_admin = False

    # Cache result for 5 minutes
    if state.redis:
        await state.redis.setex(cache_key, 300, "1" if is_admin else "0")

    return is_admin


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def handle_group_message(message: Message, bot: Bot, tenant: TenantContext | None = None, lang: str = "ru"):
    """Handle group text messages with tenant isolation."""
    from bot import state

    # --- Tenant status gate ---
    if not tenant:
        return
    if tenant.status not in ("trial", "active"):
        return

    # --- Bot must be admin to work in the group ---
    if not await _is_bot_admin(bot, message.chat.id):
        return

    text = message.text
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Check if reply to bot
    is_reply_to_bot = False
    if message.reply_to_message and message.reply_to_message.from_user:
        bot_info = await bot.get_me()
        is_reply_to_bot = message.reply_to_message.from_user.id == bot_info.id

    # Question detection
    if not is_reply_to_bot and not is_question(text, state.bot_username):
        return

    logger.info("Group question in chat %d (tenant=%s)", chat_id, tenant.tenant_id)

    # Search KB with tenant isolation
    chunks = await state.kb_service.search_for_context(
        query=text,
        tenant_id=tenant.tenant_id,
        threshold=tenant.relevance_threshold or settings.group_relevance_threshold,
        max_chunks=settings.max_context_chunks,
    )

    if not chunks and not is_reply_to_bot:
        return

    # Build prompt and generate response
    system_prompt = build_group_system_prompt(chunks, tenant)

    # For replies to bot — use reply chain as context.
    # For standalone questions — rely only on documentation (group history is noisy).
    reply_context = await _get_reply_context(message, bot) if is_reply_to_bot else []

    logger.info("History for chat %d: %d messages (reply=%s)", chat_id, len(reply_context), is_reply_to_bot)

    async with ChatActionSender.typing(chat_id=chat_id, bot=bot):
        answer = await state.llm_service.generate_response(
            tenant=tenant,
            user_message=text,
            system_prompt=system_prompt,
            history=reply_context if reply_context else None,
        )

    # Check for NO_ANSWER — tag moderators
    logger.info("LLM answer for chat %d: %s", chat_id, answer[:200])
    if NO_ANSWER_MARKER in answer or answer == FALLBACK_MESSAGE:
        logger.warning("NO_ANSWER in chat %d, chunks=%d, query='%s'", chat_id, len(chunks), text[:100])
        if NO_ANSWER_MARKER in answer and tenant.moderator_usernames:
            tags = " ".join(f"@{u}" for u in tenant.moderator_usernames)
            await message.reply(t("group_no_answer", lang, tags=tags))
        return

    # Send response
    await safe_reply(message, answer, as_reply=True)

    # Save assistant response
    await state.conv_service.save_message(
        tenant_id=tenant.tenant_id,
        user_id=user_id,
        chat_id=chat_id,
        chat_type="group",
        role="assistant",
        content=answer,
    )

    logger.info("Group response in chat %d: %d chars", chat_id, len(answer))
