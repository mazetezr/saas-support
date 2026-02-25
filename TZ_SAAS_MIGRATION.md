# ТЗ: Миграция AI Support Bot → SaaS сервис

## Цель

Взять существующее ядро бота и надстроить SaaS-слой:
мультитенантность, подписки, онбординг, оплата криптой.

Главный приоритет — **изоляция данных между тенантами**. Ни при каких условиях бот не должен использовать документацию одного проекта для ответа в другом.

---

## Стек (дополнения к существующему)

| Компонент | Технология | Зачем |
|-----------|-----------|-------|
| БД | PostgreSQL + pgvector | Мультитенантность, изоляция |
| Кэш | Redis | Кэш тенантов, rate limiting |
| Миграции | Alembic | Версионирование схемы БД. При изменении структуры БД создаётся файл-миграция. На сервере: `git pull` + `alembic upgrade head` — и БД обновлена. Можно автоматизировать в Docker entrypoint. |
| Оплата | Cryptocloud API | Крипто-платежи |
| Фоновые задачи | arq (Redis-based) | Парсинг доков, проверка подписок |

---

## Изоляция тенантов (КРИТИЧЕСКИ ВАЖНО)

### Принцип: tenant_id ВЕЗДЕ

Каждая таблица содержит `tenant_id`. Каждый запрос фильтруется по `tenant_id`. Нет исключений.

### Уровень 1 — БД

```sql
-- Все чанки привязаны к тенанту
SELECT content FROM chunks
WHERE tenant_id = $1  -- ВСЕГДА
ORDER BY embedding <=> $query_vec
LIMIT 5;
```

**Запрещено:** любые запросы к chunks/messages/documents без `WHERE tenant_id = ...`

### Уровень 2 — Сервисный слой

```python
class KnowledgeBase:
    async def search(self, query: str, tenant_id: str, limit: int = 5):
        """tenant_id — обязательный параметр, не Optional"""
        # ...

    async def add_document(self, tenant_id: str, filename: str, content: str):
        """Документ всегда привязан к конкретному тенанту"""
        # ...
```

**Правило:** `tenant_id` — обязательный (не Optional) параметр во всех методах сервисов. Если где-то tenant_id не передан — это баг, не фича.

### Уровень 3 — Мидлвара

```python
class TenantMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        chat_id = event.chat.id
        chat_type = event.chat.type

        if chat_type in ("group", "supergroup"):
            tenant = await self._resolve_by_chat(chat_id)
        elif chat_type == "private":
            tenant = await self._resolve_by_user(event.from_user.id)
        else:
            return

        # Нет тенанта — хендлер получит tenant=None
        # и должен сам решить что делать (онбординг/игнор)
        data["tenant"] = tenant
        return await handler(event, data)

    async def _resolve_by_chat(self, chat_id: int) -> TenantContext | None:
        """Redis кэш → PostgreSQL fallback. TTL 5 мин."""
        cached = await redis.get(f"tenant:chat:{chat_id}")
        if cached:
            return TenantContext.from_json(cached)

        tenant = await tenant_repo.get_by_chat_id(chat_id)
        if tenant:
            await redis.setex(
                f"tenant:chat:{chat_id}",
                300,
                tenant.to_json()
            )
        return tenant

    async def _resolve_by_user(self, user_id: int) -> TenantContext | None:
        """Для личных сообщений — по user_settings.current_tenant_id"""
        settings = await user_settings_repo.get(user_id)
        if settings and settings.current_tenant_id:
            return await tenant_repo.get(settings.current_tenant_id)
        return None
```

### Уровень 4 — Дополнительная защита

```python
# Декоратор для критичных операций
def require_tenant_match(func):
    """Проверяет что запрашиваемый ресурс принадлежит текущему тенанту"""
    async def wrapper(*args, tenant: TenantContext, resource_tenant_id: str, **kwargs):
        if str(tenant.tenant_id) != str(resource_tenant_id):
            raise TenantMismatchError(
                f"Tenant {tenant.tenant_id} tried to access resource of {resource_tenant_id}"
            )
        return await func(*args, tenant=tenant, **kwargs)
    return wrapper
```

---

## Модель данных

### Новые таблицы (поверх существующих)

