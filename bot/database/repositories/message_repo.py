"""Message repository — CRUD for messages and conversation summaries with tenant isolation."""

from uuid import UUID

from bot.database.connection import Database


class MessageRepo:
    def __init__(self, db: Database):
        self.db = db

    async def save(
        self,
        tenant_id: UUID,
        user_id: int,
        chat_id: int,
        chat_type: str,
        role: str,
        content: str,
    ) -> int:
        """Save a message. Returns the message ID."""
        return await self.db.fetchval(
            """
            INSERT INTO messages (tenant_id, user_id, chat_id, chat_type, role, content)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            tenant_id, user_id, chat_id, chat_type, role, content,
        )

    async def get_recent(
        self, user_id: int, chat_id: int, tenant_id: UUID, limit: int = 10
    ) -> list[dict]:
        """Get recent messages in chronological order."""
        rows = await self.db.fetch(
            """
            SELECT role, content FROM messages
            WHERE user_id = $1 AND chat_id = $2 AND tenant_id = $3
            ORDER BY created_at DESC
            LIMIT $4
            """,
            user_id, chat_id, tenant_id, limit,
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def get_context(
        self, user_id: int, chat_id: int, tenant_id: UUID, limit: int = 10
    ) -> list[dict]:
        """Smart context: latest summary + messages after it, or just recent messages."""
        summary = await self.db.fetchrow(
            """
            SELECT summary, messages_to FROM conversation_summaries
            WHERE user_id = $1 AND chat_id = $2 AND tenant_id = $3
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id, chat_id, tenant_id,
        )

        if summary:
            context = [{"role": "system", "content": f"Краткое содержание предыдущего разговора:\n{summary['summary']}"}]
            rows = await self.db.fetch(
                """
                SELECT role, content FROM messages
                WHERE user_id = $1 AND chat_id = $2 AND tenant_id = $3
                  AND id > $4
                ORDER BY created_at ASC
                """,
                user_id, chat_id, tenant_id, summary["messages_to"],
            )
            context.extend({"role": r["role"], "content": r["content"]} for r in rows)
            return context

        return await self.get_recent(user_id, chat_id, tenant_id, limit)

    async def count_uncompacted(
        self, user_id: int, chat_id: int, tenant_id: UUID
    ) -> int:
        """Count messages not yet covered by a summary."""
        last_to = await self.db.fetchval(
            """
            SELECT COALESCE(MAX(messages_to), 0) FROM conversation_summaries
            WHERE user_id = $1 AND chat_id = $2 AND tenant_id = $3
            """,
            user_id, chat_id, tenant_id,
        )
        return await self.db.fetchval(
            """
            SELECT COUNT(*) FROM messages
            WHERE user_id = $1 AND chat_id = $2 AND tenant_id = $3 AND id > $4
            """,
            user_id, chat_id, tenant_id, last_to,
        ) or 0

    async def get_for_compaction(
        self, user_id: int, chat_id: int, tenant_id: UUID, keep_recent: int = 10
    ) -> tuple[list, int | None, int | None]:
        """Get messages to compact. Returns (messages_to_summarize, from_id, to_id)."""
        last_to = await self.db.fetchval(
            """
            SELECT COALESCE(MAX(messages_to), 0) FROM conversation_summaries
            WHERE user_id = $1 AND chat_id = $2 AND tenant_id = $3
            """,
            user_id, chat_id, tenant_id,
        )
        rows = await self.db.fetch(
            """
            SELECT id, role, content FROM messages
            WHERE user_id = $1 AND chat_id = $2 AND tenant_id = $3 AND id > $4
            ORDER BY created_at ASC
            """,
            user_id, chat_id, tenant_id, last_to,
        )
        if len(rows) <= keep_recent:
            return [], None, None

        to_summarize = rows[:-keep_recent]
        return (
            [{"role": r["role"], "content": r["content"]} for r in to_summarize],
            to_summarize[0]["id"],
            to_summarize[-1]["id"],
        )

    async def save_summary(
        self,
        user_id: int,
        chat_id: int,
        tenant_id: UUID,
        summary: str,
        messages_from: int,
        messages_to: int,
    ):
        await self.db.execute(
            """
            INSERT INTO conversation_summaries
                (tenant_id, user_id, chat_id, summary, messages_from, messages_to)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            tenant_id, user_id, chat_id, summary, messages_from, messages_to,
        )

    async def get_recent_group_context(
        self, chat_id: int, tenant_id: UUID, limit: int = 6
    ) -> list[dict]:
        """Get recent group messages for context."""
        rows = await self.db.fetch(
            """
            SELECT role, content FROM messages
            WHERE chat_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            chat_id, tenant_id, limit,
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def count_recent_bot_messages(
        self, chat_id: int, tenant_id: UUID, seconds: int = 15
    ) -> int:
        """Count bot messages in last N seconds (for rate limiting)."""
        return await self.db.fetchval(
            """
            SELECT COUNT(*) FROM messages
            WHERE chat_id = $1 AND tenant_id = $2
              AND role = 'assistant'
              AND created_at > NOW() - $3 * INTERVAL '1 second'
            """,
            chat_id, tenant_id, seconds,
        ) or 0

    async def add_faq_candidate(
        self, tenant_id: UUID, question: str, answer: str, message_id: int
    ):
        """Upsert FAQ candidate: increment frequency or insert new."""
        existing = await self.db.fetchrow(
            "SELECT id, frequency, source_message_ids FROM faq_candidates WHERE tenant_id = $1 AND question = $2",
            tenant_id, question,
        )
        if existing:
            ids = f"{existing['source_message_ids']},{message_id}" if existing['source_message_ids'] else str(message_id)
            await self.db.execute(
                "UPDATE faq_candidates SET frequency = frequency + 1, source_message_ids = $1 WHERE id = $2",
                ids, existing["id"],
            )
        else:
            await self.db.execute(
                """
                INSERT INTO faq_candidates (tenant_id, question, answer, frequency, source_message_ids)
                VALUES ($1, $2, $3, 1, $4)
                """,
                tenant_id, question, answer, str(message_id),
            )

    async def get_faq_candidates(self, tenant_id: UUID, limit: int = 20):
        return await self.db.fetch(
            """
            SELECT id, question, answer, frequency, created_at
            FROM faq_candidates
            WHERE tenant_id = $1
            ORDER BY frequency DESC
            LIMIT $2
            """,
            tenant_id, limit,
        )
