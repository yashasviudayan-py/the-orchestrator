"""
Redis client with connection pooling and health checks.
Provides robust connection management with automatic reconnection.
"""

import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError, RedisError

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client with connection pooling and health monitoring."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        max_connections: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        """
        Initialize Redis client.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Optional password
            max_connections: Maximum connections in pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password

        # Create connection pool
        self.pool = ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            decode_responses=True,  # Auto-decode bytes to str
        )

        self._client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to Redis."""
        try:
            self._client = redis.Redis(connection_pool=self.pool)
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
        except (ConnectionError, TimeoutError) as e:
            self._connected = False
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Redis connection and cleanup pool."""
        if self._client:
            await self._client.aclose()
            await self.pool.aclose()
            self._connected = False
            logger.info("Disconnected from Redis")

    async def health_check(self) -> bool:
        """
        Check if Redis is healthy.

        Returns:
            True if Redis responds to PING, False otherwise
        """
        if not self._connected or not self._client:
            return False

        try:
            await self._client.ping()
            return True
        except RedisError:
            return False

    @asynccontextmanager
    async def _ensure_connection(self):
        """
        Context manager to ensure connection is active.
        Attempts reconnection if needed.
        """
        if not self._connected or not await self.health_check():
            logger.warning("Redis connection lost, attempting reconnection...")
            await self.connect()

        try:
            yield self._client
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis operation failed: {e}")
            self._connected = False
            raise

    async def get(self, key: str) -> Optional[str]:
        """
        Get value for key.

        Args:
            key: Redis key

        Returns:
            Value or None if key doesn't exist
        """
        async with self._ensure_connection() as client:
            return await client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        nx: bool = False,
    ) -> bool:
        """
        Set key to value.

        Args:
            key: Redis key
            value: Value to set
            ex: Expiration in seconds
            nx: Only set if key doesn't exist

        Returns:
            True if successful
        """
        async with self._ensure_connection() as client:
            result = await client.set(key, value, ex=ex, nx=nx)
            return bool(result)

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys.

        Args:
            keys: Keys to delete

        Returns:
            Number of keys deleted
        """
        async with self._ensure_connection() as client:
            return await client.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """
        Check if keys exist.

        Args:
            keys: Keys to check

        Returns:
            Number of existing keys
        """
        async with self._ensure_connection() as client:
            return await client.exists(*keys)

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration on key.

        Args:
            key: Redis key
            seconds: TTL in seconds

        Returns:
            True if successful
        """
        async with self._ensure_connection() as client:
            return await client.expire(key, seconds)

    async def keys(self, pattern: str = "*") -> list[str]:
        """
        Find keys matching pattern.

        Args:
            pattern: Pattern to match (e.g., "task:*")

        Returns:
            List of matching keys
        """
        async with self._ensure_connection() as client:
            return await client.keys(pattern)

    async def hset(self, name: str, mapping: dict) -> int:
        """
        Set hash fields.

        Args:
            name: Hash key
            mapping: Dict of field->value

        Returns:
            Number of fields added
        """
        async with self._ensure_connection() as client:
            return await client.hset(name, mapping=mapping)

    async def hgetall(self, name: str) -> dict:
        """
        Get all hash fields.

        Args:
            name: Hash key

        Returns:
            Dict of field->value
        """
        async with self._ensure_connection() as client:
            return await client.hgetall(name)

    async def lpush(self, key: str, *values: str) -> int:
        """
        Push values to list (left/head).

        Args:
            key: List key
            values: Values to push

        Returns:
            List length after push
        """
        async with self._ensure_connection() as client:
            return await client.lpush(key, *values)

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> list[str]:
        """
        Get list range.

        Args:
            key: List key
            start: Start index
            end: End index (-1 for all)

        Returns:
            List of values
        """
        async with self._ensure_connection() as client:
            return await client.lrange(key, start, end)

    async def flushdb(self) -> bool:
        """
        Clear current database. USE WITH CAUTION.

        Returns:
            True if successful
        """
        async with self._ensure_connection() as client:
            await client.flushdb()
            logger.warning(f"Flushed Redis database {self.db}")
            return True


# Singleton instance
_redis_client: Optional[RedisClient] = None


def get_redis_client(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
) -> RedisClient:
    """
    Get or create Redis client singleton.

    Args:
        host: Redis host
        port: Redis port
        db: Redis database
        password: Optional password

    Returns:
        RedisClient instance
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(
            host=host,
            port=port,
            db=db,
            password=password,
        )
    return _redis_client