```sql
-- ============================================
-- ТЕНАНТЫ
-- ============================================
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id BIGINT NOT NULL UNIQUE,    -- Telegram ID владельца (1 тенант на юзера)
    project_name TEXT NOT NULL,              -- Название проекта
    chat_id BIGINT UNIQUE,                   -- ID группы
    chat_title TEXT,

    -- Настройки
    moderator_usernames TEXT[] DEFAULT '{}',  -- @username модераторов для тега
    persona_doc TEXT,                         -- Стиль говора (текст)
    language TEXT DEFAULT 'en',
    relevance_threshold FLOAT DEFAULT 0.75,

    -- API
    openrouter_api_key TEXT NOT NULL,         -- Зашифрованный ключ клиента

    -- Статус
    status TEXT DEFAULT 'trial',             -- trial, active, expired, suspended
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- ПОДПИСКИ
-- ============================================
CREATE TABLE plans (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,               -- lite, standard, pro, business
    max_chunks INT NOT NULL,
    price_usd DECIMAL(10,2) NOT NULL,
    duration_days INT DEFAULT 30
);

-- Seed:
-- INSERT INTO plans VALUES
-- (1, 'lite',     20,  5.00,  30),
-- (2, 'standard', 50,  9.00,  30),
-- (3, 'pro',      100, 19.00, 30),
-- (4, 'business', 200, 39.00, 30);

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    plan_id INT REFERENCES plans(id),
    status TEXT DEFAULT 'active',            -- active, expired, cancelled
    started_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    -- Оплата
    payment_provider TEXT DEFAULT 'cryptocloud',
    payment_invoice_id TEXT,                 -- ID инвойса Cryptocloud
    payment_amount DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_tenant ON subscriptions(tenant_id);
CREATE INDEX idx_subscriptions_expires ON subscriptions(expires_at) WHERE status = 'active';

-- ============================================
-- НАСТРОЙКИ ЮЗЕРА (для личных сообщений)
-- ============================================
CREATE TABLE user_settings (
    user_id BIGINT PRIMARY KEY,              -- Telegram ID
    current_tenant_id UUID REFERENCES tenants(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- ШИФРОВАНИЕ API-КЛЮЧЕЙ
-- ============================================
-- openrouter_api_key хранится зашифрованным (Fernet / AES-256)
-- Ключ шифрования — в переменной окружения, НЕ в БД
-- При чтении: расшифровка в сервисном слое
-- В логах API-ключ НИКОГДА не появляется
```

### Изменения в существующих таблицах

```sql
-- Добавить tenant_id во ВСЕ существующие таблицы:

ALTER TABLE documents ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE chunks ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE messages ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;

-- Индексы для изоляции
CREATE INDEX idx_chunks_tenant ON chunks(tenant_id);
CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_messages_tenant ON messages(tenant_id);

-- pgvector поиск с фильтром по тенанту
CREATE INDEX idx_chunks_tenant_embedding ON chunks(tenant_id);
-- При поиске: WHERE tenant_id = $1 ORDER BY embedding <=> $2
```

---

## Шифрование API-ключей

```python
# core/encryption.py

from cryptography.fernet import Fernet
import os

# Ключ из переменной окружения
ENCRYPTION_KEY = os.environ["ENCRYPTION_KEY"]  # Fernet.generate_key() один раз
fernet = Fernet(ENCRYPTION_KEY)

def encrypt_api_key(key: str) -> str:
    return fernet.encrypt(key.encode()).decode()

def decrypt_api_key(encrypted: str) -> str:
    return fernet.decrypt(encrypted.encode()).decode()

# Использование:
# При сохранении: tenant.openrouter_api_key = encrypt_api_key(raw_key)
# При вызове LLM: real_key = decrypt_api_key(tenant.openrouter_api_key)
```

---

## Онбординг (пошаговый flow в личке)

### Состояния онбординга

```python
from enum import Enum

class OnboardingStep(str, Enum):
    START = "start"                    # Начало
    API_KEY = "api_key"                # Шаг 0: API-ключ
    PROJECT_NAME = "project_name"      # Шаг 1: Название проекта
    ADD_TO_GROUP = "add_to_group"      # Шаг 2: Добавить бота + прислать chat_id
    MODERATORS = "moderators"          # Шаг 3: Юзернеймы модераторов
    PERSONA = "persona"                # Шаг 4: Стиль говора (можно skip)
    DOCUMENTS = "documents"            # Шаг 5: Документация (можно skip)
    DONE = "done"                      # Готово
```

### FSM-хранилище в Redis

```python
# Состояние онбординга хранится в Redis, не в памяти
# Ключ: onboarding:{user_id}
# TTL: 24 часа (если не завершил — сброс)

onboarding_data = {
    "step": "add_to_group",
    "api_key_encrypted": "gAAAA...",
    "project_name": "Syndicate",
    "chat_id": None,
    "moderators": [],
    "persona": None,
    "is_trial": True
}
```

### Детальный flow

```
ПОЛЬЗОВАТЕЛЬ                              БОТ
─────────────────────────────────────────────────────────────

/start
                                          "Привет! Я AI Support Bot.
                                           Давайте настроим бота для вашего проекта.
                                           
                                           Сначала мне нужен API-ключ OpenRouter.
                                           Инструкция: [ссылка]
                                           
                                           Отправьте ваш API-ключ:"

sk-or-v1-abc123...
                                          ✅ Ключ принят и зашифрован.
                                          (бот проверяет ключ запросом к OpenRouter)
                                          (если невалидный: "❌ Ключ не работает, проверьте")
                                          
                                          "Шаг 1/5: Как называется ваш проект?"

Syndicate
                                          "Шаг 2/5: Добавьте бота в группу вашего
                                           проекта как участника, затем отправьте
                                           мне ID группы.
                                           
                                           Как узнать ID: [инструкция]"

-1001234567890
                                          (бот вызывает getChat(-1001234567890))
                                          
                                          ВАРИАНТ А — бот в группе:
                                          ✅ Нашёл группу "Syndicate Chat"
                                          
                                          ВАРИАНТ Б — бота нет в группе:
                                          "❌ Меня нет в этой группе.
                                           Сначала добавьте @YourBot в группу,
                                           затем отправьте ID ещё раз."

(после успешного подключения)
                                          "Шаг 3/5: Отправьте @username модераторов
                                           через пробел. Бот будет тегать их когда
                                           не знает ответ.
                                           
                                           Пример: @alice @bob @charlie"

@architect @neo
                                          ✅ Модераторы: @architect, @neo
                                          
                                          "Шаг 4/5: Отправьте документ со стилем
                                           общения бота (описание тона, персонажа,
                                           примеры фраз). Или нажмите Пропустить."
                                          
                                          [Пропустить]

(отправляет .txt с описанием персоны)
                                          ✅ Стиль загружен.
                                          
                                          "Шаг 5/5: Отправьте документацию проекта
                                           (PDF, TXT, MD, DOCX). Можно несколько
                                           файлов. Когда закончите — нажмите Готово.
                                           Или нажмите Пропустить — загрузите позже."
                                          
                                          [Готово]  [Пропустить]

(отправляет whitepaper.pdf)
                                          ⏳ Обрабатываю whitepaper.pdf...
                                          ✅ whitepaper.pdf — 46 чанков

(отправляет faq.md)
                                          ✅ faq.md — 12 чанков

[Готово]
                                          "🎉 Готово! Бот настроен для Syndicate.
                                           
                                           📊 Загружено: 58 чанков
                                           ⏱ Пробный период: 7 дней
                                           
                                           Бот уже работает в вашей группе!
                                           
                                           Когда триал закончится, выберите план
                                           в меню → Подписка."
```

