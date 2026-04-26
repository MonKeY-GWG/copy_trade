import asyncpg


def normalize_asyncpg_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


async def connect(database_url: str) -> asyncpg.Connection:
    return await asyncpg.connect(normalize_asyncpg_database_url(database_url))
