"""Main menu and settings handlers for tenant owners.

Provides InlineKeyboardMarkup menus and settings management:
- Main menu: Settings / Subscription
- Settings: Change group, Moderators, Bot style, Documents, Back
"""

import io
import logging
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.core.tenant import TenantContext
from bot.services.document_parser import DocumentParser
from bot.texts import t

logger = logging.getLogger(__name__)

router = Router(name="menu")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


# --- Inline Keyboards (now functions) ---

def build_main_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("btn_settings", lang), callback_data="menu_settings"),
            InlineKeyboardButton(text=t("btn_subscription", lang), callback_data="menu_subscription"),
        ],
    ])


def build_settings_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("btn_change_group", lang), callback_data="set_group"),
            InlineKeyboardButton(text=t("btn_moderators", lang), callback_data="set_mods"),
        ],
        [
            InlineKeyboardButton(text=t("btn_bot_style", lang), callback_data="set_persona"),
            InlineKeyboardButton(text=t("btn_documents", lang), callback_data="set_docs"),
        ],
        [
            InlineKeyboardButton(text=t("btn_rate_limits", lang), callback_data="set_rate_limits"),
        ],
        [
            InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_back"),
        ],
    ])


class SettingsStates(StatesGroup):
    waiting_new_chat_id = State()
    waiting_new_moderators = State()
    waiting_new_persona = State()
    waiting_new_document = State()
    waiting_new_rate_limits = State()


# --- Helper ---

async def _get_owner_tenant(message_or_callback, app_state) -> TenantContext | None:
    """Get tenant if user is owner. Returns None otherwise."""
    if isinstance(message_or_callback, CallbackQuery):
        user_id = message_or_callback.from_user.id
    else:
        user_id = message_or_callback.from_user.id

    record = await app_state.tenant_repo.get_by_owner(user_id)
    if record:
        return TenantContext.from_record(record)
    return None


# --- Main Menu ---