### Код онбординга

```python
# handlers/onboarding.py

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

class SetupStates(StatesGroup):
    waiting_api_key = State()
    waiting_project_name = State()
    waiting_chat_id = State()
    waiting_moderators = State()
    waiting_persona = State()
    waiting_documents = State()


@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext):
    # Проверяем — может уже есть тенант
    existing = await tenant_repo.get_by_owner(message.from_user.id)
    if existing:
        await message.answer("У вас уже настроен проект. Используйте меню.")
        return

    await message.answer(
        "Привет! Я AI Support Bot.\n\n"
        "Давайте настроим бота для вашего проекта.\n"
        "Сначала мне нужен API-ключ OpenRouter.\n\n"
        "Как получить: https://openrouter.ai/keys\n\n"
        "Отправьте ваш API-ключ:"
    )
    await state.set_state(SetupStates.waiting_api_key)


# === Шаг 0: API-ключ ===
@router.message(SetupStates.waiting_api_key)
async def process_api_key(message: Message, state: FSMContext):
    key = message.text.strip()

    # Удаляем сообщение с ключом из чата (безопасность!)
    await message.delete()

    # Валидируем ключ
    is_valid = await llm.validate_api_key(key)
    if not is_valid:
        await message.answer("❌ Ключ не работает. Проверьте и отправьте ещё раз:")
        return

    await state.update_data(api_key_encrypted=encrypt_api_key(key))
    await message.answer("✅ Ключ принят.\n\nШаг 1/5: Как называется ваш проект?")
    await state.set_state(SetupStates.waiting_project_name)


# === Шаг 1: Название ===
@router.message(SetupStates.waiting_project_name)
async def process_project_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) > 100:
        await message.answer("Слишком длинное название. До 100 символов:")
        return

    await state.update_data(project_name=name)
    await message.answer(
        f"✅ Проект: {name}\n\n"
        "Шаг 2/5: Добавьте бота в группу проекта, "
        "затем отправьте ID группы.\n\n"
        "Как узнать ID: добавьте @userinfobot в группу, "
        "он покажет ID."
    )
    await state.set_state(SetupStates.waiting_chat_id)


# === Шаг 2: Chat ID ===
@router.message(SetupStates.waiting_chat_id)
async def process_chat_id(message: Message, state: FSMContext):
    try:
        chat_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Отправьте числовой ID группы:")
        return

    # Проверяем что бот в группе
    try:
        chat = await message.bot.get_chat(chat_id)
        bot_member = await message.bot.get_chat_member(chat_id, message.bot.id)
        if bot_member.status in ("left", "kicked"):
            raise Exception("Bot not in group")
    except Exception:
        await message.answer(
            "❌ Меня нет в этой группе.\n"
            "Сначала добавьте бота в группу, затем отправьте ID ещё раз."
        )
        return

    # Проверяем что группа не занята другим тенантом
    existing = await tenant_repo.get_by_chat_id(chat_id)
    if existing:
        await message.answer("❌ В этой группе уже работает другой проект.")
        return

    await state.update_data(chat_id=chat_id, chat_title=chat.title)
    await message.answer(
        f"✅ Группа: {chat.title}\n\n"
        "Шаг 3/5: Отправьте @username модераторов через пробел.\n"
        "Бот будет тегать их когда не знает ответ.\n\n"
        "Пример: @alice @bob"
    )
    await state.set_state(SetupStates.waiting_moderators)


# === Шаг 3: Модераторы ===
@router.message(SetupStates.waiting_moderators)
async def process_moderators(message: Message, state: FSMContext):
    raw = message.text.strip()
    # Парсим @username'ы
    usernames = [
        u.strip().lstrip("@")
        for u in raw.split()
        if u.strip().startswith("@") or u.strip().isalnum()
    ]

    if not usernames:
        await message.answer("❌ Не распознал юзернеймы. Формат: @alice @bob")
        return

    await state.update_data(moderators=usernames)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить →", callback_data="skip_persona")]
    ])
    await message.answer(
        f"✅ Модераторы: {', '.join('@' + u for u in usernames)}\n\n"
        "Шаг 4/5: Отправьте документ с описанием стиля общения бота "
        "(тон, персонаж, примеры). Или пропустите — будет нейтральный стиль.",
        reply_markup=keyboard
    )
    await state.set_state(SetupStates.waiting_persona)


# === Шаг 4: Персона (skip-able) ===
@router.message(SetupStates.waiting_persona, F.document)
async def process_persona_doc(message: Message, state: FSMContext):
    file = await message.bot.download(message.document)
    text = await doc_parser.parse_bytes(file.read(), message.document.file_name)
    await state.update_data(persona=text)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить →", callback_data="skip_documents")]
    ])
    await message.answer(
        "✅ Стиль загружен.\n\n"
        "Шаг 5/5: Отправьте документацию проекта (PDF, TXT, MD, DOCX).\n"
        "Можно несколько файлов. Когда закончите — нажмите Готово.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="docs_done")],
            [InlineKeyboardButton(text="Пропустить →", callback_data="skip_documents")]
        ])
    )
    await state.set_state(SetupStates.waiting_documents)

@router.callback_query(F.data == "skip_persona")
async def skip_persona(callback: CallbackQuery, state: FSMContext):
    await state.update_data(persona=None)
    await callback.message.answer(
        "Шаг 5/5: Отправьте документацию проекта. Когда закончите — Готово.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="docs_done")],
            [InlineKeyboardButton(text="Пропустить →", callback_data="skip_documents")]
        ])
    )
    await state.set_state(SetupStates.waiting_documents)
    await callback.answer()


# === Шаг 5: Документы (skip-able) ===
@router.message(SetupStates.waiting_documents, F.document)
async def process_document(message: Message, state: FSMContext):
    data = await state.get_data()
    docs_count = data.get("docs_uploaded", 0)

    file = await message.bot.download(message.document)
    text = await doc_parser.parse_bytes(file.read(), message.document.file_name)
    chunks = text_splitter.split(text, chunk_size=2500)

    # Сохраняем временно (тенант ещё не создан)
    pending = data.get("pending_docs", [])
    pending.append({
        "filename": message.document.file_name,
        "chunks": chunks
    })
    await state.update_data(
        pending_docs=pending,
        docs_uploaded=docs_count + 1
    )

    total_chunks = sum(len(d["chunks"]) for d in pending)
    await message.answer(
        f"✅ {message.document.file_name} — {len(chunks)} чанков\n"
        f"📊 Всего: {total_chunks} чанков\n\n"
        "Отправьте ещё файлы или нажмите Готово.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="docs_done")]
        ])
    )


@router.callback_query(F.data.in_({"docs_done", "skip_documents"}))
async def finish_onboarding(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # === Создаём тенанта ===
    tenant = await tenant_repo.create(
        owner_user_id=callback.from_user.id,
        project_name=data["project_name"],
        chat_id=data["chat_id"],
        chat_title=data.get("chat_title"),
        openrouter_api_key=data["api_key_encrypted"],  # уже зашифрован
        moderator_usernames=data.get("moderators", []),
        persona_doc=data.get("persona"),
        status="trial"
    )

    # === Создаём триал-подписку ===
    await subscription_repo.create_trial(
        tenant_id=tenant.id,
        days=7
    )

    # === Сохраняем документы (если есть) ===
    total_chunks = 0
    for doc_data in data.get("pending_docs", []):
        doc = await document_repo.create(tenant.id, doc_data["filename"])
        for i, chunk_text in enumerate(doc_data["chunks"]):
            embedding = embedder.encode(chunk_text).tolist()
            await chunk_repo.create(
                document_id=doc.id,
                tenant_id=tenant.id,
                chunk_index=i,
                content=chunk_text,
                embedding=embedding
            )
            total_chunks += 1
        await document_repo.update_status(doc.id, "ready", len(doc_data["chunks"]))

    # === Привязываем юзера к тенанту ===
    await user_settings_repo.set_tenant(callback.from_user.id, tenant.id)

    # === Очищаем FSM ===
    await state.clear()

    # === Инвалидируем кэш ===
    await redis.delete(f"tenant:chat:{data['chat_id']}")

    chunks_info = f"\n📊 Загружено: {total_chunks} чанков" if total_chunks else ""
    await callback.message.answer(
        f"🎉 Готово! Бот настроен для {data['project_name']}.\n"
        f"{chunks_info}\n"
        f"⏱ Пробный период: 7 дней\n\n"
        f"Бот уже работает в группе!\n\n"
        f"Используйте меню для управления.",
    )
    await callback.answer()
```

