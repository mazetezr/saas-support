"""Superadmin commands for platform management.

All commands require superadmin_ids from config.
Available: /tenants, /tenant, /activate, /suspend, /global_stats, /revenue
"""

import logging
from datetime import timedelta
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings

logger = logging.getLogger(__name__)

router = Router(name="superadmin")
router.message.filter(F.chat.type == "private")


def is_superadmin(message: Message) -> bool:
    return message.from_user and message.from_user.id in settings.superadmin_ids



@router.message(Command("tenants"), is_superadmin)
async def handle_tenants(message: Message):
    """List all tenants with status, chunk count, and plan."""
    from bot import state

    tenants = await state.tenant_repo.list_all()

    if not tenants:
        await message.answer("Нет тенантов.")
        return

    lines = ["<b>Все тенанты:</b>\n"]
    for t in tenants:
        chunks = await state.chunk_repo.count_by_tenant(t["id"])
        sub = await state.subscription_repo.get_active(t["id"])
        plan = sub["plan_name"] if sub and sub.get("plan_name") else "—"
        lines.append(
            f"• <b>{t['project_name']}</b> [{t['status']}]\n"
            f"  ID: <code>{t['id']}</code> | "
            f"Чанков: {chunks} | План: {plan}"
        )

    logger.info("ADMIN: /tenants by user %d — listed %d tenants", message.from_user.id, len(tenants))
    await message.answer("\n".join(lines))


@router.message(Command("tenant"), is_superadmin)
async def handle_tenant_detail(message: Message):
    """Show detailed info for a specific tenant."""
    from bot import state

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /tenant <id>")
        return

    try:
        tenant_id = UUID(args[1].strip())
    except ValueError:
        await message.answer("Неверный UUID.")
        return

    tenant = await state.tenant_repo.get(tenant_id)
    if not tenant:
        await message.answer("Тенант не найден.")
        return

    chunks = await state.chunk_repo.count_by_tenant(tenant_id)
    docs = await state.document_repo.count_by_tenant(tenant_id)
    sub = await state.subscription_repo.get_active(tenant_id)

    plan = sub["plan_name"] if sub and sub.get("plan_name") else "Trial"
    expires = sub["expires_at"].strftime("%d.%m.%Y %H:%M") if sub and sub["expires_at"] else "—"

    mods = ", ".join(f"@{u}" for u in (tenant["moderator_usernames"] or [])) or "—"

    logger.info("ADMIN: /tenant %s by user %d — viewed '%s'", tenant_id, message.from_user.id, tenant["project_name"])
    await message.answer(
        f"<b>Тенант: {tenant['project_name']}</b>\n\n"
        f"ID: <code>{tenant['id']}</code>\n"
        f"Владелец: {tenant['owner_user_id']}\n"
        f"Группа: {tenant.get('chat_title', '—')} ({tenant['chat_id']})\n"
        f"Статус: <b>{tenant['status']}</b>\n"
        f"План: {plan}\n"
        f"Истекает: {expires}\n"
        f"Документов: {docs}\n"
        f"Фрагментов: {chunks}\n"
        f"Модераторы: {mods}\n"
        f"Персона: {'Да' if tenant['persona_doc'] else 'Нет'}\n"
        f"Создан: {tenant['created_at'].strftime('%d.%m.%Y %H:%M')}"
    )


@router.message(Command("activate"), is_superadmin)
async def handle_activate(message: Message):
    """Manually activate a subscription: /activate <id> <plan> <days>"""
    from bot import state

    args = message.text.split()
    if len(args) < 4:
        await message.answer("Использование: /activate <tenant_id> <plan_name> <days>")
        return

    try:
        plan_name = args[2].lower()
        days = int(args[3])
    except (ValueError, IndexError):
        await message.answer("Неверные параметры.")
        return

    try:
        tenant_id = UUID(args[1].strip())
    except ValueError:
        await message.answer("Неверный UUID.")
        return

    tenant = await state.tenant_repo.get(tenant_id)
    if not tenant:
        await message.answer("Тенант не найден.")
        return

    plan = await state.plan_repo.get_by_name(plan_name)
    if not plan:
        await message.answer(f"План '{plan_name}' не найден.")
        return

    # Expire all previous active subscriptions for this tenant
    await state.db.execute(
        "UPDATE subscriptions SET status = 'expired' WHERE tenant_id = $1 AND status = 'active'",
        tenant_id,
    )

    # Create activated subscription
    await state.db.execute(
        """
        INSERT INTO subscriptions (tenant_id, plan_id, status, started_at, expires_at, payment_provider)
        VALUES ($1, $2, 'active', NOW(), NOW() + $3::interval, 'manual')
        """,
        tenant_id, plan["id"], timedelta(days=days),
    )

    await state.tenant_repo.update_status(tenant_id, "active")

    # Invalidate cache
    if state.redis and tenant["chat_id"]:
        await state.redis.delete(f"tenant:chat:{tenant['chat_id']}")

    logger.info(
        "ADMIN: /activate by user %d — tenant=%s ('%s'), plan=%s, days=%d",
        message.from_user.id, tenant_id, tenant["project_name"], plan_name, days,
    )

    await message.answer(
        f"Подписка активирована: {tenant['project_name']} — "
        f"{plan_name.title()} на {days} дней."
    )

    # Notify owner
    if state.bot_instance:
        try:
            await state.bot_instance.send_message(
                tenant["owner_user_id"],
                f"Подписка <b>{plan_name.title()}</b> для проекта "
                f"<b>{tenant['project_name']}</b> активирована администратором на {days} дней.",
            )
        except Exception:
            pass


