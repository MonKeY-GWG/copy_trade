from typing import Protocol

from copy_trade_copy_engine.database import DatabasePool

INSERT_IDEMPOTENCY_KEY_SQL = """
INSERT INTO copy_execution_idempotency (idempotency_key)
VALUES ($1)
ON CONFLICT (idempotency_key) DO NOTHING
"""

DELETE_IDEMPOTENCY_KEY_SQL = """
DELETE FROM copy_execution_idempotency
WHERE idempotency_key = $1
"""


class IdempotencyStore(Protocol):
    async def reserve(self, key: str) -> bool:
        raise NotImplementedError

    async def release(self, key: str) -> None:
        raise NotImplementedError


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._reserved_keys: set[str] = set()

    async def reserve(self, key: str) -> bool:
        if key in self._reserved_keys:
            return False
        self._reserved_keys.add(key)
        return True

    async def release(self, key: str) -> None:
        self._reserved_keys.discard(key)


class PostgresIdempotencyStore:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def reserve(self, key: str) -> bool:
        async with self._pool.acquire() as connection:
            result = await connection.execute(INSERT_IDEMPOTENCY_KEY_SQL, key)
        return result == "INSERT 0 1"

    async def release(self, key: str) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(DELETE_IDEMPOTENCY_KEY_SQL, key)