---

## Меню (ReplyKeyboardMarkup)

### Структура меню (показывается после онбординга)

```
Главное меню:
┌──────────────────────┐
│  ⚙️ Настройки        │
│  💳 Подписка         │
└──────────────────────┘
```

### Подменю "Настройки"

```
⚙️ Настройки:
┌──────────────────────┐
│  📌 Сменить группу   │
│  👥 Модераторы       │
│  🎭 Стиль бота      │
│  📄 Документы        │
│  ◀️ Назад            │
└──────────────────────┘
```

### Подменю "Подписка"

```
💳 Подписка:
┌──────────────────────────────┐
│  Проект: Syndicate           │
│  План: Trial                 │
│  Чанков: 58                  │
│  Истекает: 25.02.2026        │
│                              │
│  [Выбрать план]              │
│  ◀️ Назад                    │
└──────────────────────────────┘
```

### Реализация меню

```python
# handlers/menu.py

from aiogram import Router, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

router = Router()

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="💳 Подписка")],
    ],
    resize_keyboard=True
)

SETTINGS_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📌 Сменить группу"), KeyboardButton(text="👥 Модераторы")],
        [KeyboardButton(text="🎭 Стиль бота"), KeyboardButton(text="📄 Документы")],
        [KeyboardButton(text="◀️ Назад")],
    ],
    resize_keyboard=True
)


# === Главное меню ===
@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message, tenant: TenantContext):
    await message.answer("Настройки:", reply_markup=SETTINGS_MENU)

@router.message(F.text == "◀️ Назад")
async def back_to_main(message: Message):
    await message.answer("Главное меню:", reply_markup=MAIN_MENU)


# === Сменить группу ===
@router.message(F.text == "📌 Сменить группу")
async def change_group(message: Message, state: FSMContext, tenant: TenantContext):
    await message.answer(
        f"Текущая группа: {tenant.chat_title}\n\n"
        "Добавьте бота в новую группу и отправьте ID:"
    )
    await state.set_state(SettingsStates.waiting_new_chat_id)

@router.message(SettingsStates.waiting_new_chat_id)
async def process_new_chat_id(message: Message, state: FSMContext, tenant: TenantContext):
    try:
        chat_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Отправьте числовой ID:")
        return

    # Проверяем что бот в группе
    try:
        chat = await message.bot.get_chat(chat_id)
        member = await message.bot.get_chat_member(chat_id, message.bot.id)
        if member.status in ("left", "kicked"):
            raise Exception()
    except Exception:
        await message.answer("❌ Меня нет в этой группе. Добавьте бота, затем ID.")
        return

    # Проверяем что не занята
    existing = await tenant_repo.get_by_chat_id(chat_id)
    if existing and str(existing.id) != str(tenant.tenant_id):
        await message.answer("❌ В этой группе уже работает другой проект.")
        return

    # Обновляем
    old_chat_id = tenant.chat_id
    await tenant_repo.update_chat(tenant.tenant_id, chat_id, chat.title)

    # Инвалидируем кэш старой и новой группы
    await redis.delete(f"tenant:chat:{old_chat_id}")
    await redis.delete(f"tenant:chat:{chat_id}")

    await state.clear()
    await message.answer(
        f"✅ Группа изменена: {chat.title}",
        reply_markup=SETTINGS_MENU
    )


# === Модераторы ===
@router.message(F.text == "👥 Модераторы")
async def moderators_menu(message: Message, tenant: TenantContext):
    current = ", ".join(f"@{u}" for u in tenant.moderator_usernames) or "не заданы"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить", callback_data="mod_edit")],
        [InlineKeyboardButton(text="Удалить всех", callback_data="mod_clear")],
    ])
    await message.answer(f"Текущие модераторы: {current}", reply_markup=keyboard)

@router.callback_query(F.data == "mod_edit")
async def mod_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправьте новый список: @user1 @user2")
    await state.set_state(SettingsStates.waiting_moderators)
    await callback.answer()

@router.message(SettingsStates.waiting_moderators)
async def process_new_moderators(message: Message, state: FSMContext, tenant: TenantContext):
    usernames = [u.strip().lstrip("@") for u in message.text.split() if u.strip()]
    await tenant_repo.update_moderators(tenant.tenant_id, usernames)
    await redis.delete(f"tenant:chat:{tenant.chat_id}")
    await state.clear()
    await message.answer(
        f"✅ Модераторы: {', '.join('@' + u for u in usernames)}",
        reply_markup=SETTINGS_MENU
    )


# === Стиль бота ===
@router.message(F.text == "🎭 Стиль бота")
async def persona_menu(message: Message, tenant: TenantContext):
    has_persona = "Загружен" if tenant.persona_doc else "Не задан (нейтральный стиль)"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Загрузить новый", callback_data="persona_upload")],
        [InlineKeyboardButton(text="Удалить", callback_data="persona_delete")],
    ])
    await message.answer(f"Стиль бота: {has_persona}", reply_markup=keyboard)

@router.callback_query(F.data == "persona_upload")
async def persona_upload(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправьте документ с описанием стиля:")
    await state.set_state(SettingsStates.waiting_persona)
    await callback.answer()

@router.callback_query(F.data == "persona_delete")
async def persona_delete(callback: CallbackQuery, tenant: TenantContext):
    await tenant_repo.update_persona(tenant.tenant_id, None)
    await redis.delete(f"tenant:chat:{tenant.chat_id}")
    await callback.message.answer("✅ Стиль удалён. Бот будет отвечать нейтрально.")
    await callback.answer()


# === Документы ===
@router.message(F.text == "📄 Документы")
async def documents_menu(message: Message, tenant: TenantContext):
    docs = await document_repo.list_by_tenant(tenant.tenant_id)
    total_chunks = await chunk_repo.count_by_tenant(tenant.tenant_id)

    if not docs:
        text = "Документы не загружены.\n\nОтправьте файл для загрузки."
    else:
        lines = [f"📄 Документы ({total_chunks} чанков):\n"]
        for doc in docs:
            lines.append(f"• {doc.filename} — {doc.chunk_count} чанков")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="doc_add")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="doc_delete_menu")],
    ])
    await message.answer(text, reply_markup=keyboard)

@router.callback_query(F.data == "doc_delete_menu")
async def doc_delete_menu(callback: CallbackQuery, tenant: TenantContext):
    docs = await document_repo.list_by_tenant(tenant.tenant_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🗑 {doc.filename} ({doc.chunk_count})",
            callback_data=f"doc_del:{doc.id}"
        )]
        for doc in docs
    ])
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("doc_del:"))
async def doc_delete(callback: CallbackQuery, tenant: TenantContext):
    doc_id = callback.data.split(":")[1]

    # Проверяем принадлежность (изоляция!)
    doc = await document_repo.get(doc_id)
    if not doc or str(doc.tenant_id) != str(tenant.tenant_id):
        await callback.answer("❌ Документ не найден")
        return

    await document_repo.delete(doc_id)  # CASCADE удалит чанки
    await callback.message.answer(
        f"✅ {doc.filename} удалён.",
        reply_markup=SETTINGS_MENU
    )
    await callback.answer()
```

