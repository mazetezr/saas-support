"""PostgreSQL connection pool manager using asyncpg.

Replaces the single-connection SQLite DatabaseManager from the original bot.
Uses a connection pool (min=5, max=20) for concurrent request handling.
"""

import logging

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


class Database:
    """Async PostgreSQL connection pool manager."""

    def __init__(self, database_url: str):
        # asyncpg expects postgresql:// scheme, strip +asyncpg if present
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        """Create connection pool and register pgvector type."""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=5,
            max_size=20,
            command_timeout=60,
            init=self._init_connection,
        )
        logger.info("PostgreSQL connection pool initialized")

    @staticmethod
    async def _init_connection(conn: asyncpg.Connection) -> None:
        """Initialize each connection with pgvector codec."""
        await register_vector(conn)

    async def close(self) -> None:
        """Close connection pool gracefully."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Execute query and return all rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """Execute query and return first row or None."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Execute query and return first column of first row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        """Execute a write operation (INSERT/UPDATE/DELETE)."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args: list) -> None:
        """Execute a query for each set of args."""
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)
