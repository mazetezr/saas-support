"""TenantContext dataclass for multi-tenancy.

Represents the resolved tenant for the current request.
Serializable to/from JSON for Redis caching.
"""

import json
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class TenantContext:
    tenant_id: UUID
    owner_user_id: int
    project_name: str
    chat_id: int | None
    chat_title: str | None
    moderator_usernames: list[str]
    persona_doc: str | None
    language: str
    relevance_threshold: float
    openrouter_api_key: str  # encrypted
    status: str
    is_active: bool
    rate_limit_per_minute: int = 5
    rate_limit_per_day: int = 50

    def to_json(self) -> str:
        """Serialize for Redis cache storage."""
        return json.dumps({
            "tenant_id": str(self.tenant_id),
            "owner_user_id": self.owner_user_id,
            "project_name": self.project_name,
            "chat_id": self.chat_id,
            "chat_title": self.chat_title,
            "moderator_usernames": self.moderator_usernames,
            "persona_doc": self.persona_doc,
            "language": self.language,
            "relevance_threshold": self.relevance_threshold,
            "openrouter_api_key": self.openrouter_api_key,
            "status": self.status,
            "is_active": self.is_active,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "rate_limit_per_day": self.rate_limit_per_day,
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> "TenantContext":
        """Deserialize from Redis cache."""
        d = json.loads(data)
        return cls(
            tenant_id=UUID(d["tenant_id"]),
            owner_user_id=d["owner_user_id"],
            project_name=d["project_name"],
            chat_id=d["chat_id"],
            chat_title=d["chat_title"],
            moderator_usernames=d.get("moderator_usernames", []),
            persona_doc=d.get("persona_doc"),
            language=d.get("language", "ru"),
            relevance_threshold=d.get("relevance_threshold", 0.75),
            openrouter_api_key=d["openrouter_api_key"],
            status=d["status"],
            is_active=d.get("is_active", True),
            rate_limit_per_minute=d.get("rate_limit_per_minute", 5),
            rate_limit_per_day=d.get("rate_limit_per_day", 50),
        )

    @classmethod
    def from_record(cls, record) -> "TenantContext":
        """Create from asyncpg Record."""
        return cls(
            tenant_id=record["id"],
            owner_user_id=record["owner_user_id"],
            project_name=record["project_name"],
            chat_id=record["chat_id"],
            chat_title=record["chat_title"],
            moderator_usernames=record.get("moderator_usernames") or [],
            persona_doc=record.get("persona_doc"),
            language=record.get("language", "ru"),
            relevance_threshold=record.get("relevance_threshold", 0.75),
            openrouter_api_key=record["openrouter_api_key"],
            status=record["status"],
            is_active=record.get("is_active", True),
            rate_limit_per_minute=record.get("rate_limit_per_minute") or 5,
            rate_limit_per_day=record.get("rate_limit_per_day") or 50,
        )
