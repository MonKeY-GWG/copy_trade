import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    nats_url: str
    database_url: str


def _env(name: str, default: str) -> str:
    return os.getenv(f"COPY_TRADE_{name}", default)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        nats_url=_env("NATS_URL", "nats://localhost:4222"),
        database_url=_env(
            "DATABASE_URL",
            "postgresql+asyncpg://copy_trade:copy_trade@localhost:5432/copy_trade",
        ),
    )
