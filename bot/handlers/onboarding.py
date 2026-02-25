"""Onboarding FSM — 7-step tenant registration flow.

Steps:
1. OpenRouter API key (validated, message deleted, encrypted)
2. Project name (≤100 chars)
3. Group chat ID (bot membership verified, not taken)
4. Moderator @usernames
5. Rate limits (messages per minute / per day per user)
6. Persona/style document (optional, skip button)
7. Documentation files (optional, accumulate, done/skip buttons)

On completion: tenant created, 7-day trial started, documents ingested.
"""

import io
import logging
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.core.encryption import encrypt_api_key
from bot.services.document_parser import DocumentParser
from bot.texts import t

logger = logging.getLogger(__name__)

router = Router(name="onboarding")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class SetupStates(StatesGroup):
    waiting_api_key = State()
    waiting_project_name = State()
    waiting_chat_id = State()
    waiting_moderators = State()
    waiting_rate_limits = State()
    waiting_persona = State()
    waiting_documents = State()


# --- /start command ---

@router.message(Command("start"), F.chat.type == "private")
async def handle_start(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    """Entry point: language picker → owner main menu / new user welcome."""
    from bot import state as app_state

    user_id = message.from_user.id
    await state.clear()

    # Check if language has been set
    user_settings = await app_state.user_settings_repo.get(user_id)
    if not user_settings or user_settings.get("language") is None:
        lang_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="set_lang:ru"),
                InlineKeyboardButton(text="English", callback_data="set_lang:en"),
            ],
        ])
        await message.answer(t("lang_pick", lang), reply_markup=lang_kb)
        return

    # Language is set — proceed
    existing = await app_state.tenant_repo.get_by_owner(user_id)
    if existing:
        from bot.handlers.menu import build_main_menu
        await message.answer(
            t("welcome_back", lang, project_name=existing["project_name"]),
            reply_markup=build_main_menu(lang),
        )
        return

    # New user welcome
    welcome_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_create_project", lang), callback_data="start_setup")],
        [InlineKeyboardButton(text=t("btn_ask_question", lang), callback_data="start_ask")],
    ])
    await message.answer(t("welcome_new", lang), reply_markup=welcome_kb)


# --- Language selection ---