---

## Подписка и оплата (Cryptocloud)

### Flow оплаты

```
Юзер: меню → 💳 Подписка
                                          
Бот:  "Проект: Syndicate
       План: Trial (осталось 3 дня)
       Чанков: 58
       
       Подходящий план: Standard (до 100 чанков) — $9/мес"
       
       [Lite $5]  [Standard $9]
       [Pro $19]  [Business $39]

Юзер: нажимает [Standard $9]

Бот:  создаёт инвойс в Cryptocloud →
      "Оплатите $9 по ссылке: https://pay.cryptocloud.plus/..."
      [Оплатить]

Юзер: оплачивает криптой

Cryptocloud webhook → бот:
      "✅ Оплата получена!
       План Standard активирован до 19.03.2026"
```

### Код

```python
# services/payment.py

import httpx
from config import settings

CRYPTOCLOUD_API = "https://api.cryptocloud.plus/v2"

async def create_invoice(
    tenant_id: str,
    plan_name: str,
    amount_usd: float,
    owner_user_id: int
) -> str:
    """Создаёт инвойс в Cryptocloud, возвращает URL оплаты"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{CRYPTOCLOUD_API}/invoice/create",
            headers={
                "Authorization": f"Token {settings.cryptocloud_api_key}",
            },
            json={
                "amount": amount_usd,
                "currency": "USD",
                "order_id": f"{tenant_id}:{plan_name}",
                "email": "",  # опционально
            }
        )
    data = response.json()
    invoice_id = data["result"]["id"]
    pay_url = data["result"]["link"]

    # Сохраняем инвойс
    await subscription_repo.create_pending(
        tenant_id=tenant_id,
        plan_name=plan_name,
        invoice_id=invoice_id,
        amount=amount_usd
    )

    return pay_url


# handlers/subscription.py

@router.message(F.text == "💳 Подписка")
async def subscription_menu(message: Message, tenant: TenantContext):
    sub = await subscription_repo.get_active(tenant.tenant_id)
    total_chunks = await chunk_repo.count_by_tenant(tenant.tenant_id)

    # Определяем подходящий план
    suggested = suggest_plan(total_chunks)

    if sub:
        days_left = (sub.expires_at - datetime.utcnow()).days
        status_text = (
            f"Проект: {tenant.project_name}\n"
            f"План: {sub.plan_name.title()}\n"
            f"Чанков: {total_chunks}\n"
            f"Истекает: {sub.expires_at.strftime('%d.%m.%Y')} "
            f"({days_left} дн.)\n"
        )
    else:
        status_text = (
            f"Проект: {tenant.project_name}\n"
            f"План: нет активной подписки\n"
            f"Чанков: {total_chunks}\n"
        )

    if suggested:
        status_text += f"\n💡 Рекомендуемый план: {suggested.title()} (до {PLAN_LIMITS[suggested]} чанков)"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Lite $5", callback_data="buy:lite"),
            InlineKeyboardButton(text="Standard $9", callback_data="buy:standard"),
        ],
        [
            InlineKeyboardButton(text="Pro $19", callback_data="buy:pro"),
            InlineKeyboardButton(text="Business $39", callback_data="buy:business"),
        ],
    ])
    await message.answer(status_text, reply_markup=keyboard)


PLAN_LIMITS = {"lite": 20, "standard": 50, "pro": 100, "business": 200}
PLAN_PRICES = {"lite": 5, "standard": 9, "pro": 19, "business": 39}

def suggest_plan(total_chunks: int) -> str | None:
    """Рекомендует минимальный план который вмещает текущие чанки"""
    for name, limit in sorted(PLAN_LIMITS.items(), key=lambda x: x[1]):
        if total_chunks <= limit:
            return name
    return "business"


@router.callback_query(F.data.startswith("buy:"))
async def process_buy(callback: CallbackQuery, tenant: TenantContext):
    plan_name = callback.data.split(":")[1]
    price = PLAN_PRICES[plan_name]
    limit = PLAN_LIMITS[plan_name]

    # Проверяем что чанков не больше лимита плана
    total_chunks = await chunk_repo.count_by_tenant(tenant.tenant_id)
    if total_chunks > limit:
        await callback.answer(
            f"❌ У вас {total_chunks} чанков, план {plan_name} вмещает {limit}. "
            f"Выберите план побольше или удалите лишние документы.",
            show_alert=True
        )
        return

    # Создаём инвойс
    pay_url = await create_invoice(
        tenant_id=str(tenant.tenant_id),
        plan_name=plan_name,
        amount_usd=price,
        owner_user_id=callback.from_user.id
    )

    await callback.message.answer(
        f"💳 Оплата: {plan_name.title()} — ${price}/мес\n"
        f"До {limit} чанков\n\n"
        f"Оплатите по ссылке:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Оплатить", url=pay_url)]
        ])
    )
    await callback.answer()


# === Webhook от Cryptocloud ===
# Настроить в Cryptocloud: POST https://your-server.com/api/payment/webhook

from aiohttp import web

async def payment_webhook(request: web.Request):
    data = await request.json()

    # Верифицируем подпись
    if not verify_cryptocloud_signature(data, settings.cryptocloud_secret):
        return web.Response(status=403)

    if data.get("status") == "success":
        invoice_id = data["invoice_id"]
        pending = await subscription_repo.get_by_invoice(invoice_id)

        if pending:
            # Активируем подписку
            plan = await plan_repo.get_by_name(pending.plan_name)
            await subscription_repo.activate(
                tenant_id=pending.tenant_id,
                plan_id=plan.id,
                invoice_id=invoice_id,
                days=30
            )

            # Обновляем статус тенанта
            await tenant_repo.update_status(pending.tenant_id, "active")

            # Инвалидируем кэш
            tenant = await tenant_repo.get(pending.tenant_id)
            await redis.delete(f"tenant:chat:{tenant.chat_id}")

            # Уведомляем владельца
            await bot.send_message(
                tenant.owner_user_id,
                f"✅ Оплата получена!\n"
                f"План {pending.plan_name.title()} активирован на 30 дней."
            )

    return web.Response(status=200)
```

