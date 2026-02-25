"""Shared formatting utilities for Telegram message output.

Converts LLM Markdown to Telegram HTML and provides safe sending
with fallback to plain text.
"""

import html
import logging
import re

from aiogram.enums import ParseMode
from aiogram.types import Message

logger = logging.getLogger(__name__)


def markdown_to_telegram_html(text: str) -> str:
    """Convert LLM Markdown to Telegram-compatible HTML.

    Handles code blocks, inline code, bold, italic, and strikethrough.
    Falls back gracefully — unmatched markers are left as-is.
    """
    result = []
    # Split on fenced code blocks first (```...```)
    parts = re.split(r"(```[\s\S]*?```)", text)

    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            # Fenced code block — extract optional language and content
            inner = part[3:-3]
            # Strip leading language identifier line (e.g. "python\n")
            if inner and not inner[0].isspace():
                first_nl = inner.find("\n")
                if first_nl != -1:
                    inner = inner[first_nl + 1:]
                else:
                    inner = ""
            result.append(f"<pre>{html.escape(inner)}</pre>")
        else:
            # Escape HTML entities first
            chunk = html.escape(part)
            # Inline code: `text`
            chunk = re.sub(r"`([^`]+)`", r"<code>\1</code>", chunk)
            # Bold: **text** or __text__
            chunk = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", chunk)
            chunk = re.sub(r"__(.+?)__", r"<b>\1</b>", chunk)
            # Italic: *text* or _text_ (but not inside words with underscores)
            chunk = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<i>\1</i>", chunk)
            chunk = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", chunk)
            # Strikethrough: ~~text~~
            chunk = re.sub(r"~~(.+?)~~", r"<s>\1</s>", chunk)
            result.append(chunk)

    return "".join(result)


async def safe_reply(message: Message, text: str, as_reply: bool = False) -> None:
    """Send message with HTML formatting, splitting long messages.

    Args:
        message: The message to respond to.
        text: Raw text (may contain Markdown).
        as_reply: If True, reply to the original message instead of sending a new one.
    """
    parts = split_long_message(text, max_chars=4096)

    for i, part in enumerate(parts):
        # Only reply to the first part
        send = message.reply if (as_reply and i == 0) else message.answer
        try:
            formatted = markdown_to_telegram_html(part)
            await send(formatted, parse_mode=ParseMode.HTML)
        except Exception:
            logger.warning("HTML parse failed, sending as plain text")
            await send(part)


def split_long_message(text: str, max_chars: int = 4096) -> list[str]:
    """Split text into chunks that fit Telegram's message limit.

    Tries to split at paragraph, sentence, or word boundaries.
    Returns a list of message parts.
    """
    if len(text) <= max_chars:
        return [text]

    parts = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            parts.append(remaining)
            break

        chunk = remaining[:max_chars]

        # Try paragraph boundary
        idx = chunk.rfind("\n\n")
        if idx > max_chars * 0.3:
            parts.append(chunk[:idx].rstrip())
            remaining = remaining[idx:].lstrip("\n")
            continue

        # Try sentence boundary
        for sep in (". ", ".\n", "! ", "!\n", "? ", "?\n"):
            idx = chunk.rfind(sep)
            if idx > max_chars * 0.3:
                parts.append(chunk[:idx + 1].rstrip())
                remaining = remaining[idx + 1:].lstrip()
                break
        else:
            # Fall back to word boundary
            idx = chunk.rfind(" ")
            if idx > max_chars * 0.5:
                parts.append(chunk[:idx])
                remaining = remaining[idx:].lstrip()
            else:
                # Hard cut
                parts.append(chunk)
                remaining = remaining[max_chars:]

    return [p for p in parts if p.strip()]


def truncate_response(text: str, max_chars: int = 4096) -> str:
    """Truncate text at sentence or word boundary. Kept for backward compat."""
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]

    for sep in (". ", ".\n", "! ", "!\n", "? ", "?\n"):
        idx = truncated.rfind(sep)
        if idx > max_chars * 0.5:
            return truncated[: idx + 1].rstrip()

    idx = truncated.rfind(" ")
    if idx > max_chars * 0.7:
        return truncated[:idx] + "..."

    return truncated + "..."