@router.callback_query(F.data.startswith("set_lang:"))
async def handle_set_language(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Handle language selection callback."""
    from bot import state as app_state

    await callback.answer()
    lang = callback.data.split(":", 1)[1]
    if lang not in ("ru", "en"):
        lang = "ru"

    user_id = callback.from_user.id
    await app_state.user_settings_repo.update_language(user_id, lang)

    # Invalidate Redis cache
    if app_state.redis:
        await app_state.redis.delete(f"user:lang:{user_id}")

    await callback.message.edit_text(t("lang_set", lang))

    # Continue with start flow
    existing = await app_state.tenant_repo.get_by_owner(user_id)
    if existing:
        from bot.handlers.menu import build_main_menu
        await callback.message.answer(
            t("welcome_back", lang, project_name=existing["project_name"]),
            reply_markup=build_main_menu(lang),
        )
        return

    welcome_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_create_project", lang), callback_data="start_setup")],
        [InlineKeyboardButton(text=t("btn_ask_question", lang), callback_data="start_ask")],
    ])
    await callback.message.answer(t("welcome_new", lang), reply_markup=welcome_kb)


# --- /lang command ---

@router.message(Command("lang"), F.chat.type == "private")
async def handle_lang_command(message: Message, lang: str = "ru"):
    """Show language picker."""
    lang_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Русский", callback_data="set_lang:ru"),
            InlineKeyboardButton(text="English", callback_data="set_lang:en"),
        ],
    ])
    await message.answer(t("lang_pick", lang), reply_markup=lang_kb)


@router.callback_query(F.data == "start_setup")
async def start_setup(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    """Begin onboarding flow."""
    await callback.answer()
    await state.set_state(SetupStates.waiting_api_key)
    await callback.message.edit_text(t("step1_prompt", lang))


@router.callback_query(F.data == "start_ask")
async def start_ask(callback: CallbackQuery, lang: str = "ru"):
    """Show project selector for regular users."""
    await callback.answer()
    from bot.handlers.private import show_project_selector
    await show_project_selector(callback.message, lang=lang)


# --- Step 0: API Key ---

@router.message(SetupStates.waiting_api_key, F.text)
async def process_api_key(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    from bot import state as app_state

    api_key = message.text.strip()

    # Delete message with API key immediately
    try:
        await message.delete()
    except Exception:
        pass

    # Validate key
    is_valid = await app_state.llm_service.validate_api_key(api_key)
    if not is_valid:
        await message.answer(t("api_key_invalid", lang))
        return

    # Encrypt and save to FSM state
    encrypted = encrypt_api_key(api_key)
    await state.update_data(api_key_encrypted=encrypted)

    await state.set_state(SetupStates.waiting_project_name)
    await message.answer(t("api_key_accepted", lang))


# --- Step 1: Project Name ---

@router.message(SetupStates.waiting_project_name, F.text)
async def process_project_name(message: Message, state: FSMContext, lang: str = "ru"):
    name = message.text.strip()

    if len(name) > 100:
        await message.answer(t("name_too_long", lang))
        return

    if len(name) < 2:
        await message.answer(t("name_too_short", lang))
        return

    await state.update_data(project_name=name)
    await state.set_state(SetupStates.waiting_chat_id)
    await message.answer(t("step3_prompt", lang, project_name=name))


# --- Step 2: Chat ID ---

@router.message(SetupStates.waiting_chat_id, F.text)
async def process_chat_id(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    from bot import state as app_state

    text = message.text.strip()

    # Parse chat ID
    try:
        chat_id = int(text)
    except ValueError:
        await message.answer(t("invalid_chat_id", lang))
        return

    # Check bot is an admin in the group
    try:
        chat = await bot.get_chat(chat_id)
        member = await bot.get_chat_member(chat_id, bot.id)
        if member.status in ("left", "kicked"):
            await message.answer(t("bot_not_in_group", lang))
            return
        if member.status not in ("administrator", "creator"):
            await message.answer(t("bot_not_admin", lang))
            return
    except Exception as e:
        logger.warning("Failed to verify group %d: %s", chat_id, e)
        await message.answer(t("group_verify_fail", lang, chat_id=chat_id, error=e))
        return

    # Check group not taken by another tenant
    existing = await app_state.tenant_repo.get_by_chat_id(chat_id)
    if existing:
        await message.answer(t("group_taken", lang))
        return

    chat_title = chat.title if hasattr(chat, "title") else None
    await state.update_data(chat_id=chat_id, chat_title=chat_title)

    skip_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="skip_moderators")],
    ])

    await state.set_state(SetupStates.waiting_moderators)
    await message.answer(
        t("step4_prompt", lang, chat_title=chat_title or chat_id),
        reply_markup=skip_kb,
    )


# --- Step 3: Moderators ---

@router.message(SetupStates.waiting_moderators, F.text)
async def process_moderators(message: Message, state: FSMContext, lang: str = "ru"):
    text = message.text.strip()

    # Parse @usernames
    usernames = []
    for word in text.split():
        word = word.strip().lstrip("@")
        if word:
            usernames.append(word)

    if not usernames:
        await message.answer(t("no_moderators", lang))
        return

    await state.update_data(moderators=usernames)
    prefix = t("mods_prefix", lang, mods=", ".join("@" + u for u in usernames))
    await _go_to_rate_limits(message, state, prefix, lang)


@router.callback_query(SetupStates.waiting_moderators, F.data == "skip_moderators")
async def skip_moderators(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await callback.answer()
    await state.update_data(moderators=[])
    await _go_to_rate_limits(callback.message, state, t("mods_skipped", lang), lang)


async def _go_to_rate_limits(message: Message, state: FSMContext, prefix: str, lang: str = "ru"):
    """Transition to rate limits step."""
    default_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_rate_default", lang), callback_data="rate_default")],
    ])

    await state.set_state(SetupStates.waiting_rate_limits)
    await message.answer(
        f"{prefix}{t('step5_prompt', lang)}",
        reply_markup=default_kb,
    )


# --- Step 5: Rate Limits ---

def _go_to_persona(state_text: str = "", lang: str = "ru") -> tuple[str, InlineKeyboardMarkup]:
    """Build persona step message and keyboard."""
    skip_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="skip_persona")],
    ])
    text = f"{state_text}{t('step6_prompt', lang)}"
    return text, skip_kb


@router.message(SetupStates.waiting_rate_limits, F.text)
async def process_rate_limits(message: Message, state: FSMContext, lang: str = "ru"):
    text = message.text.strip()
    parts = text.split()

    if len(parts) != 2:
        await message.answer(t("rate_format_error", lang))
        return

    try:
        per_minute = int(parts[0])
        per_day = int(parts[1])
    except ValueError:
        await message.answer(t("rate_not_integers", lang))
        return

    if per_minute < 1 or per_minute > 60:
        await message.answer(t("rate_minute_range", lang))
        return

    if per_day < 1 or per_day > 10000:
        await message.answer(t("rate_day_range", lang))
        return

    if per_day < per_minute:
        await message.answer(t("rate_day_less_minute", lang))
        return

    await state.update_data(rate_limit_per_minute=per_minute, rate_limit_per_day=per_day)

    await state.set_state(SetupStates.waiting_persona)
    prefix = t("rate_set", lang, per_minute=per_minute, per_day=per_day)
    text, skip_kb = _go_to_persona(prefix, lang)
    await message.answer(text, reply_markup=skip_kb)


@router.callback_query(SetupStates.waiting_rate_limits, F.data == "rate_default")
async def rate_default(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await callback.answer()
    await state.update_data(rate_limit_per_minute=5, rate_limit_per_day=50)

    await state.set_state(SetupStates.waiting_persona)
    prefix = t("rate_set_default", lang)
    text, skip_kb = _go_to_persona(prefix, lang)
    await callback.message.answer(text, reply_markup=skip_kb)


# --- Step 6: Persona ---

def _docs_step_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="skip_documents")],
    ])


@router.message(SetupStates.waiting_persona, F.document)
async def process_persona_doc(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    doc = message.document

    if doc.file_size > 1 * 1024 * 1024:  # 1 MB limit for persona
        await message.answer(t("persona_file_too_big", lang))
        return

    # Download and parse
    file = await bot.download(doc, destination=io.BytesIO())
    content = file.read()

    try:
        text = DocumentParser.parse(doc.file_name, content)
    except Exception:
        await message.answer(t("persona_parse_error", lang))
        return

    await state.update_data(persona_doc=text)

    await state.set_state(SetupStates.waiting_documents)
    await message.answer(
        t("persona_loaded", lang) + t("step7_prompt", lang),
        reply_markup=_docs_step_kb(lang),
    )


@router.message(SetupStates.waiting_persona, F.text)
async def process_persona_text(message: Message, state: FSMContext, lang: str = "ru"):
    """Accept persona/style as plain text message."""
    text = message.text.strip()

    if len(text) < 10:
        await message.answer(t("persona_too_short", lang))
        return

    if len(text) > 5000:
        await message.answer(t("persona_too_long", lang))
        return

    await state.update_data(persona_doc=text)

    await state.set_state(SetupStates.waiting_documents)
    await message.answer(
        t("persona_loaded", lang) + t("step7_prompt", lang),
        reply_markup=_docs_step_kb(lang),
    )


@router.callback_query(SetupStates.waiting_persona, F.data == "skip_persona")
async def skip_persona(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await callback.answer()
    await state.update_data(persona_doc=None)

    await state.set_state(SetupStates.waiting_documents)
    await callback.message.answer(
        t("step7_prompt_max", lang),
        reply_markup=_docs_step_kb(lang),
    )


# --- Step 5: Documents ---

@router.message(SetupStates.waiting_documents, F.document)
async def process_document(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    import asyncio
    from bot.config import settings
    from bot.utils.text_splitter import RecursiveCharacterTextSplitter

    doc = message.document

    if doc.file_size > 20 * 1024 * 1024:
        await message.answer(t("doc_too_big", lang))
        return

    ext = "." + doc.file_name.rsplit(".", 1)[-1].lower() if "." in doc.file_name else ""
    if ext not in DocumentParser.SUPPORTED_EXTENSIONS:
        await message.answer(
            t("doc_unsupported", lang, formats=", ".join(DocumentParser.SUPPORTED_EXTENSIONS))
        )
        return

    # Download file
    file = await bot.download(doc, destination=io.BytesIO())
    content = file.read()

    # Parse and count chunks immediately
    try:
        text = await asyncio.to_thread(DocumentParser.parse, doc.file_name, content)
    except Exception:
        await message.answer(t("doc_parse_error", lang))
        return

    if not text or len(text.strip()) < 50:
        await message.answer(t("doc_too_short", lang))
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = splitter.split_text(text)
    chunk_count = len(chunks)

    # Accumulate in FSM state
    data = await state.get_data()
    pending_docs = data.get("pending_docs", [])
    total_chunks = data.get("pending_total_chunks", 0)
    pending_docs.append({"filename": doc.file_name, "content": content.hex()})
    total_chunks += chunk_count
    await state.update_data(pending_docs=pending_docs, pending_total_chunks=total_chunks)

    done_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_done", lang), callback_data="docs_done")],
    ])

    await message.answer(
        t("doc_added", lang,
          filename=doc.file_name,
          chunks=chunk_count,
          total_files=len(pending_docs),
          total_chunks=total_chunks),
        reply_markup=done_kb,
    )


@router.callback_query(SetupStates.waiting_documents, F.data == "docs_done")
async def docs_done(callback: CallbackQuery, state: FSMContext, bot: Bot, lang: str = "ru"):
    await callback.answer()
    await finish_onboarding(callback.message, state, bot, callback.from_user.id, lang)


@router.callback_query(SetupStates.waiting_documents, F.data == "skip_documents")
async def skip_documents(callback: CallbackQuery, state: FSMContext, bot: Bot, lang: str = "ru"):
    await callback.answer()
    await state.update_data(pending_docs=[])
    await finish_onboarding(callback.message, state, bot, callback.from_user.id, lang)


# --- Finish onboarding ---

async def finish_onboarding(message: Message, state: FSMContext, bot: Bot, user_id: int, lang: str = "ru"):
    """Create tenant, trial subscription, ingest documents, show main menu."""
    from bot import state as app_state

    data = await state.get_data()

    # 1. Create tenant
    tenant_record = await app_state.tenant_repo.create(
        owner_user_id=user_id,
        project_name=data["project_name"],
        chat_id=data["chat_id"],
        chat_title=data.get("chat_title"),
        openrouter_api_key=data["api_key_encrypted"],
        moderator_usernames=data.get("moderators", []),
        persona_doc=data.get("persona_doc"),
        status="trial",
        rate_limit_per_minute=data.get("rate_limit_per_minute", 5),
        rate_limit_per_day=data.get("rate_limit_per_day", 50),
    )
    tenant_id = tenant_record["id"]

    # 2. Create 7-day trial subscription
    await app_state.subscription_repo.create_trial(tenant_id, days=7)

    # 3. Set user_settings for the owner
    await app_state.user_settings_repo.set_tenant(user_id, tenant_id)

    # 4. Ingest pending documents
    pending_docs = data.get("pending_docs", [])
    ingested_count = 0
    total_chunks = 0

    for doc_data in pending_docs:
        try:
            content = bytes.fromhex(doc_data["content"])
            result = await app_state.kb_service.ingest_document(
                tenant_id=tenant_id,
                filename=doc_data["filename"],
                content=content,
                uploaded_by=user_id,
            )
            ingested_count += 1
            total_chunks += result["chunk_count"]
        except Exception as e:
            logger.error("Failed to ingest %s during onboarding: %s", doc_data["filename"], e)

    # 5. Invalidate Redis cache
    if app_state.redis and data.get("chat_id"):
        await app_state.redis.delete(f"tenant:chat:{data['chat_id']}")

    # 6. Clear FSM state
    await state.clear()

    # 7. Show completion + main menu
    from bot.handlers.menu import build_main_menu

    doc_text = ""
    if ingested_count:
        doc_text = t("docs_ingested", lang, count=ingested_count, chunks=total_chunks)

    mods = data.get("moderators", [])
    mods_text = ", ".join("@" + u for u in mods) if mods else "—"

    await message.answer(
        t("setup_complete", lang,
          project_name=data["project_name"],
          chat_title=data.get("chat_title", data["chat_id"]),
          moderators=mods_text,
          doc_text=doc_text),
        reply_markup=build_main_menu(lang),
    )
