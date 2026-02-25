"""Subscription management handlers.

Shows current plan info, plan selection, and Cryptocloud payment links.
"""

import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.core.tenant import TenantContext
from bot.services.subscription_service import PLAN_LIMITS, PLAN_PRICES, suggest_plan
from bot.texts import t

logger = logging.getLogger(__name__)

router = Router(name="subscription")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.callback_query(F.data == "menu_subscription")
async def handle_subscription(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state

    await callback.answer()

    user_id = callback.from_user.id
    tenant_record = await app_state.tenant_repo.get_by_owner(user_id)
    if not tenant_record:
        return

    tenant = TenantContext.from_record(tenant_record)
    sub = await app_state.subscription_repo.get_active(tenant.tenant_id)
    total_chunks = await app_state.chunk_repo.count_by_tenant(tenant.tenant_id)
    doc_count = await app_state.document_repo.count_by_tenant(tenant.tenant_id)

    # Build info text
    if sub:
        plan_name = sub.get("plan_name") or "Trial"
        max_chunks = sub.get("max_chunks") or "∞"
        expires = sub["expires_at"].strftime("%d.%m.%Y") if sub["expires_at"] else "—"
    else:
        plan_name = t("sub_no_active", lang)
        max_chunks = "—"
        expires = "—"

    suggested = suggest_plan(total_chunks)

    text = t("sub_info", lang,
             project_name=tenant.project_name,
             plan_name=plan_name,
             doc_count=doc_count,
             total_chunks=total_chunks,
             max_chunks=max_chunks,
             expires=expires)

    # Add plan lines
    for name in ("lite", "standard", "pro", "business"):
        text += t("sub_plan_line", lang,
                  name=name.title(),
                  price=PLAN_PRICES[name],
                  limit=PLAN_LIMITS[name])

    if suggested:
        text += t("sub_recommendation", lang,
                  total_chunks=total_chunks,
                  plan=suggested.title(),
                  price=PLAN_PRICES[suggested])

    # Plan selection buttons — mark suggested plan
    def plan_btn(name: str) -> InlineKeyboardButton:
        label = f"{name.title()} ${PLAN_PRICES[name]}"
        if name == suggested:
            label = f"* {label}"
        return InlineKeyboardButton(text=label, callback_data=f"buy:{name}")

    plan_buttons = [
        [plan_btn("lite"), plan_btn("standard")],
        [plan_btn("pro"), plan_btn("business")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_back")],
    ]
    plan_kb = InlineKeyboardMarkup(inline_keyboard=plan_buttons)

    await callback.message.edit_text(text, reply_markup=plan_kb)


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    from bot.services.payment import create_invoice

    await callback.answer()

    user_id = callback.from_user.id
    tenant_record = await app_state.tenant_repo.get_by_owner(user_id)
    if not tenant_record:
        await callback.message.answer(t("project_not_found", lang))
        return

    tenant = TenantContext.from_record(tenant_record)
    plan_name = callback.data.split(":", 1)[1]

    if plan_name not in PLAN_PRICES:
        await callback.message.answer(t("sub_unknown_plan", lang))
        return

    # Check chunk limit
    total_chunks = await app_state.chunk_repo.count_by_tenant(tenant.tenant_id)
    if total_chunks > PLAN_LIMITS[plan_name]:
        await callback.message.answer(
            t("sub_chunk_limit", lang,
              total_chunks=total_chunks,
              plan=plan_name.title(),
              max_chunks=PLAN_LIMITS[plan_name])
        )
        return

    price = PLAN_PRICES[plan_name]

    try:
        # Get plan from DB
        plan_record = await app_state.plan_repo.get_by_name(plan_name)
        if not plan_record:
            await callback.message.answer(t("sub_plan_not_found", lang))
            return

        # Create Cryptocloud invoice
        invoice = await create_invoice(tenant.tenant_id, plan_name, price)

        # Save pending subscription
        await app_state.subscription_repo.create_pending(
            tenant_id=tenant.tenant_id,
            plan_id=plan_record["id"],
            invoice_id=invoice["invoice_id"],
            amount=price,
        )

        # Send payment link with check button
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_pay", lang), url=invoice["pay_url"])],
            [InlineKeyboardButton(
                text=t("btn_check_payment", lang),
                callback_data=f"check_pay:{invoice['invoice_id']}",
            )],
        ])

        await callback.message.answer(
            t("sub_invoice", lang, plan=plan_name.title(), price=price),
            reply_markup=pay_kb,
        )

    except Exception as e:
        logger.error("Failed to create invoice for tenant %s: %s", tenant.tenant_id, e)
        await callback.message.answer(t("sub_invoice_error", lang))


@router.callback_query(F.data.startswith("check_pay:"))
async def handle_check_payment(callback: CallbackQuery, lang: str = "ru"):
    from bot import state as app_state
    from bot.services.payment import check_invoice_status
    from bot.services.subscription_service import activate_subscription

    await callback.answer(t("sub_checking", lang))

    invoice_id = callback.data.split(":", 1)[1]

    # Check if already activated
    sub = await app_state.subscription_repo.get_by_invoice(invoice_id)
    if not sub:
        await callback.message.answer(t("sub_not_found", lang))
        return

    if sub["status"] == "active":
        await callback.message.answer(t("sub_already_active", lang))
        return

    # Poll Cryptocloud API for invoice status
    try:
        status = await check_invoice_status(invoice_id)
    except Exception as e:
        logger.error("Failed to check invoice %s: %s", invoice_id, e)
        await callback.message.answer(t("sub_check_error", lang))
        return

    if status not in ("paid", "overpaid"):
        status_text = {
            "created": t("sub_status_awaiting", lang),
            "partial": t("sub_status_partial", lang),
            "canceled": t("sub_status_canceled", lang),
        }.get(status, status or "—")
        await callback.message.answer(t("sub_not_paid", lang, status=status_text))
        return

    # Payment confirmed — activate subscription
    tenant_id = sub["tenant_id"]
    tenant = await app_state.tenant_repo.get(tenant_id)
    if not tenant:
        await callback.message.answer(t("project_not_found", lang))
        return

    stored_invoice_id = sub["payment_invoice_id"]
    success = await activate_subscription(
        tenant_id=tenant_id,
        invoice_id=stored_invoice_id,
        tenant_repo=app_state.tenant_repo,
        subscription_repo=app_state.subscription_repo,
        redis_manager=app_state.redis,
        chat_id=tenant["chat_id"],
    )

    if success:
        plan_name = "Unknown"
        if sub.get("plan_id"):
            plan = await app_state.plan_repo.get_by_id(sub["plan_id"])
            if plan:
                plan_name = plan["name"].title()
        await callback.message.answer(
            t("sub_activated", lang, plan=plan_name, project_name=tenant["project_name"]),
        )
    else:
        await callback.message.answer(t("sub_activate_error", lang))
