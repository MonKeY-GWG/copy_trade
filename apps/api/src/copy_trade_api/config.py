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
    allow_environment_admin_token: bool = False
    admin_rate_limit_requests: int = 120
    admin_rate_limit_window_seconds: float = 60.0
    session_cookie_secure: bool = True
    session_ttl_minutes: int = 480
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)


def _env(name: str, default: str) -> str:
    return os.getenv(f"COPY_TRADE_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(f"COPY_TRADE_{name}")
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(f"COPY_TRADE_{name}")
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(f"COPY_TRADE_{name}")
    if value is None:
        return default
    return float(value)


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(f"COPY_TRADE_{name}")
    if value is None:
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


@lru_cache
def get_settings() -> Settings:
    env = _env("ENV", "production")
    return Settings(
        env=env,
        service_name=_env("SERVICE_NAME", "copy-trade-api"),
        api_version=_env("API_VERSION", "0.1.0"),
        database_url=_env(
            "DATABASE_URL",
            "postgresql+asyncpg://copy_trade:copy_trade@localhost:5432/copy_trade",
        ),
        redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
        nats_url=_env("NATS_URL", "nats://localhost:4222"),
        admin_api_token=os.getenv("COPY_TRADE_ADMIN_API_TOKEN"),
        allow_environment_admin_token=_env_bool("ALLOW_ENV_ADMIN_TOKEN", False),
        admin_rate_limit_requests=_env_int("ADMIN_RATE_LIMIT_REQUESTS", 120),
        admin_rate_limit_window_seconds=_env_float("ADMIN_RATE_LIMIT_WINDOW_SECONDS", 60.0),
        session_cookie_secure=_env_bool(
            "SESSION_COOKIE_SECURE",
            env.lower() not in {"dev", "development", "local", "test"},
        ),
        session_ttl_minutes=_env_int("SESSION_TTL_MINUTES", 480),
        cors_origins=_env_csv("CORS_ORIGINS", ("http://localhost:3000",)),
    )
