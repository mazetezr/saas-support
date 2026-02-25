"""LLM service for OpenRouter API integration with per-tenant API keys.

Uses a shared httpx.AsyncClient for connection pooling. Each request
uses the tenant's decrypted API key. On 401 errors, notifies the tenant owner.
"""

import logging
from typing import Optional, TYPE_CHECKING

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

from bot.config import settings
from bot.core.encryption import decrypt_api_key

if TYPE_CHECKING:
    from bot.core.tenant import TenantContext

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "Извините, не удалось обработать ваш запрос. Попробуйте позже."


def _is_retryable_error(exception: BaseException) -> bool:
    """Retryable: timeout, 429, 502, 503. Non-retryable: 400, 401, 402."""
    if isinstance(exception, httpx.TimeoutException):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in (429, 502, 503)
    return False


class LLMService:
    """Async LLM service with per-tenant API key support.

    Lifecycle: start() at bot startup, close() at shutdown.
    generate_response() never raises — returns FALLBACK_MESSAGE on failure.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Initialize shared HTTP client (no auth header — per-request)."""
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        logger.info("LLM service started (model: %s)", settings.openrouter_model)

    async def close(self):
        if self.client:
            await self.client.aclose()
            logger.info("LLM service closed")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _call_api(self, messages: list[dict], api_key: str) -> str:
        """Make API call with the provided API key."""
        response = await self.client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.openrouter_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 4000,
            },
        )
        response.raise_for_status()

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("OpenRouter returned empty choices array")

        content = choices[0].get("message", {}).get("content")
        if content is None:
            raise ValueError("OpenRouter returned null content")

        usage = data.get("usage")
        if usage:
            logger.debug(
                "Token usage — prompt: %s, completion: %s, total: %s",
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
            )

        return content

    @staticmethod
    def _detect_language_hint(text: str) -> str:
        """Add language mirroring instruction for non-Cyrillic text."""
        cyrillic_count = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
        total_alpha = sum(1 for c in text if c.isalpha())
        if total_alpha > 3 and cyrillic_count < total_alpha * 0.3:
            return "[IMPORTANT: Respond in the SAME language as this message. Do NOT respond in Russian.]\n"
        return ""

    async def generate_response(
        self,
        tenant: "TenantContext",
        user_message: str,
        system_prompt: str = "",
        history: list[dict] | None = None,
    ) -> str:
        """Generate an LLM response using the tenant's API key. Never raises."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)

        lang_hint = self._detect_language_hint(user_message)
        messages.append({"role": "user", "content": f"{lang_hint}{user_message}"})

        try:
            api_key = decrypt_api_key(tenant.openrouter_api_key)
            return await self._call_api(messages, api_key)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Invalid API key for tenant %s", tenant.tenant_id)
                await self._notify_owner_bad_key(tenant)
                return "NO_ANSWER"
            if e.response.status_code == 429:
                logger.warning("Rate limited for tenant %s", tenant.tenant_id)
                return "NO_ANSWER"
            logger.error("LLM request failed for tenant %s: %s", tenant.tenant_id, e)
            return FALLBACK_MESSAGE
        except Exception as e:
            logger.error("LLM request failed for tenant %s: %s", tenant.tenant_id, e)
            return FALLBACK_MESSAGE

    async def validate_api_key(self, raw_key: str) -> bool:
        """Test an API key by making a minimal request. Used during onboarding."""
        try:
            response = await self.client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {raw_key}"},
                json={
                    "model": settings.openrouter_model,
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 1,
                },
            )
            return response.status_code != 401
        except Exception:
            return False

    async def _notify_owner_bad_key(self, tenant: "TenantContext") -> None:
        """Send notification to tenant owner about invalid API key."""
        from bot import state
        if state.bot_instance:
            try:
                await state.bot_instance.send_message(
                    tenant.owner_user_id,
                    f"Ваш API ключ OpenRouter для проекта \"{tenant.project_name}\" "
                    f"недействителен (ошибка 401). Бот не сможет отвечать, пока ключ не будет обновлён.\n\n"
                    f"Перейдите в Настройки для обновления ключа.",
                )
            except Exception as e:
                logger.error("Failed to notify owner %d: %s", tenant.owner_user_id, e)
