import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from copy_trade_api.audit import AuditLogRecord
from copy_trade_api.config import Settings
from copy_trade_api.copy_relationships import (
    CopyRelationshipCreate,
    CopyRelationshipRecord,
    CopyRelationshipUpdate,
    DuplicateCopyRelationshipError,
    PostgresCopyRelationshipRepository,
)
from copy_trade_api.identity import AuthenticatedPrincipal
from copy_trade_api.main import create_app
from copy_trade_domain.events import Exchange

ADMIN_TOKEN = "test-admin-token"


class FakeCopyRelationshipRepository:
    def __init__(self) -> None:
        self.records: list[CopyRelationshipRecord] = []
        self.created_payloads: list[CopyRelationshipCreate] = []
        self.created_principals: list[AuthenticatedPrincipal] = []
        self.updated_payloads: list[tuple[UUID, CopyRelationshipUpdate]] = []
        self.updated_principals: list[AuthenticatedPrincipal] = []
        self.raise_duplicate = False

    async def create(
        self,
        payload: CopyRelationshipCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CopyRelationshipRecord:
        if self.raise_duplicate:
            raise DuplicateCopyRelationshipError
        self.created_payloads.append(payload)
        self.created_principals.append(principal)
        record = make_record(
            active=payload.active,
            max_slippage_bps=payload.max_slippage_bps,
            effective_from=payload.effective_from,
        )
        self.records.append(record)
        return record

    async def list(
        self,
        *,
        active: bool | None,
        source_account_id: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[CopyRelationshipRecord]:
        records = self.records
        if active is not None:
            records = [record for record in records if record.active is active]
        if source_account_id is not None:
            records = [
                record for record in records if record.source_account_id == source_account_id
            ]
        return records[offset : offset + limit]

    async def update(
        self,
        relationship_id: UUID,
        payload: CopyRelationshipUpdate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CopyRelationshipRecord | None:
        self.updated_payloads.append((relationship_id, payload))
        self.updated_principals.append(principal)
        for index, record in enumerate(self.records):
            if record.id == relationship_id:
                updated = CopyRelationshipRecord(
                    id=record.id,
                    source_exchange=record.source_exchange,
                    source_account_id=record.source_account_id,
                    source_symbol=record.source_symbol,
                    follower_account_id=record.follower_account_id,
                    target_exchange=record.target_exchange,
                    target_symbol=record.target_symbol,
                    max_slippage_bps=(
                        payload.max_slippage_bps
                        if payload.max_slippage_bps is not None
                        else record.max_slippage_bps
                    ),
                    active=payload.active if payload.active is not None else record.active,
                    effective_from=record.effective_from,
                    created_at=record.created_at,
                    updated_at=datetime.now(UTC),
                )
                self.records[index] = updated
                return updated
        return None


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.records: list[AuditLogRecord] = []

    async def list(
        self,
        *,
        entity_type: str | None,
        entity_id: UUID | None,
        action: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[AuditLogRecord]:
        records = self.records
        if entity_type is not None:
            records = [record for record in records if record.entity_type == entity_type]
        if entity_id is not None:
            records = [record for record in records if record.entity_id == entity_id]
        if action is not None:
            records = [record for record in records if record.action == action]
        return records[offset : offset + limit]


class FakeAdminCredentialRepository:
    def __init__(
        self,
        principal: AuthenticatedPrincipal | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.principal = principal
        self.error = error
        self.tokens: list[str] = []

    async def authenticate_admin_token(self, token: str) -> AuthenticatedPrincipal | None:
        self.tokens.append(token)
        if self.error is not None:
            raise self.error
        return self.principal


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class FakeConnection:
    def __init__(self, rows: Sequence[dict[str, object] | None]) -> None:
        self._rows = list(rows)
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[object, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self._rows.pop(0)

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append(args)
        return "INSERT 0 1"

    async def close(self) -> None:
        self.closed = True


def make_settings(admin_api_token: str | None = ADMIN_TOKEN) -> Settings:
    return make_settings_for_env(env="test", admin_api_token=admin_api_token)


def make_settings_for_env(
    env: str,
    admin_api_token: str | None = ADMIN_TOKEN,
    *,
    allow_environment_admin_token: bool = False,
    admin_rate_limit_requests: int = 120,
    admin_rate_limit_window_seconds: float = 60.0,
) -> Settings:
    return Settings(
        env=env,
        service_name="copy-trade-api",
        api_version="0.1.0",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        nats_url="nats://localhost:4222",
        admin_api_token=admin_api_token,
        allow_environment_admin_token=allow_environment_admin_token,
        admin_rate_limit_requests=admin_rate_limit_requests,
        admin_rate_limit_window_seconds=admin_rate_limit_window_seconds,
    )


def make_record(
    *,
    active: bool = True,
    max_slippage_bps: int = 100,
    effective_from: datetime | None = None,
) -> CopyRelationshipRecord:
    now = datetime.now(UTC)
    return CopyRelationshipRecord(
        id=uuid4(),
        source_exchange=Exchange.HYPERLIQUID,
        source_account_id="trader-1",
        source_symbol="BTC-USD",
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
        max_slippage_bps=max_slippage_bps,
        active=active,
        effective_from=effective_from or now,
        created_at=now,
        updated_at=now,
    )


def make_row(
    *,
    relationship_id: UUID | None = None,
    active: bool = True,
    max_slippage_bps: int = 100,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": relationship_id or uuid4(),
        "source_exchange": Exchange.HYPERLIQUID.value,
        "source_account_id": "trader-1",
        "source_symbol": "BTC-USD",
        "follower_account_id": "follower-1",
        "target_exchange": Exchange.BLOFIN.value,
        "target_symbol": "BTC-USDT",
        "max_slippage_bps": max_slippage_bps,
        "active": active,
        "effective_from": now,
        "created_at": now,
        "updated_at": now,
    }


def make_audit_log_record(
    *,
    entity_id: UUID | None = None,
    action: str = "copy_relationship.created",
) -> AuditLogRecord:
    now = datetime.now(UTC)
    return AuditLogRecord(
        id=uuid4(),
        occurred_at=now,
        actor_type="admin_api",
        actor_id=None,
        action=action,
        entity_type="copy_relationship",
        entity_id=entity_id or uuid4(),
        before_state=None,
        after_state={"active": True},
        metadata_json={},
    )


def make_admin_principal(*, roles: tuple[str, ...] = ("admin",)) -> AuthenticatedPrincipal:
    user_id = uuid4()
    return AuthenticatedPrincipal(
        user_id=user_id,
        credential_id=uuid4(),
        roles=roles,
        actor_type="user",
        actor_id=str(user_id),
        source="database",
    )


def make_environment_principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=None,
        credential_id=None,
        roles=("admin",),
        actor_type="admin_api",
        actor_id=None,
        source="environment",
    )


def make_client(
    repository: FakeCopyRelationshipRepository | None = None,
    *,
    admin_api_token: str | None = ADMIN_TOKEN,
    audit_repository: FakeAuditLogRepository | None = None,
    admin_credential_repository: FakeAdminCredentialRepository | None = None,
    settings: Settings | None = None,
) -> TestClient:
    effective_settings = settings or make_settings(admin_api_token)
    if admin_credential_repository is None:
        admin_credential_repository = FakeAdminCredentialRepository(
            make_admin_principal() if effective_settings.admin_api_token is not None else None,
        )
    return TestClient(
        create_app(
            settings=effective_settings,
            copy_relationship_repository=repository or FakeCopyRelationshipRepository(),
            audit_log_repository=audit_repository or FakeAuditLogRepository(),
            admin_credential_repository=admin_credential_repository,
        )
    )


def auth_headers(token: str = ADMIN_TOKEN) -> dict[str, str]:
    return {"X-Copy-Trade-Admin-Token": token}


def create_payload() -> dict[str, object]:
    return {
        "source_exchange": "hyperliquid",
        "source_account_id": "trader-1",
        "source_symbol": "BTC-USD",
        "follower_account_id": "follower-1",
        "target_exchange": "blofin",
        "target_symbol": "BTC-USDT",
        "max_slippage_bps": 100,
        "active": True,
        "effective_from": "2026-04-26T12:00:00+00:00",
    }


def test_copy_relationship_endpoints_require_admin_token() -> None:
    client = make_client()

    response = client.get("/admin/copy-relationships")

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_copy_relationship_endpoints_return_401_when_no_admin_credential_matches() -> None:
    client = make_client(admin_api_token=None)

    response = client.get("/admin/copy-relationships", headers=auth_headers())

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_copy_relationship_endpoints_accept_database_admin_principal() -> None:
    repository = FakeAdminCredentialRepository(make_admin_principal())
    client = make_client(admin_api_token=None, admin_credential_repository=repository)

    response = client.get(
        "/admin/copy-relationships",
        headers=auth_headers("db-admin-token"),
    )

    assert response.status_code == 200
    assert repository.tokens == ["db-admin-token"]


def test_copy_relationship_endpoints_reject_non_admin_database_principal() -> None:
    repository = FakeAdminCredentialRepository(make_admin_principal(roles=("trader",)))
    client = make_client(admin_api_token=None, admin_credential_repository=repository)

    response = client.get(
        "/admin/copy-relationships",
        headers=auth_headers("db-trader-token"),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_local_environment_admin_token_is_fallback_when_database_auth_fails() -> None:
    repository = FakeAdminCredentialRepository(error=RuntimeError("database unavailable"))
    client = make_client(
        admin_credential_repository=repository,
        settings=make_settings_for_env("local", allow_environment_admin_token=True),
    )

    response = client.get("/admin/copy-relationships", headers=auth_headers())

    assert response.status_code == 200


def test_environment_admin_token_requires_explicit_flag() -> None:
    repository = FakeAdminCredentialRepository(error=RuntimeError("database unavailable"))
    client = make_client(
        admin_credential_repository=repository,
        settings=make_settings_for_env("local", allow_environment_admin_token=False),
    )

    response = client.get("/admin/copy-relationships", headers=auth_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": "admin identity backend is unavailable"}


def test_prod_environment_admin_token_is_not_a_database_auth_bypass() -> None:
    repository = FakeAdminCredentialRepository(error=RuntimeError("database unavailable"))
    client = make_client(
        admin_credential_repository=repository,
        settings=make_settings_for_env("prod", allow_environment_admin_token=True),
    )

    response = client.get("/admin/copy-relationships", headers=auth_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": "admin identity backend is unavailable"}


def test_admin_routes_are_rate_limited() -> None:
    client = make_client(
        settings=make_settings_for_env(
            "test",
            admin_rate_limit_requests=2,
            admin_rate_limit_window_seconds=60.0,
        ),
    )

    first_response = client.get("/admin/copy-relationships", headers=auth_headers())
    second_response = client.get("/admin/copy-relationships", headers=auth_headers())
    third_response = client.get("/admin/copy-relationships", headers=auth_headers())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 429
    assert third_response.json() == {"detail": "rate limit exceeded"}


def test_create_copy_relationship_returns_created_relationship() -> None:
    repository = FakeCopyRelationshipRepository()
    client = make_client(repository)

    response = client.post(
        "/admin/copy-relationships",
        json=create_payload(),
        headers=auth_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_exchange"] == "hyperliquid"
    assert body["source_account_id"] == "trader-1"
    assert body["target_exchange"] == "blofin"
    assert body["target_symbol"] == "BTC-USDT"
    assert body["max_slippage_bps"] == 100
    assert repository.created_payloads[0].effective_from.tzinfo is not None


def test_create_copy_relationship_rejects_naive_effective_from() -> None:
    client = make_client()
    payload = create_payload()
    payload["effective_from"] = "2026-04-26T12:00:00"

    response = client.post(
        "/admin/copy-relationships",
        json=payload,
        headers=auth_headers(),
    )

    assert response.status_code == 422


def test_create_copy_relationship_returns_409_for_duplicate_active_relationship() -> None:
    repository = FakeCopyRelationshipRepository()
    repository.raise_duplicate = True
    client = make_client(repository)

    response = client.post(
        "/admin/copy-relationships",
        json=create_payload(),
        headers=auth_headers(),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "active copy relationship already exists"}


def test_list_copy_relationships_returns_filtered_items() -> None:
    repository = FakeCopyRelationshipRepository()
    repository.records = [make_record(active=True), make_record(active=False)]
    client = make_client(repository)

    response = client.get(
        "/admin/copy-relationships?active=true&source_account_id=trader-1&limit=10&offset=0",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["active"] is True


def test_update_copy_relationship_deactivates_relationship() -> None:
    repository = FakeCopyRelationshipRepository()
    record = make_record(active=True)
    repository.records = [record]
    client = make_client(repository)

    response = client.patch(
        f"/admin/copy-relationships/{record.id}",
        json={"active": False},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False
    assert repository.updated_payloads[0][0] == record.id


def test_update_copy_relationship_returns_404_for_missing_relationship() -> None:
    client = make_client(FakeCopyRelationshipRepository())

    response = client.patch(
        f"/admin/copy-relationships/{uuid4()}",
        json={"active": False},
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "copy relationship not found"}


def test_update_copy_relationship_requires_at_least_one_field() -> None:
    client = make_client()

    response = client.patch(
        f"/admin/copy-relationships/{uuid4()}",
        json={},
        headers=auth_headers(),
    )

    assert response.status_code == 422


def test_list_audit_logs_returns_filtered_items() -> None:
    entity_id = uuid4()
    audit_repository = FakeAuditLogRepository()
    audit_repository.records = [
        make_audit_log_record(entity_id=entity_id),
        make_audit_log_record(action="copy_relationship.updated"),
    ]
    client = make_client(audit_repository=audit_repository)

    response = client.get(
        f"/admin/audit-logs?entity_type=copy_relationship&entity_id={entity_id}",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["entity_id"] == str(entity_id)
    assert body["items"][0]["metadata"] == {}


async def test_postgres_repository_create_writes_audit_log(monkeypatch: pytest.MonkeyPatch) -> None:
    row = make_row()
    connection = FakeConnection([row])

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.copy_relationships.connect", fake_connect)
    repository = PostgresCopyRelationshipRepository(make_settings())

    record = await repository.create(
        CopyRelationshipCreate.model_validate(create_payload()),
        principal=make_environment_principal(),
    )

    assert record.id == row["id"]
    assert connection.closed is True
    assert len(connection.execute_calls) == 1
    audit_args = connection.execute_calls[0]
    assert audit_args[1] == "admin_api"
    assert audit_args[2] is None
    assert audit_args[3] == "copy_relationship.created"
    assert audit_args[4] == "copy_relationship"
    assert audit_args[5] == row["id"]
    assert audit_args[6] is None
    after_state = json.loads(audit_args[7])
    assert after_state["id"] == str(row["id"])
    assert after_state["source_account_id"] == "trader-1"
    assert "X-Copy-Trade-Admin-Token" not in json.dumps(after_state)


async def test_postgres_repository_update_writes_before_and_after_audit_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relationship_id = uuid4()
    before_row = make_row(relationship_id=relationship_id, active=True, max_slippage_bps=100)
    after_row = make_row(relationship_id=relationship_id, active=False, max_slippage_bps=150)
    connection = FakeConnection([before_row, after_row])

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.copy_relationships.connect", fake_connect)
    repository = PostgresCopyRelationshipRepository(make_settings())

    record = await repository.update(
        relationship_id,
        CopyRelationshipUpdate(active=False, max_slippage_bps=150),
        principal=make_environment_principal(),
    )

    assert record is not None
    assert record.active is False
    assert len(connection.execute_calls) == 1
    audit_args = connection.execute_calls[0]
    assert audit_args[3] == "copy_relationship.updated"
    before_state = json.loads(audit_args[6])
    after_state = json.loads(audit_args[7])
    assert before_state["active"] is True
    assert before_state["max_slippage_bps"] == 100
    assert after_state["active"] is False
    assert after_state["max_slippage_bps"] == 150


async def test_postgres_repository_audit_log_uses_database_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = make_row()
    connection = FakeConnection([row])

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.copy_relationships.connect", fake_connect)
    repository = PostgresCopyRelationshipRepository(make_settings())
    principal = make_admin_principal()

    await repository.create(
        CopyRelationshipCreate.model_validate(create_payload()),
        principal=principal,
    )

    audit_args = connection.execute_calls[0]
    assert audit_args[1] == "user"
    assert audit_args[2] == principal.actor_id
