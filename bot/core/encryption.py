"""Fernet encryption for tenant API keys.

API keys are encrypted at rest in PostgreSQL.
The ENCRYPTION_KEY is stored only in environment variables, never in the database.
"""

from cryptography.fernet import Fernet

from bot.config import settings

_fernet = Fernet(settings.encryption_key.encode())


def encrypt_api_key(key: str) -> str:
    """Encrypt an OpenRouter API key for storage."""
    return _fernet.encrypt(key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt an OpenRouter API key for use."""
    return _fernet.decrypt(encrypted.encode()).decode()