---

## Триал → Подписка (переход)

```python
# workers/tasks.py

async def check_trial_expiry(ctx):
    """Запускать раз в час"""
    
    # За 1 день до конца триала — напоминание
    expiring_soon = await subscription_repo.get_expiring(hours=24)
    for sub in expiring_soon:
        tenant = await tenant_repo.get(sub.tenant_id)
        total_chunks = await chunk_repo.count_by_tenant(sub.tenant_id)
        suggested = suggest_plan(total_chunks)
        price = PLAN_PRICES.get(suggested, "?")

        await bot.send_message(
            tenant.owner_user_id,
            f"⏰ Триал для {tenant.project_name} истекает завтра.\n\n"
            f"📊 Ваша база: {total_chunks} чанков\n"
            f"💡 Подходящий план: {suggested.title()} — ${price}/мес\n\n"
            f"Оформите подписку в меню → 💳 Подписка"
        )

    # Истёкшие триалы — деактивация
    expired = await subscription_repo.get_expired()
    for sub in expired:
        tenant = await tenant_repo.get(sub.tenant_id)
        await tenant_repo.update_status(sub.tenant_id, "expired")
        await subscription_repo.expire(sub.id)
        
        # Инвалидируем кэш (бот перестанет отвечать)
        await redis.delete(f"tenant:chat:{tenant.chat_id}")
        
        total_chunks = await chunk_repo.count_by_tenant(sub.tenant_id)
        suggested = suggest_plan(total_chunks)
        
        await bot.send_message(
            tenant.owner_user_id,
            f"⚠️ Пробный период для {tenant.project_name} истёк.\n"
            f"Бот перестал отвечать в группе.\n\n"
            f"📊 Ваши данные на месте: {total_chunks} чанков\n"
            f"Оформите подписку чтобы бот продолжил работу."
        )
```

