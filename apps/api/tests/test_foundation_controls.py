from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from copy_trade_api.config import Settings
from copy_trade_api.foundation_controls import (
    DeadLetterEventRecord,
    DeadLetterStatus,
    ExchangeAccountCreate,
    ExchangeAccountRecord,
    ExchangeAccountStatus,
    ExchangeAccountUpdate,
    FoundationControlConflictError,
    FoundationControlReferenceNotFoundError,
    PostgresFoundationControlRepository,
    RiskSettingsRecord,
    RiskSettingsUpsert,
    SubscriptionRecord,
    SubscriptionStatus,
    SubscriptionUpsert,
)
from copy_trade_api.identity import AuthenticatedPrincipal
from copy_trade_api.main import create_app
from copy_trade_domain.events import Exchange

ADMIN_TOKEN = "test-admin-token"


class FakeAuthRepository:
    async def authenticate_admin_token(self, _token: str) -> AuthenticatedPrincipal:
        user_id = uuid4()
        return AuthenticatedPrincipal(
            user_id=user_id,
            credential_id=uuid4(),
            roles=("admin",),
            actor_type="user",
            actor_id=str(user_id),
            source="database",
        )


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


class RaisingConnection:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchrow(self, _query: str, *_args: object) -> dict[str, object] | None:
        raise self.error

    async def close(self) -> None:
        self.closed = True