@router.message(Command("suspend"), is_superadmin)
async def handle_suspend(message: Message):
    """Suspend a tenant: /suspend <id>"""
    from bot import state

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /suspend <tenant_id>")
        return

    try:
        tenant_id = UUID(args[1].strip())
    except ValueError:
        await message.answer("Неверный UUID.")
        return

    tenant = await state.tenant_repo.get(tenant_id)
    if not tenant:
        await message.answer("Тенант не найден.")
        return

    await state.tenant_repo.update_status(tenant_id, "suspended")

    # Expire active subscriptions on suspend
    await state.db.execute(
        "UPDATE subscriptions SET status = 'expired' WHERE tenant_id = $1 AND status = 'active'",
        tenant_id,
    )

    if state.redis and tenant["chat_id"]:
        await state.redis.delete(f"tenant:chat:{tenant['chat_id']}")

    logger.info(
        "ADMIN: /suspend by user %d — tenant=%s ('%s')",
        message.from_user.id, tenant_id, tenant["project_name"],
    )

    await message.answer(f"Тенант <b>{tenant['project_name']}</b> заблокирован.")


@router.message(Command("global_stats"), is_superadmin)
async def handle_global_stats(message: Message):
    """Show overall platform statistics."""
    from bot import state

    total_tenants = await state.tenant_repo.count_all()
    active = await state.db.fetchval(
        "SELECT COUNT(*) FROM tenants WHERE status = 'active'"
    )
    trial = await state.db.fetchval(
        "SELECT COUNT(*) FROM tenants WHERE status = 'trial'"
    )
    expired = await state.db.fetchval(
        "SELECT COUNT(*) FROM tenants WHERE status = 'expired'"
    )
    total_chunks = await state.db.fetchval("SELECT COUNT(*) FROM chunks")
    total_messages = await state.db.fetchval("SELECT COUNT(*) FROM messages")
    total_docs = await state.db.fetchval("SELECT COUNT(*) FROM documents")

    logger.info("ADMIN: /global_stats by user %d", message.from_user.id)
    await message.answer(
        f"<b>Статистика платформы</b>\n\n"
        f"Тенантов: {total_tenants}\n"
        f"  Активных: {active}\n"
        f"  Триал: {trial}\n"
        f"  Истёкших: {expired}\n\n"
        f"Документов: {total_docs}\n"
        f"Фрагментов: {total_chunks}\n"
        f"Сообщений: {total_messages}"
    )


@router.message(Command("revenue"), is_superadmin)
async def handle_revenue(message: Message):
    """Show revenue statistics."""
    from bot import state

    revenue_30d = await state.subscription_repo.get_revenue(days=30)
    revenue_90d = await state.subscription_repo.get_revenue(days=90)
    revenue_all = await state.subscription_repo.get_revenue(days=3650)

    paid_subs = await state.db.fetchval(
        "SELECT COUNT(*) FROM subscriptions WHERE payment_amount IS NOT NULL AND payment_amount > 0"
    )

    logger.info("ADMIN: /revenue by user %d", message.from_user.id)
    await message.answer(
        f"<b>Доходы</b>\n\n"
        f"За 30 дней: ${revenue_30d:.2f}\n"
        f"За 90 дней: ${revenue_90d:.2f}\n"
        f"Всего: ${revenue_all:.2f}\n\n"
        f"Оплаченных подписок: {paid_subs}"
    )
