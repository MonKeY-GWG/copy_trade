from uuid import uuid4

import pytest

from copy_trade_api.config import Settings
from copy_trade_api.identity import (
    ADMIN_API_CREDENTIAL_TYPE,
    AuthenticatedPrincipal,
    PostgresAdminCredentialRepository,
    hash_api_token,
)

ADMIN_DB_TOKEN = "db-admin-token-" + ("a" * 32)
TRADER_DB_TOKEN = "db-trader-token-" + ("b" * 32)
UNKNOWN_DB_TOKEN = "unknown-token-" + ("c" * 32)


class FakeConnection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.row

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        return "UPDATE 1"

    async def close(self) -> None:
        self.closed = True


def make_settings() -> Settings:
    return Settings(
        env="test",
        service_name="copy-trade-api",
        api_version="0.1.0",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        nats_url="nats://localhost:4222",
        admin_api_token=None,
    )


def test_hash_api_token_is_stable_and_not_plaintext() -> None:
    token = "high-entropy-admin-token"

    digest = hash_api_token(token)

    assert digest == hash_api_token(token)
    assert digest != token
    assert len(digest) == 64


async def test_postgres_admin_repository_accepts_admin_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    credential_id = uuid4()
    connection = FakeConnection(
        {
            "user_id": user_id,
            "credential_id": credential_id,
            "roles": ["admin", "trader"],
        }
    )

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.identity.connect", fake_connect)
    repository = PostgresAdminCredentialRepository(make_settings())

    principal = await repository.authenticate_admin_token(ADMIN_DB_TOKEN)

    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.user_id == user_id
    assert principal.credential_id == credential_id
    assert principal.roles == ("admin", "trader")
    assert principal.actor_type == "user"
    assert principal.actor_id == str(user_id)
    assert principal.source == "database"
    assert connection.closed is True
    fetch_args = connection.fetchrow_calls[0][1]
    assert fetch_args[0] == ADMIN_API_CREDENTIAL_TYPE
    assert fetch_args[1] == hash_api_token(ADMIN_DB_TOKEN)
    assert connection.execute_calls[0][1] == (credential_id,)


async def test_postgres_admin_repository_rejects_non_admin_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        {
            "user_id": uuid4(),
            "credential_id": uuid4(),
            "roles": ["trader"],
        }
    )

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.identity.connect", fake_connect)
    repository = PostgresAdminCredentialRepository(make_settings())

    principal = await repository.authenticate_admin_token(TRADER_DB_TOKEN)

    assert principal is None
    assert connection.execute_calls == []
    assert connection.closed is True


async def test_postgres_admin_repository_returns_none_for_unknown_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(None)

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.identity.connect", fake_connect)
    repository = PostgresAdminCredentialRepository(make_settings())

    principal = await repository.authenticate_admin_token(UNKNOWN_DB_TOKEN)

    assert principal is None
    assert connection.execute_calls == []
    assert connection.closed is True


async def test_postgres_admin_repository_rejects_short_token_without_database_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_connect(_database_url: str) -> FakeConnection:
        raise AssertionError("short token should not query the database")

    monkeypatch.setattr("copy_trade_api.identity.connect", fake_connect)
    repository = PostgresAdminCredentialRepository(make_settings())

    principal = await repository.authenticate_admin_token("short-token")

    assert principal is None