class FakeFoundationControlRepository:
    def __init__(self) -> None:
        self.subscription = make_subscription()
        self.exchange_account = make_exchange_account()
        self.risk_settings = make_risk_settings()
        self.dead_letter_event = make_dead_letter_event()
        self.updated_exchange_payloads: list[ExchangeAccountUpdate] = []
        self.return_none = False
        self.error: Exception | None = None

    async def upsert_subscription(
        self,
        user_id: UUID,
        payload: SubscriptionUpsert,
        *,
        principal: AuthenticatedPrincipal,
    ) -> SubscriptionRecord:
        if self.error is not None:
            raise self.error
        return make_subscription(
            user_id=user_id,
            status=payload.status,
            copy_trading_enabled=payload.copy_trading_enabled,
        )

    async def list_subscriptions(
        self,
        *,
        status_filter: SubscriptionStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[SubscriptionRecord]:
        records = [self.subscription]
        if status_filter is not None:
            records = [record for record in records if record.status == status_filter]
        return records[offset : offset + limit]

    async def create_exchange_account(
        self,
        payload: ExchangeAccountCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> ExchangeAccountRecord:
        if self.error is not None:
            raise self.error
        return make_exchange_account(
            user_id=payload.user_id,
            exchange=payload.exchange,
            account_id=payload.account_id,
            status=payload.status,
            secret_reference=payload.secret_reference,
            secret_fingerprint=payload.secret_fingerprint,
        )

    async def list_exchange_accounts(
        self,
        *,
        user_id: UUID | None,
        status_filter: ExchangeAccountStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[ExchangeAccountRecord]:
        records = [self.exchange_account]
        if user_id is not None:
            records = [record for record in records if record.user_id == user_id]
        if status_filter is not None:
            records = [record for record in records if record.status == status_filter]
        return records[offset : offset + limit]

    async def update_exchange_account(
        self,
        account_id: UUID,
        payload: ExchangeAccountUpdate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> ExchangeAccountRecord | None:
        if self.error is not None:
            raise self.error
        self.updated_exchange_payloads.append(payload)
        if self.return_none:
            return None
        return make_exchange_account(
            record_id=account_id,
            status=payload.status or ExchangeAccountStatus.ACTIVE,
        )

    async def upsert_risk_settings(
        self,
        relationship_id: UUID,
        payload: RiskSettingsUpsert,
        *,
        principal: AuthenticatedPrincipal,
    ) -> RiskSettingsRecord:
        if self.error is not None:
            raise self.error
        return make_risk_settings(
            relationship_id=relationship_id,
            enabled=payload.enabled,
            max_order_quantity=payload.max_order_quantity,
            max_slippage_bps=payload.max_slippage_bps,
            max_leverage=payload.max_leverage,
        )

    async def get_risk_settings(self, relationship_id: UUID) -> RiskSettingsRecord | None:
        if self.return_none:
            return None
        return make_risk_settings(relationship_id=relationship_id)

    async def list_dead_letter_events(
        self,
        *,
        status_filter: DeadLetterStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[DeadLetterEventRecord]:
        records = [self.dead_letter_event]
        if status_filter is not None:
            records = [record for record in records if record.status == status_filter]
        return records[offset : offset + limit]


def make_settings() -> Settings:
    return Settings(
        env="test",
        service_name="copy-trade-api",
        api_version="0.1.0",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        nats_url="nats://localhost:4222",
        admin_api_token=ADMIN_TOKEN,
    )


def make_subscription(
    *,
    user_id: UUID | None = None,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    copy_trading_enabled: bool = True,
) -> SubscriptionRecord:
    now = datetime.now(UTC)
    return SubscriptionRecord(
        user_id=user_id or uuid4(),
        status=status,
        copy_trading_enabled=copy_trading_enabled,
        current_period_end=None,
        created_at=now,
        updated_at=now,
    )


def make_exchange_account(
    *,
    record_id: UUID | None = None,
    user_id: UUID | None = None,
    exchange: Exchange = Exchange.HYPERLIQUID,
    account_id: str = "trader-1",
    status: ExchangeAccountStatus = ExchangeAccountStatus.ACTIVE,
    secret_reference: str | None = "secret://copy-trade/test",
    secret_fingerprint: str | None = "a" * 64,
) -> ExchangeAccountRecord:
    now = datetime.now(UTC)
    return ExchangeAccountRecord(
        id=record_id or uuid4(),
        user_id=user_id or uuid4(),
        exchange=exchange,
        account_id=account_id,
        label="Trader",
        status=status,
        secret_reference=secret_reference,
        secret_fingerprint=secret_fingerprint,
        created_at=now,
        updated_at=now,
    )


def make_risk_settings(
    *,
    relationship_id: UUID | None = None,
    enabled: bool = True,
    max_order_quantity: Decimal | None = Decimal("1.0"),
    max_slippage_bps: int = 100,
    max_leverage: Decimal | None = Decimal("5"),
) -> RiskSettingsRecord:
    now = datetime.now(UTC)
    return RiskSettingsRecord(
        copy_relationship_id=relationship_id or uuid4(),
        enabled=enabled,
        max_order_quantity=max_order_quantity,
        max_slippage_bps=max_slippage_bps,
        max_leverage=max_leverage,
        created_at=now,
        updated_at=now,
    )


def make_dead_letter_event() -> DeadLetterEventRecord:
    now = datetime.now(UTC)
    return DeadLetterEventRecord(
        id=uuid4(),
        idempotency_key="dlq:test",
        failed_subject="exchange.trade_event.normalized",
        delivery_attempt=3,
        max_delivery_attempts=3,
        error_type="RuntimeError",
        payload={
            "event_id": str(uuid4()),
            "api_secret": "do-not-return",
            "raw_response": {"authorization": "Bearer hidden"},
        },
        status=DeadLetterStatus.OPEN,
        created_at=now,
        updated_at=now,
    )


def make_client(repository: FakeFoundationControlRepository) -> TestClient:
    return TestClient(
        create_app(
            settings=make_settings(),
            admin_credential_repository=FakeAuthRepository(),
            foundation_control_repository=repository,
        )
    )


def auth_headers() -> dict[str, str]:
    return {"X-Copy-Trade-Admin-Token": ADMIN_TOKEN}


def make_principal() -> AuthenticatedPrincipal:
    user_id = uuid4()
    return AuthenticatedPrincipal(
        user_id=user_id,
        credential_id=uuid4(),
        roles=("admin",),
        actor_type="user",
        actor_id=str(user_id),
        source="database",
    )


def test_upsert_subscription_returns_subscription_state() -> None:
    repository = FakeFoundationControlRepository()
    client = make_client(repository)
    user_id = uuid4()

    response = client.put(
        f"/admin/identity/users/{user_id}/subscription",
        headers=auth_headers(),
        json={"status": "active", "copy_trading_enabled": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user_id)
    assert body["status"] == "active"
    assert body["copy_trading_enabled"] is True


def test_upsert_subscription_returns_404_for_missing_user() -> None:
    repository = FakeFoundationControlRepository()
    repository.error = FoundationControlReferenceNotFoundError("user not found")
    client = make_client(repository)

    response = client.put(
        f"/admin/identity/users/{uuid4()}/subscription",
        headers=auth_headers(),
        json={"status": "active", "copy_trading_enabled": True},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "user not found"}


def test_create_exchange_account_returns_redacted_secret_metadata() -> None:
    repository = FakeFoundationControlRepository()
    client = make_client(repository)

    response = client.post(
        "/admin/exchange-accounts",
        headers=auth_headers(),
        json={
            "user_id": str(uuid4()),
            "exchange": "hyperliquid",
            "account_id": "trader-1",
            "status": "active",
            "secret_reference": "secret://copy-trade/test",
            "secret_fingerprint": "A" * 64,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["has_secret"] is True
    assert body["secret_fingerprint_prefix"] == "aaaaaaaa"
    assert "secret_reference" not in body
    assert "secret_fingerprint" not in body


def test_create_exchange_account_returns_409_for_duplicate_account() -> None:
    repository = FakeFoundationControlRepository()
    repository.error = FoundationControlConflictError("exchange account already exists")
    client = make_client(repository)

    response = client.post(
        "/admin/exchange-accounts",
        headers=auth_headers(),
        json={
            "user_id": str(uuid4()),
            "exchange": "hyperliquid",
            "account_id": "trader-1",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "exchange account already exists"}


def test_update_exchange_account_returns_404_for_missing_account() -> None:
    repository = FakeFoundationControlRepository()
    repository.return_none = True
    client = make_client(repository)

    response = client.patch(
        f"/admin/exchange-accounts/{uuid4()}",
        headers=auth_headers(),
        json={"status": "disabled"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "exchange account not found"}


def test_update_exchange_account_can_clear_secret_metadata() -> None:
    repository = FakeFoundationControlRepository()
    client = make_client(repository)

    response = client.patch(
        f"/admin/exchange-accounts/{uuid4()}",
        headers=auth_headers(),
        json={"secret_reference": None, "secret_fingerprint": None},
    )

    assert response.status_code == 200
    assert repository.updated_exchange_payloads[0].model_fields_set == {
        "secret_reference",
        "secret_fingerprint",
    }


def test_upsert_and_get_risk_settings() -> None:
    repository = FakeFoundationControlRepository()
    client = make_client(repository)
    relationship_id = uuid4()

    upsert_response = client.put(
        f"/admin/copy-relationships/{relationship_id}/risk-settings",
        headers=auth_headers(),
        json={"enabled": True, "max_order_quantity": "0.5", "max_slippage_bps": 50},
    )
    get_response = client.get(
        f"/admin/copy-relationships/{relationship_id}/risk-settings",
        headers=auth_headers(),
    )

    assert upsert_response.status_code == 200
    assert upsert_response.json()["max_order_quantity"] == "0.5"
    assert get_response.status_code == 200
    assert get_response.json()["copy_relationship_id"] == str(relationship_id)


def test_upsert_risk_settings_returns_404_for_missing_relationship() -> None:
    repository = FakeFoundationControlRepository()
    repository.error = FoundationControlReferenceNotFoundError("copy relationship not found")
    client = make_client(repository)

    response = client.put(
        f"/admin/copy-relationships/{uuid4()}/risk-settings",
        headers=auth_headers(),
        json={"enabled": True, "max_slippage_bps": 50},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "copy relationship not found"}


def test_list_dead_letter_events_returns_operational_view() -> None:
    repository = FakeFoundationControlRepository()
    client = make_client(repository)

    response = client.get(
        "/admin/operations/dead-letter-events?status=open",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["failed_subject"] == "exchange.trade_event.normalized"
    assert body["items"][0]["payload"]["api_secret"] == "[redacted]"
    assert body["items"][0]["payload"]["raw_response"] == "[redacted]"


async def test_postgres_repository_maps_missing_subscription_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = RaisingConnection(asyncpg.ForeignKeyViolationError("fk"))

    async def fake_connect(_database_url: str) -> RaisingConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.foundation_controls.connect", fake_connect)
    repository = PostgresFoundationControlRepository(make_settings())

    with pytest.raises(FoundationControlReferenceNotFoundError, match="user not found"):
        await repository.upsert_subscription(
            uuid4(),
            SubscriptionUpsert(status=SubscriptionStatus.ACTIVE),
            principal=make_principal(),
        )

    assert connection.closed is True


async def test_postgres_repository_maps_duplicate_exchange_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = RaisingConnection(asyncpg.UniqueViolationError("unique"))

    async def fake_connect(_database_url: str) -> RaisingConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.foundation_controls.connect", fake_connect)
    repository = PostgresFoundationControlRepository(make_settings())

    with pytest.raises(FoundationControlConflictError, match="exchange account already exists"):
        await repository.create_exchange_account(
            ExchangeAccountCreate(
                user_id=uuid4(),
                exchange=Exchange.HYPERLIQUID,
                account_id="trader-1",
            ),
            principal=make_principal(),
        )

    assert connection.closed is True


async def test_postgres_repository_maps_missing_risk_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = RaisingConnection(asyncpg.ForeignKeyViolationError("fk"))

    async def fake_connect(_database_url: str) -> RaisingConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.foundation_controls.connect", fake_connect)
    repository = PostgresFoundationControlRepository(make_settings())

    with pytest.raises(
        FoundationControlReferenceNotFoundError,
        match="copy relationship not found",
    ):
        await repository.upsert_risk_settings(
            uuid4(),
            RiskSettingsUpsert(enabled=True),
            principal=make_principal(),
        )

    assert connection.closed is True
