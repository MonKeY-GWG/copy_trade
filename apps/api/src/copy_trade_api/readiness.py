import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import nats
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from copy_trade_api.config import Settings

DependencyName = Literal["postgres", "redis", "nats"]
DependencyState = Literal["ok", "unavailable"]
DependencyCheck = Callable[[], Awaitable[None]]

READINESS_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class DependencyStatus:
    name: DependencyName
    status: DependencyState


@dataclass(frozen=True)
class ReadinessReport:
    dependencies: tuple[DependencyStatus, ...]

    @property
    def ready(self) -> bool:
        return all(dependency.status == "ok" for dependency in self.dependencies)

    def as_response(self) -> dict[str, str | dict[str, str]]:
        return {
            "status": "ready" if self.ready else "not_ready",
            "dependencies": {
                dependency.name: dependency.status for dependency in self.dependencies
            },
        }


async def check_readiness(settings: Settings) -> ReadinessReport:
    checks: tuple[tuple[DependencyName, DependencyCheck], ...] = (
        ("postgres", lambda: check_postgres(settings.database_url)),
        ("redis", lambda: check_redis(settings.redis_url)),
        ("nats", lambda: check_nats(settings.nats_url)),
    )

    dependencies = await asyncio.gather(
        *(check_dependency(name, check) for name, check in checks),
    )
    return ReadinessReport(dependencies=dependencies)


async def check_dependency(name: DependencyName, check: DependencyCheck) -> DependencyStatus:
    try:
        await asyncio.wait_for(check(), timeout=READINESS_TIMEOUT_SECONDS)
    except Exception:
        return DependencyStatus(name=name, status="unavailable")
    return DependencyStatus(name=name, status="ok")


async def check_postgres(database_url: str) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def check_redis(redis_url: str) -> None:
    client = Redis.from_url(redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def check_nats(nats_url: str) -> None:
    client = await nats.connect(
        servers=nats_url,
        name="copy-trade-api-readiness",
        connect_timeout=READINESS_TIMEOUT_SECONDS,
        allow_reconnect=False,
        max_reconnect_attempts=0,
    )
    try:
        if not client.is_connected:
            raise ConnectionError("nats connection is not active")
    finally:
        await client.close()