### Логика в групповом хендлере

```python
@router.message(F.chat.type.in_({"group", "supergroup"}))
async def monitor_group(message: Message, tenant: TenantContext | None = None):
    # Нет тенанта — бот просто в случайной группе
    if not tenant:
        return

    # Тенант не активен (триал истёк, подписка кончилась)
    if tenant.status not in ("trial", "active"):
        return

    # ... остальная логика ответов
```

---

## Личка: выбор проекта обычным юзером

Когда обычный участник (не владелец тенанта) пишет боту в личку — бот не знает из какого он проекта. Юзер выбирает сам.

### Flow

```
Юзер: /start (или любое сообщение)

Бот:  "Выберите проект:"
      
      [Syndicate]        [Zifretta]
      [DeFi Protocol]    [GameDev DAO]
      [CryptoKitties]    [Merlin Chain]
      
      [1/2 ▶]

Юзер: нажимает [Syndicate]

Бот:  "✅ Проект: Syndicate
       Задавайте вопросы!"
       
       (сохраняет в user_settings.current_tenant_id)

Юзер: "Как подключить API?"

Бот:  (ищет по документации Syndicate, отвечает)
```

### Смена проекта

Команда `/switch` — сбрасывает выбор и показывает список проектов заново.

### Код

```python
# handlers/private.py

PROJECTS_PER_PAGE = 10

@router.message(F.chat.type == "private")
async def handle_private(message: Message, tenant: TenantContext | None = None):
    user_id = message.from_user.id
    
    # Владелец тенанта — показываем меню управления
    owner_tenant = await tenant_repo.get_by_owner(user_id)
    if owner_tenant:
        # ... меню владельца (настройки, подписка и т.д.)
        return
    
    # Обычный юзер — проверяем выбран ли проект
    if not tenant:
        await show_project_selector(message, page=0)
        return
    
    # Проект выбран — отвечаем на вопрос
    # ... поиск по документации tenant, LLM ответ


async def show_project_selector(message: Message, page: int = 0):
    """Показывает список активных проектов с пагинацией"""
    tenants = await tenant_repo.get_all_active()
    total = len(tenants)
    total_pages = (total + PROJECTS_PER_PAGE - 1) // PROJECTS_PER_PAGE
    
    start = page * PROJECTS_PER_PAGE
    end = start + PROJECTS_PER_PAGE
    page_tenants = tenants[start:end]
    
    # Кнопки проектов (по 2 в ряд)
    buttons = []
    row = []
    for t in page_tenants:
        row.append(InlineKeyboardButton(
            text=t.project_name,
            callback_data=f"select_project:{t.id}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    # Навигация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"projects_page:{page-1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"projects_page:{page+1}"))
    if nav:
        buttons.append(nav)
    
    await message.answer(
        "Выберите проект:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("select_project:"))
async def on_project_selected(callback: CallbackQuery):
    tenant_id = callback.data.split(":")[1]
    tenant = await tenant_repo.get(tenant_id)
    
    if not tenant or tenant.status not in ("trial", "active"):
        await callback.answer("❌ Проект недоступен", show_alert=True)
        return
    
    await user_settings_repo.set_tenant(callback.from_user.id, tenant_id)
    
    await callback.message.answer(
        f"✅ Проект: {tenant.project_name}\n"
        f"Задавайте вопросы!\n\n"
        f"Сменить проект: /switch"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("projects_page:"))
async def on_page_change(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_project_selector(callback.message, page=page)
    await callback.answer()


@router.message(Command("switch"), F.chat.type == "private")
async def switch_project(message: Message):
    """Сбрасывает выбор проекта"""
    await user_settings_repo.clear_tenant(message.from_user.id)
    await show_project_selector(message, page=0)
```

