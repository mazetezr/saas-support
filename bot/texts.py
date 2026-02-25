"""Centralized UI text translations (RU/EN).

Usage:
    from bot.texts import t
    msg = t("welcome_back", lang, project_name=name)
"""

from typing import Any

_TEXTS: dict[str, dict[str, str]] = {
    # ── Language picker ──
    "lang_pick": {
        "ru": "Выберите язык / Choose language:",
        "en": "Choose language / Выберите язык:",
    },
    "lang_set": {
        "ru": "Язык установлен: Русский",
        "en": "Language set: English",
    },

    # ── Onboarding: /start ──
    "welcome_back": {
        "ru": "Добро пожаловать обратно! Ваш проект: <b>{project_name}</b>",
        "en": "Welcome back! Your project: <b>{project_name}</b>",
    },
    "welcome_new": {
        "ru": "Добро пожаловать! Я бот AI-поддержки.\n\nВыберите, что хотите сделать:",
        "en": "Welcome! I'm an AI support bot.\n\nChoose what you'd like to do:",
    },
    "btn_create_project": {
        "ru": "Создать проект",
        "en": "Create project",
    },
    "btn_ask_question": {
        "ru": "Задать вопрос по проекту",
        "en": "Ask a project question",
    },

    # ── Onboarding: Step 1 — API key ──
    "step1_prompt": {
        "ru": (
            "Давайте настроим вашего AI-бота поддержки.\n\n"
            "<b>Шаг 1/7: API ключ OpenRouter</b>\n\n"
            "Отправьте ваш API ключ OpenRouter.\n"
            "Получить ключ можно на https://openrouter.ai/keys\n\n"
            "Убедитесь, что на аккаунте OpenRouter пополнен баланс "
            "(Credits -> Top up), иначе AI не сможет отвечать.\n\n"
            "Сообщение с ключом будет немедленно удалено для безопасности."
        ),
        "en": (
            "Let's set up your AI support bot.\n\n"
            "<b>Step 1/7: OpenRouter API Key</b>\n\n"
            "Send your OpenRouter API key.\n"
            "Get a key at https://openrouter.ai/keys\n\n"
            "Make sure your OpenRouter account has credits "
            "(Credits -> Top up), otherwise the AI won't be able to respond.\n\n"
            "The message with the key will be deleted immediately for security."
        ),
    },
    "api_key_invalid": {
        "ru": "API ключ недействителен. Пожалуйста, проверьте и отправьте ещё раз.",
        "en": "Invalid API key. Please check and send again.",
    },
    "api_key_accepted": {
        "ru": (
            "API ключ принят и зашифрован.\n\n"
            "<b>Шаг 2/7: Название проекта</b>\n\n"
            "Введите название вашего проекта (до 100 символов):"
        ),
        "en": (
            "API key accepted and encrypted.\n\n"
            "<b>Step 2/7: Project Name</b>\n\n"
            "Enter your project name (up to 100 characters):"
        ),
    },

    # ── Onboarding: Step 2 — Project name ──
    "name_too_long": {
        "ru": "Слишком длинное название. Максимум 100 символов.",
        "en": "Name is too long. Maximum 100 characters.",
    },
    "name_too_short": {
        "ru": "Слишком короткое название. Минимум 2 символа.",
        "en": "Name is too short. Minimum 2 characters.",
    },
    "step3_prompt": {
        "ru": (
            "Проект: <b>{project_name}</b>\n\n"
            "<b>Шаг 3/7: Группа Telegram</b>\n\n"
            "Добавьте бота в вашу группу <b>и сделайте его администратором</b>, "
            "затем отправьте ID группы.\n\n"
            "<b>Как узнать ID группы:</b>\n"
            "1. Откройте группу через Telegram Web — в адресной строке "
            "в конце URL будет число, добавьте к нему <code>-100</code> в начало\n"
            "2. Или в Telegram Desktop: Настройки → Продвинутые → "
            "Экспериментальные → Show Peer IDs — ID будет отображаться в профиле группы"
        ),
        "en": (
            "Project: <b>{project_name}</b>\n\n"
            "<b>Step 3/7: Telegram Group</b>\n\n"
            "Add the bot to your group <b>and make it an admin</b>, "
            "then send the group ID.\n\n"
            "<b>How to find the group ID:</b>\n"
            "1. Open the group in Telegram Web — at the end of the URL "
            "there will be a number, add <code>-100</code> at the beginning\n"
            "2. Or in Telegram Desktop: Settings → Advanced → "
            "Experimental → Show Peer IDs — the ID will appear in the group profile"
        ),
    },

    # ── Onboarding: Step 3 — Chat ID ──
    "invalid_chat_id": {
        "ru": "Пожалуйста, отправьте числовой ID группы (например, -1001234567890).",
        "en": "Please send a numeric group ID (e.g., -1001234567890).",
    },
    "bot_not_in_group": {
        "ru": "Бот не является участником этой группы. Сначала добавьте бота.",
        "en": "The bot is not a member of this group. Add the bot first.",
    },
    "bot_not_admin": {
        "ru": "Бот не является администратором этой группы. Сделайте бота админом и попробуйте снова.",
        "en": "The bot is not an admin in this group. Make the bot an admin and try again.",
    },
    "group_verify_fail": {
        "ru": (
            "Не удалось проверить группу (ID: {chat_id}).\n\n"
            "Убедитесь что:\n"
            "1. Бот добавлен в эту группу как администратор\n"
            "2. ID группы верный (начинается с -100)\n\n"
            "Ошибка: <code>{error}</code>"
        ),
        "en": (
            "Failed to verify group (ID: {chat_id}).\n\n"
            "Make sure that:\n"
            "1. The bot is added to this group as an admin\n"
            "2. The group ID is correct (starts with -100)\n\n"
            "Error: <code>{error}</code>"
        ),
    },
    "group_taken": {
        "ru": "Эта группа уже привязана к другому проекту.",
        "en": "This group is already linked to another project.",
    },

    # ── Onboarding: Step 4 — Moderators ──
    "step4_prompt": {
        "ru": (
            "Группа: <b>{chat_title}</b>\n\n"
            "<b>Шаг 4/7: Модераторы</b>\n\n"
            "Отправьте @username модераторов через пробел.\n"
            "Бот будет тегать их, когда не сможет ответить на вопрос.\n\n"
            "Пример: @admin1 @admin2\n\n"
            "Если не нужно — нажмите «Пропустить»."
        ),
        "en": (
            "Group: <b>{chat_title}</b>\n\n"
            "<b>Step 4/7: Moderators</b>\n\n"
            "Send moderator @usernames separated by spaces.\n"
            "The bot will tag them when it can't answer a question.\n\n"
            "Example: @admin1 @admin2\n\n"
            "If not needed — press \"Skip\"."
        ),
    },
    "btn_skip": {
        "ru": "Пропустить →",
        "en": "Skip →",
    },
    "no_moderators": {
        "ru": "Пожалуйста, укажите хотя бы одного модератора (@username).",
        "en": "Please specify at least one moderator (@username).",
    },
    "mods_prefix": {
        "ru": "Модераторы: {mods}\n\n",
        "en": "Moderators: {mods}\n\n",
    },
    "mods_skipped": {
        "ru": "Модераторы: пропущено\n\n",
        "en": "Moderators: skipped\n\n",
    },

    # ── Onboarding: Step 5 — Rate limits ──
    "step5_prompt": {
        "ru": (
            "<b>Шаг 5/7: Лимиты сообщений</b>\n\n"
            "Каждый вопрос пользователя тратит ваши кредиты OpenRouter. "
            "Чтобы защититься от спама, установите лимиты на каждого пользователя.\n\n"
            "Это <b>индивидуальный лимит</b> — у каждого пользователя свой счётчик. "
            "Например, если лимит 50/день, то каждый из 100 пользователей "
            "может отправить по 50 сообщений.\n\n"
            "<b>В минуту</b> — защита от спам-потока (рекомендуем 3-10)\n"
            "<b>В день</b> — дневной лимит на человека (рекомендуем 30-100)\n\n"
            "Отправьте два числа через пробел, например: <code>5 50</code>\n\n"
            "Или нажмите кнопку для значений по умолчанию."
        ),
        "en": (
            "<b>Step 5/7: Message Limits</b>\n\n"
            "Each user question costs your OpenRouter credits. "
            "Set per-user limits to protect from spam.\n\n"
            "This is an <b>individual limit</b> — each user has their own counter. "
            "For example, if the limit is 50/day, each of 100 users "
            "can send 50 messages.\n\n"
            "<b>Per minute</b> — burst protection (recommended 3-10)\n"
            "<b>Per day</b> — daily limit per person (recommended 30-100)\n\n"
            "Send two numbers separated by a space, e.g.: <code>5 50</code>\n\n"
            "Or press the button for default values."
        ),
    },
    "btn_rate_default": {
        "ru": "Оставить по умолчанию (5/мин, 50/день)",
        "en": "Keep defaults (5/min, 50/day)",
    },
    "rate_format_error": {
        "ru": "Отправьте два числа через пробел: <code>сообщений_в_минуту сообщений_в_день</code>\nПример: <code>5 50</code>",
        "en": "Send two numbers separated by a space: <code>per_minute per_day</code>\nExample: <code>5 50</code>",
    },
    "rate_not_integers": {
        "ru": "Оба значения должны быть целыми числами. Пример: <code>5 50</code>",
        "en": "Both values must be integers. Example: <code>5 50</code>",
    },
    "rate_minute_range": {
        "ru": "Лимит в минуту должен быть от 1 до 60.",
        "en": "Per-minute limit must be between 1 and 60.",
    },
    "rate_day_range": {
        "ru": "Лимит в день должен быть от 1 до 10000.",
        "en": "Per-day limit must be between 1 and 10000.",
    },
    "rate_day_less_minute": {
        "ru": "Дневной лимит не может быть меньше минутного.",
        "en": "Daily limit cannot be less than per-minute limit.",
    },
    "rate_set": {
        "ru": "Лимиты: {per_minute} сообщений/мин, {per_day} сообщений/день\n\n",
        "en": "Limits: {per_minute} msg/min, {per_day} msg/day\n\n",
    },
    "rate_set_default": {
        "ru": "Лимиты: 5 сообщений/мин, 50 сообщений/день (по умолчанию)\n\n",
        "en": "Limits: 5 msg/min, 50 msg/day (default)\n\n",
    },

    # ── Onboarding: Step 6 — Persona ──
    "step6_prompt": {
        "ru": (
            "<b>Шаг 6/7: Стиль бота (опционально)</b>\n\n"
            "Опишите стиль общения бота текстом (тон, обращение, ограничения) "
            "или отправьте файл с описанием.\n\n"
            "Или нажмите кнопку, чтобы пропустить."
        ),
        "en": (
            "<b>Step 6/7: Bot Style (optional)</b>\n\n"
            "Describe the bot's communication style as text (tone, form of address, restrictions) "
            "or send a file with the description.\n\n"
            "Or press the button to skip."
        ),
    },
    "persona_file_too_big": {
        "ru": "Файл стиля слишком большой. Максимум 1 МБ.",
        "en": "Style file is too large. Maximum 1 MB.",
    },
    "persona_parse_error": {
        "ru": "Не удалось прочитать файл. Поддерживаемые форматы: TXT, MD, PDF, DOCX.",
        "en": "Could not read the file. Supported formats: TXT, MD, PDF, DOCX.",
    },
    "persona_too_short": {
        "ru": "Слишком короткое описание стиля. Напишите подробнее или отправьте файл.",
        "en": "Style description is too short. Write in more detail or send a file.",
    },
    "persona_too_long": {
        "ru": "Слишком длинное описание (максимум 5000 символов). Сократите или отправьте файлом.",
        "en": "Description is too long (max 5000 characters). Shorten it or send as a file.",
    },

    # ── Onboarding: Step 7 — Documents ──
    "step7_prompt": {
        "ru": (
            "<b>Шаг 7/7: Документация (опционально)</b>\n\n"
            "Отправьте файлы документации вашего проекта (PDF, DOCX, TXT, MD, HTML).\n"
            "Вы можете отправить несколько файлов. Когда закончите, нажмите «Готово».\n\n"
            "Или нажмите «Пропустить», чтобы добавить документы позже."
        ),
        "en": (
            "<b>Step 7/7: Documentation (optional)</b>\n\n"
            "Send your project documentation files (PDF, DOCX, TXT, MD, HTML).\n"
            "You can send multiple files. When done, press \"Done\".\n\n"
            "Or press \"Skip\" to add documents later."
        ),
    },
    "step7_prompt_max": {
        "ru": (
            "<b>Шаг 7/7: Документация (опционально)</b>\n\n"
            "Отправьте файлы документации вашего проекта (PDF, DOCX, TXT, MD, HTML).\n"
            "Максимум 20 МБ на файл. Когда закончите, нажмите «Готово».\n\n"
            "Или нажмите «Пропустить», чтобы добавить документы позже."
        ),
        "en": (
            "<b>Step 7/7: Documentation (optional)</b>\n\n"
            "Send your project documentation files (PDF, DOCX, TXT, MD, HTML).\n"
            "Maximum 20 MB per file. When done, press \"Done\".\n\n"
            "Or press \"Skip\" to add documents later."
        ),
    },
    "persona_loaded": {
        "ru": "Стиль бота загружен.\n\n",
        "en": "Bot style loaded.\n\n",
    },
    "doc_too_big": {
        "ru": "Файл слишком большой. Максимум 20 МБ.",
        "en": "File is too large. Maximum 20 MB.",
    },
    "doc_unsupported": {
        "ru": "Неподдерживаемый формат. Поддерживаются: {formats}",
        "en": "Unsupported format. Supported: {formats}",
    },
    "doc_parse_error": {
        "ru": "Не удалось прочитать файл. Проверьте формат.",
        "en": "Could not read the file. Check the format.",
    },
    "doc_too_short": {
        "ru": "Документ пуст или слишком короткий (минимум 50 символов).",
        "en": "Document is empty or too short (minimum 50 characters).",
    },
    "doc_added": {
        "ru": (
            "Файл <b>{filename}</b> добавлен — {chunks} фрагментов.\n"
            "Итого: {total_files} файлов, {total_chunks} фрагментов.\n\n"
            "Отправьте ещё файлы или нажмите «Готово»."
        ),
        "en": (
            "File <b>{filename}</b> added — {chunks} chunks.\n"
            "Total: {total_files} files, {total_chunks} chunks.\n\n"
            "Send more files or press \"Done\"."
        ),
    },
    "btn_done": {
        "ru": "Готово",
        "en": "Done",
    },

    # ── Onboarding: Finish ──
    "setup_complete": {
        "ru": (
            "Настройка завершена!\n\n"
            "Проект: <b>{project_name}</b>\n"
            "Группа: <b>{chat_title}</b>\n"
            "Модераторы: {moderators}\n"
            "Пробный период: 7 дней{doc_text}\n\n"
            "Используйте меню для управления ботом."
        ),
        "en": (
            "Setup complete!\n\n"
            "Project: <b>{project_name}</b>\n"
            "Group: <b>{chat_title}</b>\n"
            "Moderators: {moderators}\n"
            "Trial period: 7 days{doc_text}\n\n"
            "Use the menu to manage your bot."
        ),
    },
    "docs_ingested": {
        "ru": "\nДокументов загружено: {count} ({chunks} фрагментов)",
        "en": "\nDocuments uploaded: {count} ({chunks} chunks)",
    },

    # ── Main menu ──
    "btn_settings": {
        "ru": "Настройки",
        "en": "Settings",
    },
    "btn_subscription": {
        "ru": "Подписка",
        "en": "Subscription",
    },

    # ── Settings menu ──
    "btn_change_group": {
        "ru": "Сменить группу",
        "en": "Change group",
    },
    "btn_moderators": {
        "ru": "Модераторы",
        "en": "Moderators",
    },
    "btn_bot_style": {
        "ru": "Стиль бота",
        "en": "Bot style",
    },
    "btn_documents": {
        "ru": "Документы",
        "en": "Documents",
    },
    "btn_rate_limits": {
        "ru": "Лимиты сообщений",
        "en": "Message limits",
    },
    "btn_back": {
        "ru": "« Назад",
        "en": "« Back",
    },
    "settings_title": {
        "ru": "Настройки проекта:",
        "en": "Project settings:",
    },
    "menu_back_text": {
        "ru": "Проект: <b>{project_name}</b>\nСтатус: <b>{status}</b>",
        "en": "Project: <b>{project_name}</b>\nStatus: <b>{status}</b>",
    },

    # ── Settings: Change group ──
    "change_group_prompt": {
        "ru": "Текущая группа: <b>{current}</b>\n\nОтправьте ID новой группы (бот должен быть админом в ней):",
        "en": "Current group: <b>{current}</b>\n\nSend the new group ID (bot must be an admin there):",
    },
    "invalid_group_id": {
        "ru": "Пожалуйста, отправьте числовой ID группы.",
        "en": "Please send a numeric group ID.",
    },
    "group_updated": {
        "ru": "Группа обновлена: <b>{chat_title}</b>",
        "en": "Group updated: <b>{chat_title}</b>",
    },

    # ── Settings: Moderators ──
    "mods_label": {
        "ru": "Модераторы: {mods}",
        "en": "Moderators: {mods}",
    },
    "mods_none": {
        "ru": "Не назначены",
        "en": "Not assigned",
    },
    "btn_edit": {
        "ru": "Изменить",
        "en": "Edit",
    },
    "btn_delete_all": {
        "ru": "Удалить всех",
        "en": "Delete all",
    },
    "mods_send_prompt": {
        "ru": "Отправьте @username модераторов через пробел:",
        "en": "Send moderator @usernames separated by spaces:",
    },
    "mods_at_least_one": {
        "ru": "Укажите хотя бы одного модератора.",
        "en": "Specify at least one moderator.",
    },
    "mods_updated": {
        "ru": "Модераторы обновлены: {mods}",
        "en": "Moderators updated: {mods}",
    },
    "mods_cleared": {
        "ru": "Все модераторы удалены.",
        "en": "All moderators removed.",
    },

    # ── Settings: Rate limits ──
    "rate_limits_info": {
        "ru": (
            "<b>Лимиты сообщений (на каждого пользователя)</b>\n\n"
            "В минуту: <b>{per_minute}</b>\n"
            "В день: <b>{per_day}</b>\n\n"
            "Это индивидуальный лимит — у каждого пользователя свой счётчик."
        ),
        "en": (
            "<b>Message limits (per user)</b>\n\n"
            "Per minute: <b>{per_minute}</b>\n"
            "Per day: <b>{per_day}</b>\n\n"
            "This is an individual limit — each user has their own counter."
        ),
    },
    "rate_edit_prompt": {
        "ru": "Отправьте два числа через пробел:\n<code>сообщений_в_минуту сообщений_в_день</code>\n\nПример: <code>5 50</code>",
        "en": "Send two numbers separated by a space:\n<code>per_minute per_day</code>\n\nExample: <code>5 50</code>",
    },
    "rate_send_two_numbers": {
        "ru": "Отправьте два числа через пробел. Пример: <code>5 50</code>",
        "en": "Send two numbers separated by a space. Example: <code>5 50</code>",
    },
    "rate_both_integers": {
        "ru": "Оба значения должны быть целыми числами.",
        "en": "Both values must be integers.",
    },
    "rate_minute_1_60": {
        "ru": "Лимит в минуту: от 1 до 60.",
        "en": "Per-minute limit: 1 to 60.",
    },
    "rate_day_1_10000": {
        "ru": "Лимит в день: от 1 до 10000.",
        "en": "Per-day limit: 1 to 10000.",
    },
    "rate_updated": {
        "ru": "Лимиты обновлены: {per_minute} сообщений/мин, {per_day} сообщений/день",
        "en": "Limits updated: {per_minute} msg/min, {per_day} msg/day",
    },

    # ── Settings: Persona ──
    "persona_status": {
        "ru": "Стиль бота: {status}",
        "en": "Bot style: {status}",
    },
    "persona_loaded_status": {
        "ru": "Загружен",
        "en": "Loaded",
    },
    "persona_not_set": {
        "ru": "Не задан",
        "en": "Not set",
    },
    "btn_upload_new": {
        "ru": "Загрузить новый",
        "en": "Upload new",
    },
    "btn_delete": {
        "ru": "Удалить",
        "en": "Delete",
    },
    "persona_upload_prompt": {
        "ru": "Отправьте файл со стилем бота (TXT, MD, PDF, DOCX) или напишите описание стиля текстом:",
        "en": "Send a bot style file (TXT, MD, PDF, DOCX) or write a style description as text:",
    },
    "persona_file_big": {
        "ru": "Файл слишком большой. Максимум 1 МБ.",
        "en": "File is too large. Maximum 1 MB.",
    },
    "persona_read_error": {
        "ru": "Не удалось прочитать файл.",
        "en": "Could not read the file.",
    },
    "persona_updated": {
        "ru": "Стиль бота обновлён.",
        "en": "Bot style updated.",
    },
    "persona_deleted": {
        "ru": "Стиль бота удалён.",
        "en": "Bot style deleted.",
    },
    "persona_short": {
        "ru": "Слишком короткое описание стиля. Напишите подробнее или отправьте файл.",
        "en": "Style description is too short. Write more or send a file.",
    },
    "persona_long": {
        "ru": "Слишком длинное описание (максимум 5000 символов). Сократите или отправьте файлом.",
        "en": "Description is too long (max 5000 characters). Shorten it or send as a file.",
    },

    # ── Settings: Documents ──
    "docs_list_title": {
        "ru": "Документы:",
        "en": "Documents:",
    },
    "docs_empty": {
        "ru": "Документов пока нет.",
        "en": "No documents yet.",
    },
    "btn_add": {
        "ru": "Добавить",
        "en": "Add",
    },
    "doc_add_prompt": {
        "ru": "Отправьте файл документации (PDF, DOCX, TXT, MD, HTML). Максимум 20 МБ.",
        "en": "Send a documentation file (PDF, DOCX, TXT, MD, HTML). Maximum 20 MB.",
    },
    "doc_file_big": {
        "ru": "Файл слишком большой. Максимум 20 МБ.",
        "en": "File is too large. Maximum 20 MB.",
    },
    "doc_unsupported_fmt": {
        "ru": "Неподдерживаемый формат. Поддерживаются: {formats}",
        "en": "Unsupported format. Supported: {formats}",
    },
    "doc_chunk_limit": {
        "ru": "Достигнут лимит фрагментов ({max_chunks}). Обновите план для загрузки новых документов.",
        "en": "Chunk limit reached ({max_chunks}). Upgrade your plan to upload more documents.",
    },
    "doc_uploaded": {
        "ru": "Документ <b>{filename}</b> загружен ({chunks} фрагментов).",
        "en": "Document <b>{filename}</b> uploaded ({chunks} chunks).",
    },
    "doc_upload_error_val": {
        "ru": "Ошибка: {error}",
        "en": "Error: {error}",
    },
    "doc_upload_error": {
        "ru": "Ошибка загрузки документа.",
        "en": "Document upload error.",
    },
    "doc_no_docs_delete": {
        "ru": "Нет документов для удаления.",
        "en": "No documents to delete.",
    },
    "doc_choose_delete": {
        "ru": "Выберите документ для удаления:",
        "en": "Choose a document to delete:",
    },
    "doc_invalid_id": {
        "ru": "Неверный ID документа.",
        "en": "Invalid document ID.",
    },
    "doc_deleted": {
        "ru": "Документ удалён.",
        "en": "Document deleted.",
    },

    # ── Private: project selector & help ──
    "no_projects": {
        "ru": "Нет доступных проектов. Попробуйте позже.",
        "en": "No available projects. Try again later.",
    },
    "choose_project": {
        "ru": "Выберите проект:",
        "en": "Choose a project:",
    },
    "project_not_found": {
        "ru": "Проект не найден.",
        "en": "Project not found.",
    },
    "project_selected": {
        "ru": (
            "Вы выбрали проект: <b>{project_name}</b>\n\n"
            "Задайте вопрос, и я найду ответ в документации.\n"
            "Используйте /switch чтобы сменить проект."
        ),
        "en": (
            "You selected: <b>{project_name}</b>\n\n"
            "Ask a question and I'll find the answer in the documentation.\n"
            "Use /switch to change project."
        ),
    },
    "project_unavailable": {
        "ru": "Этот проект временно недоступен.",
        "en": "This project is temporarily unavailable.",
    },
    "processing_error": {
        "ru": "Произошла ошибка при обработке сообщения. Попробуйте позже.",
        "en": "An error occurred while processing the message. Try again later.",
    },
    "help_text": {
        "ru": (
            "Я бот технической поддержки.\n\n"
            "Просто напишите вопрос — я найду ответ в документации проекта.\n\n"
            "<b>Команды:</b>\n"
            "/start — главное меню / начать\n"
            "/switch — сменить проект\n"
            "/lang — сменить язык\n"
            "/help — эта справка"
        ),
        "en": (
            "I'm a technical support bot.\n\n"
            "Just write a question — I'll find the answer in the project documentation.\n\n"
            "<b>Commands:</b>\n"
            "/start — main menu / start\n"
            "/switch — switch project\n"
            "/lang — change language\n"
            "/help — this help"
        ),
    },

    # ── Subscription ──
    "sub_info": {
        "ru": (
            "<b>Ваш проект</b>\n"
            "Проект: <b>{project_name}</b>\n"
            "План: <b>{plan_name}</b>\n"
            "Документов: <b>{doc_count}</b>\n"
            "Фрагментов: <b>{total_chunks}</b> / {max_chunks}\n"
            "Истекает: <b>{expires}</b>\n"
            "\n"
            "<b>Что такое фрагменты?</b>\n"
            "Каждый загруженный документ разбивается на фрагменты "
            "(~2500 символов, примерно 1 страница текста). "
            "Чем больше документация — тем больше фрагментов.\n"
            "\n"
            "<b>Тарифы</b>\n"
        ),
        "en": (
            "<b>Your project</b>\n"
            "Project: <b>{project_name}</b>\n"
            "Plan: <b>{plan_name}</b>\n"
            "Documents: <b>{doc_count}</b>\n"
            "Chunks: <b>{total_chunks}</b> / {max_chunks}\n"
            "Expires: <b>{expires}</b>\n"
            "\n"
            "<b>What are chunks?</b>\n"
            "Each uploaded document is split into chunks "
            "(~2500 characters, approximately 1 page of text). "
            "The more documentation — the more chunks.\n"
            "\n"
            "<b>Plans</b>\n"
        ),
    },
    "sub_plan_line": {
        "ru": "{name} — ${price}/мес · до {limit} фрагментов\n",
        "en": "{name} — ${price}/mo · up to {limit} chunks\n",
    },
    "sub_no_active": {
        "ru": "Нет активной подписки",
        "en": "No active subscription",
    },
    "sub_recommendation": {
        "ru": "\nСейчас у вас <b>{total_chunks}</b> фрагментов — рекомендуем <b>{plan}</b> (${price}/мес)",
        "en": "\nYou currently have <b>{total_chunks}</b> chunks — we recommend <b>{plan}</b> (${price}/mo)",
    },
    "sub_unknown_plan": {
        "ru": "Неизвестный план.",
        "en": "Unknown plan.",
    },
    "sub_chunk_limit": {
        "ru": (
            "У вас {total_chunks} фрагментов, а план {plan} "
            "допускает максимум {max_chunks}.\n"
            "Выберите план побольше или удалите лишние документы."
        ),
        "en": (
            "You have {total_chunks} chunks, but the {plan} plan "
            "allows a maximum of {max_chunks}.\n"
            "Choose a bigger plan or delete extra documents."
        ),
    },
    "sub_plan_not_found": {
        "ru": "План не найден в базе.",
        "en": "Plan not found in database.",
    },
    "btn_pay": {
        "ru": "Оплатить",
        "en": "Pay",
    },
    "btn_check_payment": {
        "ru": "Проверить оплату",
        "en": "Check payment",
    },
    "sub_invoice": {
        "ru": (
            "Счёт на оплату плана <b>{plan}</b> — ${price}/мес\n\n"
            "Нажмите кнопку для оплаты криптовалютой.\n"
            "После оплаты нажмите «Проверить оплату»."
        ),
        "en": (
            "Invoice for <b>{plan}</b> plan — ${price}/mo\n\n"
            "Press the button to pay with crypto.\n"
            "After payment, press \"Check payment\"."
        ),
    },
    "sub_invoice_error": {
        "ru": "Не удалось создать счёт. Попробуйте позже.",
        "en": "Could not create invoice. Try again later.",
    },
    "sub_checking": {
        "ru": "Проверяю...",
        "en": "Checking...",
    },
    "sub_not_found": {
        "ru": "Счёт не найден.",
        "en": "Invoice not found.",
    },
    "sub_already_active": {
        "ru": "Подписка уже активирована!",
        "en": "Subscription is already active!",
    },
    "sub_check_error": {
        "ru": "Не удалось проверить статус. Попробуйте позже.",
        "en": "Could not check status. Try again later.",
    },
    "sub_status_awaiting": {
        "ru": "ожидает оплаты",
        "en": "awaiting payment",
    },
    "sub_status_partial": {
        "ru": "оплачен частично",
        "en": "partially paid",
    },
    "sub_status_canceled": {
        "ru": "отменён",
        "en": "canceled",
    },
    "sub_not_paid": {
        "ru": "Статус счёта: <b>{status}</b>. Оплата ещё не завершена.",
        "en": "Invoice status: <b>{status}</b>. Payment not yet completed.",
    },
    "sub_activated": {
        "ru": "Оплата подтверждена! План <b>{plan}</b> активирован на 30 дней.\n\nПроект: {project_name}",
        "en": "Payment confirmed! <b>{plan}</b> plan activated for 30 days.\n\nProject: {project_name}",
    },
    "sub_activate_error": {
        "ru": "Не удалось активировать подписку. Обратитесь в поддержку.",
        "en": "Could not activate subscription. Contact support.",
    },

    # ── Inline ──
    "inline_no_project_title": {
        "ru": "Проект не выбран",
        "en": "No project selected",
    },
    "inline_no_project_desc": {
        "ru": "Напишите боту в личные сообщения и выберите проект.",
        "en": "Send the bot a direct message and select a project.",
    },
    "inline_no_project_text": {
        "ru": "Проект не выбран. Напишите боту в ЛС для выбора проекта.",
        "en": "No project selected. Send the bot a DM to choose a project.",
    },
    "inline_unavailable_title": {
        "ru": "Проект недоступен",
        "en": "Project unavailable",
    },
    "inline_unavailable_desc": {
        "ru": "Выбранный проект неактивен.",
        "en": "The selected project is inactive.",
    },
    "inline_unavailable_text": {
        "ru": "Проект недоступен.",
        "en": "Project unavailable.",
    },
    "inline_no_answer_title": {
        "ru": "Ответ не найден",
        "en": "No answer found",
    },
    "inline_no_answer_desc": {
        "ru": "В документации не найдено информации по вашему запросу.",
        "en": "No information found in the documentation for your query.",
    },
    "inline_no_answer_text": {
        "ru": "В документации не найдено информации по запросу: {query}",
        "en": "No information found in the documentation for: {query}",
    },
    "inline_error_title": {
        "ru": "Ошибка",
        "en": "Error",
    },
    "inline_error_desc": {
        "ru": "Не удалось обработать запрос.",
        "en": "Could not process the query.",
    },
    "inline_answer_title": {
        "ru": "Ответ ({project_name})",
        "en": "Answer ({project_name})",
    },

    # ── Group ──
    "group_no_answer": {
        "ru": "К сожалению, я не нашёл ответа в документации. {tags}",
        "en": "Unfortunately, I couldn't find an answer in the documentation. {tags}",
    },

    # ── Rate limit ──
    "rate_limit_daily": {
        "ru": "Вы достигли дневного лимита сообщений для этого проекта ({per_day}/день). Попробуйте завтра.",
        "en": "You've reached the daily message limit for this project ({per_day}/day). Try again tomorrow.",
    },
    "rate_limit_minute": {
        "ru": "Вы отправляете сообщения слишком часто. Подождите минуту (лимит: {per_minute} сообщений/мин).",
        "en": "You're sending messages too fast. Wait a minute (limit: {per_minute} msg/min).",
    },
}


def t(key: str, lang: str = "ru", **kwargs: Any) -> str:
    """Get translated text by key and language."""
    entry = _TEXTS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get("ru", key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
