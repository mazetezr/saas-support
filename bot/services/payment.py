"""Cryptocloud payment integration.

Creates invoices and verifies webhook JWT signatures for cryptocurrency payments.
Cryptocloud uses HS256 JWT tokens for webhook verification (not simple HMAC).
"""

import logging
from uuid import UUID

import httpx
import jwt

from bot.config import settings

logger = logging.getLogger(__name__)

CRYPTOCLOUD_API = "https://api.cryptocloud.plus/v2"


async def create_invoice(
    tenant_id: UUID, plan_name: str, amount_usd: float
) -> dict:
    """Create a Cryptocloud invoice for a subscription payment.

    Returns dict with 'invoice_id' and 'pay_url'.
    Raises on API failure.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{CRYPTOCLOUD_API}/invoice/create",
            headers={
                "Authorization": f"Token {settings.cryptocloud_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "shop_id": settings.cryptocloud_shop_id,
                "amount": amount_usd,
                "currency": "USD",
                "order_id": f"{tenant_id}:{plan_name}",
            },
        )
        response.raise_for_status()

    data = response.json()
    result = data.get("result", {})

    invoice_id = result.get("uuid") or result.get("id")
    pay_url = result.get("link")

    if not invoice_id or not pay_url:
        raise ValueError(f"Invalid Cryptocloud response: {data}")

    logger.info(
        "Created Cryptocloud invoice %s for tenant %s (plan=%s, $%.2f)",
        invoice_id, tenant_id, plan_name, amount_usd,
    )

    return {"invoice_id": invoice_id, "pay_url": pay_url}


async def check_invoice_status(invoice_id: str) -> str | None:
    """Check invoice status via Cryptocloud API.

    Returns 'paid', 'created', 'partial', 'overpaid', 'canceled', or None on error.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{CRYPTOCLOUD_API}/invoice/merchant/info",
            headers={
                "Authorization": f"Token {settings.cryptocloud_api_key}",
                "Content-Type": "application/json",
            },
            json={"uuids": [invoice_id]},
        )
        response.raise_for_status()

    data = response.json()
    results = data.get("result", [])
    if not results:
        logger.warning("No invoice info returned for %s", invoice_id)
        return None

    status = results[0].get("status")
    logger.info("Invoice %s status: %s", invoice_id, status)
    return status


def verify_cryptocloud_token(token: str, secret: str) -> dict | None:
    """Verify Cryptocloud webhook JWT token (HS256).

    Cryptocloud sends a 'token' field containing a JWT signed with HS256
    using the project's secret key. Token is valid for 5 minutes.

    Returns decoded payload on success, None on failure.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Cryptocloud webhook token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Cryptocloud webhook token invalid: %s", e)
        return None
