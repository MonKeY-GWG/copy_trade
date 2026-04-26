from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

import asyncpg


class DatabaseConnection(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...

    async def fetch(self, query: str, *args: object) -> Sequence[Any]: ...


class DatabasePool(Protocol):
    def acquire(self) -> AbstractAsyncContextManager[DatabaseConnection]: ...

    async def close(self) -> None: ...


def normalize_asyncpg_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


async def create_asyncpg_pool(database_url: str) -> DatabasePool:
    return await asyncpg.create_pool(
        dsn=normalize_asyncpg_database_url(database_url),
        min_size=1,
        max_size=5,
    )
