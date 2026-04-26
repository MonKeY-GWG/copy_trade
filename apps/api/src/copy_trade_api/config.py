import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    env: str
    service_name: str
    api_version: str
    database_url: str
    redis_url: str
    nats_url: str
    admin_api_token: str | None


def _env(name: str, default: str) -> str:
    return os.getenv(f"COPY_TRADE_{name}", default)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        env=_env("ENV", "local"),
        service_name=_env("SERVICE_NAME", "copy-trade-api"),
        api_version=_env("API_VERSION", "0.1.0"),
        database_url=_env(
            "DATABASE_URL",
            "postgresql+asyncpg://copy_trade:copy_trade@localhost:5432/copy_trade",
        ),
        redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
        nats_url=_env("NATS_URL", "nats://localhost:4222"),
        admin_api_token=os.getenv("COPY_TRADE_ADMIN_API_TOKEN"),
    )
