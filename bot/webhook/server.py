"""aiohttp webhook server for Cryptocloud payment callbacks.

Endpoint: POST /api/cryptocloud/callback
Receives postback from Cryptocloud when payment status changes.
Verifies JWT token (HS256), activates subscription on success.

Designed to run behind Cloudflare Tunnel:
  https://webhook.thejarvisbot.com/api/cryptocloud/callback
"""

import logging

from aiohttp import web

from bot.config import settings
from bot.services.payment import verify_cryptocloud_token
from bot.services.subscription_service import activate_subscription

logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    """GET / — health check for verifying tunnel connectivity."""
    return web.json_response({"status": "ok", "service": "saas-support-webhook"})


async def cryptocloud_callback(request: web.Request) -> web.Response:
    """POST /api/cryptocloud/callback — handle Cryptocloud payment postback.

    Cryptocloud sends:
      - status: "success"
      - invoice_id: "INV-..."
      - order_id: "<tenant_id>:<plan_name>"
      - token: JWT (HS256, signed with project secret, 5 min TTL)
      - amount_crypto, currency, invoice_info (nested)
    """
    from bot import state

    # Parse body (supports both JSON and form-urlencoded)
    content_type = request.content_type
    if "json" in content_type:
        try:
            data = await request.json()
        except Exception:
            logger.error("Failed to parse JSON body")
            return web.Response(status=400, text="Invalid JSON")
    else:
        data = dict(await request.post())

    logger.info("Cryptocloud callback raw data: %s", data)

    invoice_id = data.get("invoice_id") or data.get("uuid") or "unknown"
    status = data.get("status")
    logger.info("Cryptocloud callback: invoice=%s status=%s", invoice_id, status)

    # Verify JWT token (per Cryptocloud docs: empty/missing token = verification passed)
    token = data.get("token")
    if token and settings.cryptocloud_secret:
        payload = verify_cryptocloud_token(token, settings.cryptocloud_secret)
        if payload is None:
            logger.warning("Invalid JWT token for invoice %s", invoice_id)
            return web.Response(status=403, text="Invalid token")
        logger.debug("JWT verified for invoice %s, payload: %s", invoice_id, payload)
    elif not token:
        logger.info("No token in callback for invoice %s (verification skipped per docs)", invoice_id)

    # Only process successful payments
    if status != "success":
        logger.info("Non-success status '%s' for invoice %s, ignoring", status, invoice_id)
        return web.Response(status=200, text="OK")

    if not invoice_id or invoice_id == "unknown":
        return web.Response(status=400, text="Missing invoice_id")

    # Find the pending subscription by invoice_id
    # Cryptocloud postback sends invoice_id WITHOUT "INV-" prefix,
    # but we store the full uuid (e.g. "INV-GTSWX14G"). Try both.
    sub = await state.subscription_repo.get_by_invoice(invoice_id)
    if not sub and not invoice_id.startswith("INV-"):
        sub = await state.subscription_repo.get_by_invoice(f"INV-{invoice_id}")
    if not sub:
        logger.error("No pending subscription found for invoice %s", invoice_id)
        return web.Response(status=200, text="OK")

    tenant_id = sub["tenant_id"]
    tenant = await state.tenant_repo.get(tenant_id)
    if not tenant:
        logger.error("No tenant found for subscription (tenant_id=%s)", tenant_id)
        return web.Response(status=200, text="OK")

    # Activate subscription (use the invoice_id as stored in DB)
    stored_invoice_id = sub["payment_invoice_id"]
    success = await activate_subscription(
        tenant_id=tenant_id,
        invoice_id=stored_invoice_id,
        tenant_repo=state.tenant_repo,
        subscription_repo=state.subscription_repo,
        redis_manager=state.redis,
        chat_id=tenant["chat_id"],
    )

    # Notify tenant owner via Telegram
    if success and state.bot_instance:
        plan_name = "Unknown"
        if sub.get("plan_id"):
            plan = await state.plan_repo.get_by_id(sub["plan_id"])
            if plan:
                plan_name = plan["name"].title()

        try:
            await state.bot_instance.send_message(
                tenant["owner_user_id"],
                f"Оплата получена! План <b>{plan_name}</b> активирован на 30 дней.\n\n"
                f"Проект: {tenant['project_name']}",
            )
            logger.info("Owner %d notified about payment for tenant %s",
                        tenant["owner_user_id"], tenant_id)
        except Exception as e:
            logger.error("Failed to notify owner %d: %s", tenant["owner_user_id"], e)

    return web.Response(status=200, text="OK")


async def catch_all(request: web.Request) -> web.Response:
    """Catch-all handler to log any unmatched requests."""
    body = await request.text()
    logger.warning(
        "Unmatched request: %s %s headers=%s body=%s",
        request.method, request.path, dict(request.headers), body[:500],
    )
    return web.Response(status=404, text="Not found")


def create_webhook_app() -> web.Application:
    """Create aiohttp app with Cryptocloud webhook route."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_post("/api/cryptocloud/callback", cryptocloud_callback)
    # Also accept at root POST in case Cryptocloud sends to /
    app.router.add_post("/", cryptocloud_callback)
    # Catch-all for debugging
    app.router.add_route("*", "/{path:.*}", catch_all)
    return app