### Важно

- Показывать **только активные** тенанты (status = trial или active)
- Если у тенанта нет документации — не показывать в списке (нечем отвечать)
- `/switch` — сброс + повторный выбор
- Если проектов 0 — "Пока нет доступных проектов"

---

---

## LLM вызовы с ключом клиента

```python
# services/llm.py

async def ask_llm(
    tenant: TenantContext,
    system_prompt: str,
    user_message: str,
    **kwargs
) -> str:
    """Каждый вызов использует API-ключ КОНКРЕТНОГО тенанта"""
    
    # Расшифровываем ключ тенанта
    api_key = decrypt_api_key(tenant.openrouter_api_key)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",  # Ключ клиента!
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-chat-v3-0324",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.3,
                "max_tokens": kwargs.get("max_tokens", 1500),
            },
            timeout=60.0
        )

    # Обработка ошибок API-ключа
    if response.status_code == 401:
        # Невалидный ключ — уведомляем владельца
        await notify_owner_bad_key(tenant)
        return "NO_ANSWER"

    if response.status_code == 429:
        # Rate limit — ждём
        return "NO_ANSWER"

    return response.json()["choices"][0]["message"]["content"]
```

---

## Суперадмин (твои команды)

Вместо удалённых /export_logs, /compact, /faq_candidates:

```
/tenants                        — Все тенанты (статус, чанки, план)
/tenant <id>                    — Детали тенанта
/activate <id> <plan> <days>    — Ручная активация
/suspend <id>                   — Заблокировать тенанта
/global_stats                   — Общая статистика
/revenue                        — Доход за период
```

---

## Порядок реализации

### Этап 1 — БД и миграция (1 день)
1. PostgreSQL + pgvector (docker-compose)
2. Redis
3. Новые таблицы: tenants, plans, subscriptions, user_settings
4. Добавить tenant_id в существующие таблицы
5. Alembic миграции

### Этап 2 — Ядро мультитенантности (1 день)
6. TenantMiddleware
7. Шифрование API-ключей
8. LLM вызовы с ключом тенанта
9. Knowledge base с изоляцией по tenant_id

### Этап 3 — Онбординг (1-2 дня)
10. FSM: весь flow из 5 шагов
11. Валидация API-ключа
12. Проверка бота в группе
13. Парсинг и загрузка доков при онбординге

### Этап 4 — Меню и настройки (1 день)
14. Главное меню (ReplyKeyboard)
15. Настройки: группа, модераторы, персона, документы
16. Удаление/добавление доков через меню

### Этап 5 — Подписки и оплата (1-2 дня)
17. Cryptocloud интеграция
18. Меню подписки с рекомендацией плана
19. Webhook обработка
20. Триал → напоминание → деактивация

### Этап 6 — Групповой хендлер (доработка) (0.5 дня)
21. Проверка статуса тенанта
22. Rate limiting в Redis

### Этап 7 — Polish (0.5 дня)
23. Суперадмин команды
24. Error handling
25. Логирование