@router.callback_query(F.data == "menu_settings")
async def handle_settings(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()
    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    await callback.message.edit_text(t("settings_title", lang), reply_markup=build_settings_menu(lang))


@router.callback_query(F.data == "menu_back")
async def handle_back(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()
    await state.clear()

    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    await callback.message.edit_text(
        t("menu_back_text", lang, project_name=tenant.project_name, status=tenant.status),
        reply_markup=build_main_menu(lang),
    )


# --- Change Group ---

@router.callback_query(F.data == "set_group")
async def handle_change_group(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()
    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    await state.set_state(SettingsStates.waiting_new_chat_id)
    current = tenant.chat_title or tenant.chat_id
    await callback.message.edit_text(
        t("change_group_prompt", lang, current=current),
    )


@router.message(SettingsStates.waiting_new_chat_id, F.text)
async def process_new_chat_id(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    from bot import state as app_state

    tenant = await _get_owner_tenant(message, app_state)
    if not tenant:
        return

    try:
        new_chat_id = int(message.text.strip())
    except ValueError:
        await message.answer(t("invalid_group_id", lang))
        return

    # Check bot is an admin in the group
    try:
        chat = await bot.get_chat(new_chat_id)
        member = await bot.get_chat_member(new_chat_id, bot.id)
        if member.status in ("left", "kicked"):
            await message.answer(t("bot_not_in_group", lang))
            return
        if member.status not in ("administrator", "creator"):
            await message.answer(t("bot_not_admin", lang))
            return
    except Exception as e:
        logger.warning("Failed to verify group %d: %s", new_chat_id, e)
        await message.answer(t("group_verify_fail", lang, chat_id=new_chat_id, error=e))
        return

    # Check not taken
    existing = await app_state.tenant_repo.get_by_chat_id(new_chat_id)
    if existing and existing["id"] != tenant.tenant_id:
        await message.answer(t("group_taken", lang))
        return

    # Invalidate old cache
    if app_state.redis and tenant.chat_id:
        await app_state.redis.delete(f"tenant:chat:{tenant.chat_id}")

    # Update
    chat_title = chat.title if hasattr(chat, "title") else None
    await app_state.tenant_repo.update_chat(tenant.tenant_id, new_chat_id, chat_title)

    # Invalidate new cache
    if app_state.redis:
        await app_state.redis.delete(f"tenant:chat:{new_chat_id}")

    await state.clear()
    await message.answer(
        t("group_updated", lang, chat_title=chat_title or new_chat_id),
        reply_markup=build_settings_menu(lang),
    )


# --- Moderators ---

@router.callback_query(F.data == "set_mods")
async def handle_moderators(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()
    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    mods = tenant.moderator_usernames
    mods_text = ", ".join(f"@{u}" for u in mods) if mods else t("mods_none", lang)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_edit", lang), callback_data="mod_edit")],
        [InlineKeyboardButton(text=t("btn_delete_all", lang), callback_data="mod_clear")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_settings")],
    ])

    await callback.message.edit_text(t("mods_label", lang, mods=mods_text), reply_markup=kb)


@router.callback_query(F.data == "mod_edit")
async def mod_edit(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_new_moderators)
    await callback.message.edit_text(t("mods_send_prompt", lang))


@router.message(SettingsStates.waiting_new_moderators, F.text)
async def process_new_moderators(message: Message, state: FSMContext, lang: str = "ru"):
    from bot import state as app_state

    tenant = await _get_owner_tenant(message, app_state)
    if not tenant:
        return

    usernames = [w.strip().lstrip("@") for w in message.text.split() if w.strip().lstrip("@")]
    if not usernames:
        await message.answer(t("mods_at_least_one", lang))
        return

    await app_state.tenant_repo.update_moderators(tenant.tenant_id, usernames)

    # Invalidate cache
    if app_state.redis and tenant.chat_id:
        await app_state.redis.delete(f"tenant:chat:{tenant.chat_id}")

    await state.clear()
    await message.answer(
        t("mods_updated", lang, mods=", ".join("@" + u for u in usernames)),
        reply_markup=build_settings_menu(lang),
    )


@router.callback_query(F.data == "mod_clear")
async def mod_clear(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()

    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    await app_state.tenant_repo.update_moderators(tenant.tenant_id, [])

    if app_state.redis and tenant.chat_id:
        await app_state.redis.delete(f"tenant:chat:{tenant.chat_id}")

    await callback.message.edit_text(t("mods_cleared", lang), reply_markup=build_settings_menu(lang))


# --- Rate Limits ---

@router.callback_query(F.data == "set_rate_limits")
async def handle_rate_limits(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()
    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_edit", lang), callback_data="rate_edit")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_settings")],
    ])

    await callback.message.edit_text(
        t("rate_limits_info", lang, per_minute=tenant.rate_limit_per_minute, per_day=tenant.rate_limit_per_day),
        reply_markup=kb,
    )


@router.callback_query(F.data == "rate_edit")
async def rate_edit(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_new_rate_limits)
    await callback.message.edit_text(t("rate_edit_prompt", lang))


@router.message(SettingsStates.waiting_new_rate_limits, F.text)
async def process_new_rate_limits(message: Message, state: FSMContext, lang: str = "ru"):
    from bot import state as app_state

    tenant = await _get_owner_tenant(message, app_state)
    if not tenant:
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer(t("rate_send_two_numbers", lang))
        return

    try:
        per_minute = int(parts[0])
        per_day = int(parts[1])
    except ValueError:
        await message.answer(t("rate_both_integers", lang))
        return

    if per_minute < 1 or per_minute > 60:
        await message.answer(t("rate_minute_1_60", lang))
        return
    if per_day < 1 or per_day > 10000:
        await message.answer(t("rate_day_1_10000", lang))
        return
    if per_day < per_minute:
        await message.answer(t("rate_day_less_minute", lang))
        return

    await app_state.tenant_repo.update_rate_limits(tenant.tenant_id, per_minute, per_day)

    # Invalidate cache so middleware picks up new limits
    if app_state.redis and tenant.chat_id:
        await app_state.redis.delete(f"tenant:chat:{tenant.chat_id}")

    await state.clear()
    await message.answer(
        t("rate_updated", lang, per_minute=per_minute, per_day=per_day),
        reply_markup=build_settings_menu(lang),
    )


# --- Bot Style ---

@router.callback_query(F.data == "set_persona")
async def handle_persona(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()
    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    status = t("persona_loaded_status", lang) if tenant.persona_doc else t("persona_not_set", lang)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_upload_new", lang), callback_data="persona_upload")],
        [InlineKeyboardButton(text=t("btn_delete", lang), callback_data="persona_delete")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_settings")],
    ])

    await callback.message.edit_text(t("persona_status", lang, status=status), reply_markup=kb)


@router.callback_query(F.data == "persona_upload")
async def persona_upload(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_new_persona)
    await callback.message.edit_text(t("persona_upload_prompt", lang))


@router.message(SettingsStates.waiting_new_persona, F.document)
async def process_new_persona(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    from bot import state as app_state

    tenant = await _get_owner_tenant(message, app_state)
    if not tenant:
        return

    doc = message.document
    if doc.file_size > 1 * 1024 * 1024:
        await message.answer(t("persona_file_big", lang))
        return

    file = await bot.download(doc, destination=io.BytesIO())
    content = file.read()

    try:
        text = DocumentParser.parse(doc.file_name, content)
    except Exception:
        await message.answer(t("persona_read_error", lang))
        return

    await app_state.tenant_repo.update_persona(tenant.tenant_id, text)

    if app_state.redis and tenant.chat_id:
        await app_state.redis.delete(f"tenant:chat:{tenant.chat_id}")

    await state.clear()
    await message.answer(t("persona_updated", lang), reply_markup=build_settings_menu(lang))


@router.message(SettingsStates.waiting_new_persona, F.text)
async def process_new_persona_text(message: Message, state: FSMContext, lang: str = "ru"):
    """Accept persona/style as plain text message."""
    from bot import state as app_state

    tenant = await _get_owner_tenant(message, app_state)
    if not tenant:
        return

    text = message.text.strip()

    if len(text) < 10:
        await message.answer(t("persona_short", lang))
        return

    if len(text) > 5000:
        await message.answer(t("persona_long", lang))
        return

    await app_state.tenant_repo.update_persona(tenant.tenant_id, text)

    if app_state.redis and tenant.chat_id:
        await app_state.redis.delete(f"tenant:chat:{tenant.chat_id}")

    await state.clear()
    await message.answer(t("persona_updated", lang), reply_markup=build_settings_menu(lang))


@router.callback_query(F.data == "persona_delete")
async def persona_delete(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()

    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    await app_state.tenant_repo.update_persona(tenant.tenant_id, None)

    if app_state.redis and tenant.chat_id:
        await app_state.redis.delete(f"tenant:chat:{tenant.chat_id}")

    await callback.message.edit_text(t("persona_deleted", lang), reply_markup=build_settings_menu(lang))


# --- Documents ---

@router.callback_query(F.data == "set_docs")
async def handle_documents(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()
    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    docs = await app_state.kb_service.list_documents(tenant.tenant_id)

    if docs:
        lines = [t("docs_list_title", lang)]
        for d in docs:
            lines.append(f"• <b>{d['filename']}</b> ({d['chunk_count']} chunks)")
        text = "\n".join(lines)
    else:
        text = t("docs_empty", lang)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_add", lang), callback_data="doc_add")],
        [InlineKeyboardButton(text=t("btn_delete", lang), callback_data="doc_delete_menu")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_settings")],
    ])

    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "doc_add")
async def doc_add(callback: CallbackQuery, state: FSMContext, lang: str = "ru"):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_new_document)
    await callback.message.edit_text(t("doc_add_prompt", lang))


@router.message(SettingsStates.waiting_new_document, F.document)
async def process_new_document(message: Message, state: FSMContext, bot: Bot, lang: str = "ru"):
    from bot import state as app_state

    tenant = await _get_owner_tenant(message, app_state)
    if not tenant:
        return

    doc = message.document

    if doc.file_size > 20 * 1024 * 1024:
        await message.answer(t("doc_file_big", lang))
        return

    ext = "." + doc.file_name.rsplit(".", 1)[-1].lower() if "." in doc.file_name else ""
    if ext not in DocumentParser.SUPPORTED_EXTENSIONS:
        await message.answer(
            t("doc_unsupported_fmt", lang, formats=", ".join(DocumentParser.SUPPORTED_EXTENSIONS))
        )
        return

    # Check plan limits
    current_chunks = await app_state.chunk_repo.count_by_tenant(tenant.tenant_id)
    sub = await app_state.subscription_repo.get_active(tenant.tenant_id)
    if sub and sub.get("max_chunks"):
        if current_chunks >= sub["max_chunks"]:
            await message.answer(t("doc_chunk_limit", lang, max_chunks=sub["max_chunks"]))
            await state.clear()
            return

    file = await bot.download(doc, destination=io.BytesIO())
    content = file.read()

    try:
        result = await app_state.kb_service.ingest_document(
            tenant_id=tenant.tenant_id,
            filename=doc.file_name,
            content=content,
            uploaded_by=message.from_user.id,
        )
        await state.clear()
        await message.answer(
            t("doc_uploaded", lang, filename=result["filename"], chunks=result["chunk_count"]),
            reply_markup=build_settings_menu(lang),
        )
    except ValueError as e:
        await message.answer(t("doc_upload_error_val", lang, error=e))
    except Exception as e:
        logger.error("Document upload failed: %s", e)
        await message.answer(t("doc_upload_error", lang))


@router.callback_query(F.data == "doc_delete_menu")
async def doc_delete_menu(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()

    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    docs = await app_state.kb_service.list_documents(tenant.tenant_id)
    if not docs:
        await callback.message.edit_text(t("doc_no_docs_delete", lang), reply_markup=build_settings_menu(lang))
        return

    buttons = []
    for d in docs:
        buttons.append([
            InlineKeyboardButton(
                text=f"X {d['filename']} ({d['chunk_count']})",
                callback_data=f"doc_del:{d['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="set_docs")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(t("doc_choose_delete", lang), reply_markup=kb)


@router.callback_query(F.data.startswith("doc_del:"))
async def doc_delete(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    await callback.answer()

    tenant = await _get_owner_tenant(callback, app_state)
    if not tenant:
        return

    doc_id_str = callback.data.split(":", 1)[1]
    try:
        doc_id = UUID(doc_id_str)
    except ValueError:
        await callback.message.edit_text(t("doc_invalid_id", lang), reply_markup=build_settings_menu(lang))
        return

    try:
        await app_state.kb_service.delete_document(doc_id, tenant.tenant_id)
        await callback.message.edit_text(t("doc_deleted", lang), reply_markup=build_settings_menu(lang))
    except ValueError as e:
        await callback.message.edit_text(t("doc_upload_error_val", lang, error=e), reply_markup=build_settings_menu(lang))
