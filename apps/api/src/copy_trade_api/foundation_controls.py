from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Protocol
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from copy_trade_api.audit import insert_audit_log
from copy_trade_api.auth import AdminDependency
from copy_trade_api.config import Settings
from copy_trade_api.database import connect
from copy_trade_api.identity import AuthenticatedPrincipal
from copy_trade_domain.events import Exchange
from copy_trade_shared_events import sanitize_dead_letter_payload


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    DISABLED = "disabled"


class ExchangeAccountStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"
    ERROR = "error"


class DeadLetterStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    REPROCESSED = "reprocessed"
    IGNORED = "ignored"


AUDIT_ENTITY_SUBSCRIPTION = "user_subscription"
AUDIT_ENTITY_EXCHANGE_ACCOUNT = "exchange_account"
AUDIT_ENTITY_RISK_SETTINGS = "copy_relationship_risk_settings"
AUDIT_ACTION_SUBSCRIPTION_UPSERTED = "user_subscription.upserted"
AUDIT_ACTION_EXCHANGE_ACCOUNT_CREATED = "exchange_account.created"
AUDIT_ACTION_EXCHANGE_ACCOUNT_UPDATED = "exchange_account.updated"
AUDIT_ACTION_RISK_SETTINGS_UPSERTED = "copy_relationship_risk_settings.upserted"


class FoundationControlError(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class FoundationControlReferenceNotFoundError(FoundationControlError):
    status_code = status.HTTP_404_NOT_FOUND


class FoundationControlConflictError(FoundationControlError):
    status_code = status.HTTP_409_CONFLICT

UPSERT_SUBSCRIPTION_SQL = """
INSERT INTO user_subscriptions (
    user_id,
    status,
    copy_trading_enabled,
    current_period_end
) VALUES ($1, $2, $3, $4)
ON CONFLICT (user_id) DO UPDATE
SET
    status = EXCLUDED.status,
    copy_trading_enabled = EXCLUDED.copy_trading_enabled,
    current_period_end = EXCLUDED.current_period_end,
    updated_at = now()
RETURNING *
"""

SELECT_SUBSCRIPTIONS_SQL = """
SELECT *
FROM user_subscriptions
"""

INSERT_EXCHANGE_ACCOUNT_SQL = """
INSERT INTO exchange_accounts (
    user_id,
    exchange,
    account_id,
    label,
    status,
    secret_reference,
    secret_fingerprint
) VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING *
"""

SELECT_EXCHANGE_ACCOUNTS_SQL = """
SELECT *
FROM exchange_accounts
"""

SELECT_EXCHANGE_ACCOUNT_BY_ID_FOR_UPDATE_SQL = """
SELECT *
FROM exchange_accounts
WHERE id = $1
FOR UPDATE
"""

UPSERT_RISK_SETTINGS_SQL = """
INSERT INTO copy_relationship_risk_settings (
    copy_relationship_id,
    enabled,
    max_order_quantity,
    max_slippage_bps,
    max_leverage
) VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (copy_relationship_id) DO UPDATE
SET
    enabled = EXCLUDED.enabled,
    max_order_quantity = EXCLUDED.max_order_quantity,
    max_slippage_bps = EXCLUDED.max_slippage_bps,
    max_leverage = EXCLUDED.max_leverage,
    updated_at = now()
RETURNING *
"""

SELECT_RISK_SETTINGS_BY_RELATIONSHIP_SQL = """
SELECT *
FROM copy_relationship_risk_settings
WHERE copy_relationship_id = $1
"""

SELECT_DEAD_LETTER_EVENTS_SQL = """
SELECT *
FROM dead_letter_events
"""


@dataclass(frozen=True)
class SubscriptionRecord:
    user_id: UUID
    status: SubscriptionStatus
    copy_trading_enabled: bool
    current_period_end: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ExchangeAccountRecord:
    id: UUID
    user_id: UUID
    exchange: Exchange
    account_id: str
    label: str | None
    status: ExchangeAccountStatus
    secret_reference: str | None
    secret_fingerprint: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RiskSettingsRecord:
    copy_relationship_id: UUID
    enabled: bool
    max_order_quantity: Decimal | None
    max_slippage_bps: int
    max_leverage: Decimal | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DeadLetterEventRecord:
    id: UUID
    idempotency_key: str
    failed_subject: str
    delivery_attempt: int
    max_delivery_attempts: int
    error_type: str
    payload: dict[str, Any] | None
    status: DeadLetterStatus
    created_at: datetime
    updated_at: datetime


class SubscriptionUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SubscriptionStatus
    copy_trading_enabled: bool = False
    current_period_end: datetime | None = None

    @field_validator("current_period_end")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("current_period_end must be timezone-aware")
        return value


class SubscriptionResponse(BaseModel):
    user_id: UUID
    status: SubscriptionStatus
    copy_trading_enabled: bool
    current_period_end: datetime | None
    created_at: datetime
    updated_at: datetime


class SubscriptionListResponse(BaseModel):
    items: list[SubscriptionResponse]
    limit: int
    offset: int


class ExchangeAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    exchange: Exchange
    account_id: str = Field(min_length=1, max_length=128)
    label: str | None = Field(default=None, min_length=1, max_length=128)
    status: ExchangeAccountStatus = ExchangeAccountStatus.PENDING
    secret_reference: str | None = Field(default=None, min_length=1, max_length=256)
    secret_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("secret_fingerprint")
    @classmethod
    def normalize_fingerprint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if not all(character in "0123456789abcdef" for character in normalized):
            raise ValueError("secret_fingerprint must be 64 lowercase hex characters")
        return normalized


class ExchangeAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    status: ExchangeAccountStatus | None = None
    secret_reference: str | None = Field(default=None, min_length=1, max_length=256)
    secret_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("secret_fingerprint")
    @classmethod
    def normalize_fingerprint(cls, value: str | None) -> str | None:
        return ExchangeAccountCreate.normalize_fingerprint(value)

    @model_validator(mode="after")
    def require_change(self) -> "ExchangeAccountUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class ExchangeAccountResponse(BaseModel):
    id: UUID
    user_id: UUID
    exchange: Exchange
    account_id: str
    label: str | None
    status: ExchangeAccountStatus
    has_secret: bool
    secret_fingerprint_prefix: str | None
    created_at: datetime
    updated_at: datetime


class ExchangeAccountListResponse(BaseModel):
    items: list[ExchangeAccountResponse]
    limit: int
    offset: int


class RiskSettingsUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_order_quantity: Decimal | None = Field(default=None, gt=0)
    max_slippage_bps: int = Field(default=100, ge=0, le=1000)
    max_leverage: Decimal | None = Field(default=None, gt=0)


class RiskSettingsResponse(BaseModel):
    copy_relationship_id: UUID
    enabled: bool
    max_order_quantity: Decimal | None
    max_slippage_bps: int
    max_leverage: Decimal | None
    created_at: datetime
    updated_at: datetime


class DeadLetterEventResponse(BaseModel):
    id: UUID
    idempotency_key: str
    failed_subject: str
    delivery_attempt: int
    max_delivery_attempts: int
    error_type: str
    payload: dict[str, Any] | None
    status: DeadLetterStatus
    created_at: datetime
    updated_at: datetime


class DeadLetterEventListResponse(BaseModel):
    items: list[DeadLetterEventResponse]
    limit: int
    offset: int


SubscriptionStatusFilter = Annotated[SubscriptionStatus | None, Query(alias="status")]
ExchangeAccountStatusFilter = Annotated[ExchangeAccountStatus | None, Query(alias="status")]
DeadLetterStatusFilter = Annotated[DeadLetterStatus | None, Query(alias="status")]
LimitQuery = Annotated[int, Query(ge=1, le=500)]
OffsetQuery = Annotated[int, Query(ge=0)]


class FoundationControlRepository(Protocol):
    async def upsert_subscription(
        self,
        user_id: UUID,
        payload: SubscriptionUpsert,
        *,
        principal: AuthenticatedPrincipal,
    ) -> SubscriptionRecord: ...

    async def list_subscriptions(
        self,
        *,
        status_filter: SubscriptionStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[SubscriptionRecord]: ...

    async def create_exchange_account(
        self,
        payload: ExchangeAccountCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> ExchangeAccountRecord: ...

    async def list_exchange_accounts(
        self,
        *,
        user_id: UUID | None,
        status_filter: ExchangeAccountStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[ExchangeAccountRecord]: ...

    async def update_exchange_account(
        self,
        account_id: UUID,
        payload: ExchangeAccountUpdate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> ExchangeAccountRecord | None: ...

    async def upsert_risk_settings(
        self,
        relationship_id: UUID,
        payload: RiskSettingsUpsert,
        *,
        principal: AuthenticatedPrincipal,
    ) -> RiskSettingsRecord: ...

    async def get_risk_settings(self, relationship_id: UUID) -> RiskSettingsRecord | None: ...

    async def list_dead_letter_events(
        self,
        *,
        status_filter: DeadLetterStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[DeadLetterEventRecord]: ...


class PostgresFoundationControlRepository:
    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url

    async def upsert_subscription(
        self,
        user_id: UUID,
        payload: SubscriptionUpsert,
        *,
        principal: AuthenticatedPrincipal,
    ) -> SubscriptionRecord:
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    UPSERT_SUBSCRIPTION_SQL,
                    user_id,
                    payload.status.value,
                    payload.copy_trading_enabled,
                    payload.current_period_end,
                )
                record = _row_to_subscription(row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_SUBSCRIPTION_UPSERTED,
                    entity_type=AUDIT_ENTITY_SUBSCRIPTION,
                    entity_id=user_id,
                    before_state=None,
                    after_state=subscription_to_response(record).model_dump(mode="json"),
                )
        except asyncpg.ForeignKeyViolationError as exc:
            raise FoundationControlReferenceNotFoundError("user not found") from exc
        finally:
            await connection.close()
        return record

    async def list_subscriptions(
        self,
        *,
        status_filter: SubscriptionStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[SubscriptionRecord]:
        args: list[object] = []
        query = SELECT_SUBSCRIPTIONS_SQL
        if status_filter is not None:
            args.append(status_filter.value)
            query += f" WHERE status = ${len(args)}"
        args.extend((limit, offset))
        query += f" ORDER BY updated_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}"

        connection = await connect(self._database_url)
        try:
            rows = await connection.fetch(query, *args)
        finally:
            await connection.close()
        return tuple(_row_to_subscription(row) for row in rows)

    async def create_exchange_account(
        self,
        payload: ExchangeAccountCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> ExchangeAccountRecord:
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    INSERT_EXCHANGE_ACCOUNT_SQL,
                    payload.user_id,
                    payload.exchange.value,
                    payload.account_id,
                    payload.label,
                    payload.status.value,
                    payload.secret_reference,
                    payload.secret_fingerprint,
                )
                record = _row_to_exchange_account(row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_EXCHANGE_ACCOUNT_CREATED,
                    entity_type=AUDIT_ENTITY_EXCHANGE_ACCOUNT,
                    entity_id=record.id,
                    before_state=None,
                    after_state=exchange_account_to_response(record).model_dump(mode="json"),
                )
        except asyncpg.ForeignKeyViolationError as exc:
            raise FoundationControlReferenceNotFoundError("user not found") from exc
        except asyncpg.UniqueViolationError as exc:
            raise FoundationControlConflictError("exchange account already exists") from exc
        finally:
            await connection.close()
        return record

    async def list_exchange_accounts(
        self,
        *,
        user_id: UUID | None,
        status_filter: ExchangeAccountStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[ExchangeAccountRecord]:
        args: list[object] = []
        where: list[str] = []
        if user_id is not None:
            args.append(user_id)
            where.append(f"user_id = ${len(args)}")
        if status_filter is not None:
            args.append(status_filter.value)
            where.append(f"status = ${len(args)}")
        args.extend((limit, offset))
        query = SELECT_EXCHANGE_ACCOUNTS_SQL
        if where:
            query += " WHERE " + " AND ".join(where)
        query += f" ORDER BY created_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}"

        connection = await connect(self._database_url)
        try:
            rows = await connection.fetch(query, *args)
        finally:
            await connection.close()
        return tuple(_row_to_exchange_account(row) for row in rows)

    async def update_exchange_account(
        self,
        account_id: UUID,
        payload: ExchangeAccountUpdate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> ExchangeAccountRecord | None:
        assignments: list[str] = []
        args: list[object] = []
        for field_name in ("label", "status", "secret_reference", "secret_fingerprint"):
            if field_name not in payload.model_fields_set:
                continue
            value = getattr(payload, field_name)
            args.append(value.value if isinstance(value, StrEnum) else value)
            assignments.append(f"{field_name} = ${len(args)}")
        if not assignments:
            return None

        args.append(account_id)
        query = (
            "UPDATE exchange_accounts SET "
            + ", ".join(assignments)
            + f", updated_at = now() WHERE id = ${len(args)} RETURNING *"
        )
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                before_row = await connection.fetchrow(
                    SELECT_EXCHANGE_ACCOUNT_BY_ID_FOR_UPDATE_SQL,
                    account_id,
                )
                if before_row is None:
                    return None
                before = _row_to_exchange_account(before_row)
                after_row = await connection.fetchrow(query, *args)
                if after_row is None:
                    return None
                after = _row_to_exchange_account(after_row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_EXCHANGE_ACCOUNT_UPDATED,
                    entity_type=AUDIT_ENTITY_EXCHANGE_ACCOUNT,
                    entity_id=after.id,
                    before_state=exchange_account_to_response(before).model_dump(mode="json"),
                    after_state=exchange_account_to_response(after).model_dump(mode="json"),
                )
        finally:
            await connection.close()
        return after

    async def upsert_risk_settings(
        self,
        relationship_id: UUID,
        payload: RiskSettingsUpsert,
        *,
        principal: AuthenticatedPrincipal,
    ) -> RiskSettingsRecord:
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    UPSERT_RISK_SETTINGS_SQL,
                    relationship_id,
                    payload.enabled,
                    payload.max_order_quantity,
                    payload.max_slippage_bps,
                    payload.max_leverage,
                )
                record = _row_to_risk_settings(row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_RISK_SETTINGS_UPSERTED,
                    entity_type=AUDIT_ENTITY_RISK_SETTINGS,
                    entity_id=relationship_id,
                    before_state=None,
                    after_state=risk_settings_to_response(record).model_dump(mode="json"),
                )
        except asyncpg.ForeignKeyViolationError as exc:
            raise FoundationControlReferenceNotFoundError("copy relationship not found") from exc
        finally:
            await connection.close()
        return record

    async def get_risk_settings(self, relationship_id: UUID) -> RiskSettingsRecord | None:
        connection = await connect(self._database_url)
        try:
            row = await connection.fetchrow(
                SELECT_RISK_SETTINGS_BY_RELATIONSHIP_SQL,
                relationship_id,
            )
        finally:
            await connection.close()
        if row is None:
            return None
        return _row_to_risk_settings(row)

    async def list_dead_letter_events(
        self,
        *,
        status_filter: DeadLetterStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[DeadLetterEventRecord]:
        args: list[object] = []
        query = SELECT_DEAD_LETTER_EVENTS_SQL
        if status_filter is not None:
            args.append(status_filter.value)
            query += f" WHERE status = ${len(args)}"
        args.extend((limit, offset))
        query += f" ORDER BY created_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}"

        connection = await connect(self._database_url)
        try:
            rows = await connection.fetch(query, *args)
        finally:
            await connection.close()
        return tuple(_row_to_dead_letter_event(row) for row in rows)


def get_foundation_control_repository(request: Request) -> FoundationControlRepository:
    repository = getattr(request.app.state, "foundation_control_repository", None)
    if repository is None:
        raise RuntimeError("foundation control repository is not configured")
    return repository


FoundationControlRepositoryDependency = Annotated[
    FoundationControlRepository,
    Depends(get_foundation_control_repository),
]


def create_foundation_control_router(admin_dependency: AdminDependency) -> APIRouter:
    router = APIRouter(tags=["foundation-controls"])

    @router.put(
        "/admin/identity/users/{user_id}/subscription",
        response_model=SubscriptionResponse,
    )
    async def upsert_subscription(
        user_id: UUID,
        payload: SubscriptionUpsert,
        repository: FoundationControlRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> SubscriptionResponse:
        try:
            record = await repository.upsert_subscription(user_id, payload, principal=principal)
        except FoundationControlError as exc:
            raise _foundation_http_error(exc) from exc
        return subscription_to_response(record)

    @router.get(
        "/admin/identity/subscriptions",
        response_model=SubscriptionListResponse,
    )
    async def list_subscriptions(
        repository: FoundationControlRepositoryDependency,
        _principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
        status_filter: SubscriptionStatusFilter = None,
        limit: LimitQuery = 100,
        offset: OffsetQuery = 0,
    ) -> SubscriptionListResponse:
        items = await repository.list_subscriptions(
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )
        return SubscriptionListResponse(
            items=[subscription_to_response(item) for item in items],
            limit=limit,
            offset=offset,
        )

    @router.post(
        "/admin/exchange-accounts",
        response_model=ExchangeAccountResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_exchange_account(
        payload: ExchangeAccountCreate,
        repository: FoundationControlRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> ExchangeAccountResponse:
        try:
            record = await repository.create_exchange_account(payload, principal=principal)
        except FoundationControlError as exc:
            raise _foundation_http_error(exc) from exc
        return exchange_account_to_response(record)

    @router.get("/admin/exchange-accounts", response_model=ExchangeAccountListResponse)
    async def list_exchange_accounts(
        repository: FoundationControlRepositoryDependency,
        _principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
        user_id: UUID | None = None,
        status_filter: ExchangeAccountStatusFilter = None,
        limit: LimitQuery = 100,
        offset: OffsetQuery = 0,
    ) -> ExchangeAccountListResponse:
        items = await repository.list_exchange_accounts(
            user_id=user_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )
        return ExchangeAccountListResponse(
            items=[exchange_account_to_response(item) for item in items],
            limit=limit,
            offset=offset,
        )

    @router.patch(
        "/admin/exchange-accounts/{account_id}",
        response_model=ExchangeAccountResponse,
    )
    async def update_exchange_account(
        account_id: UUID,
        payload: ExchangeAccountUpdate,
        repository: FoundationControlRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> ExchangeAccountResponse:
        try:
            record = await repository.update_exchange_account(
                account_id,
                payload,
                principal=principal,
            )
        except FoundationControlError as exc:
            raise _foundation_http_error(exc) from exc
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="exchange account not found",
            )
        return exchange_account_to_response(record)

    @router.put(
        "/admin/copy-relationships/{relationship_id}/risk-settings",
        response_model=RiskSettingsResponse,
    )
    async def upsert_risk_settings(
        relationship_id: UUID,
        payload: RiskSettingsUpsert,
        repository: FoundationControlRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> RiskSettingsResponse:
        try:
            record = await repository.upsert_risk_settings(
                relationship_id,
                payload,
                principal=principal,
            )
        except FoundationControlError as exc:
            raise _foundation_http_error(exc) from exc
        return risk_settings_to_response(record)

    @router.get(
        "/admin/copy-relationships/{relationship_id}/risk-settings",
        response_model=RiskSettingsResponse,
    )
    async def get_risk_settings(
        relationship_id: UUID,
        repository: FoundationControlRepositoryDependency,
        _principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> RiskSettingsResponse:
        record = await repository.get_risk_settings(relationship_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="risk settings not found",
            )
        return risk_settings_to_response(record)

    @router.get("/admin/operations/dead-letter-events", response_model=DeadLetterEventListResponse)
    async def list_dead_letter_events(
        repository: FoundationControlRepositoryDependency,
        _principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
        status_filter: DeadLetterStatusFilter = None,
        limit: LimitQuery = 100,
        offset: OffsetQuery = 0,
    ) -> DeadLetterEventListResponse:
        items = await repository.list_dead_letter_events(
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )
        return DeadLetterEventListResponse(
            items=[dead_letter_event_to_response(item) for item in items],
            limit=limit,
            offset=offset,
        )

    return router


def subscription_to_response(record: SubscriptionRecord) -> SubscriptionResponse:
    return SubscriptionResponse.model_validate(record, from_attributes=True)


def exchange_account_to_response(record: ExchangeAccountRecord) -> ExchangeAccountResponse:
    return ExchangeAccountResponse(
        id=record.id,
        user_id=record.user_id,
        exchange=record.exchange,
        account_id=record.account_id,
        label=record.label,
        status=record.status,
        has_secret=record.secret_reference is not None or record.secret_fingerprint is not None,
        secret_fingerprint_prefix=(
            record.secret_fingerprint[:8] if record.secret_fingerprint is not None else None
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def risk_settings_to_response(record: RiskSettingsRecord) -> RiskSettingsResponse:
    return RiskSettingsResponse.model_validate(record, from_attributes=True)


def dead_letter_event_to_response(record: DeadLetterEventRecord) -> DeadLetterEventResponse:
    return DeadLetterEventResponse(
        id=record.id,
        idempotency_key=record.idempotency_key,
        failed_subject=record.failed_subject,
        delivery_attempt=record.delivery_attempt,
        max_delivery_attempts=record.max_delivery_attempts,
        error_type=record.error_type,
        payload=sanitize_dead_letter_payload(record.payload),
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _foundation_http_error(error: FoundationControlError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _row_to_subscription(row: Any) -> SubscriptionRecord:
    return SubscriptionRecord(
        user_id=UUID(str(row["user_id"])),
        status=SubscriptionStatus(str(row["status"])),
        copy_trading_enabled=bool(row["copy_trading_enabled"]),
        current_period_end=row["current_period_end"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_exchange_account(row: Any) -> ExchangeAccountRecord:
    return ExchangeAccountRecord(
        id=UUID(str(row["id"])),
        user_id=UUID(str(row["user_id"])),
        exchange=Exchange(str(row["exchange"])),
        account_id=str(row["account_id"]),
        label=row["label"],
        status=ExchangeAccountStatus(str(row["status"])),
        secret_reference=row["secret_reference"],
        secret_fingerprint=row["secret_fingerprint"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_risk_settings(row: Any) -> RiskSettingsRecord:
    return RiskSettingsRecord(
        copy_relationship_id=UUID(str(row["copy_relationship_id"])),
        enabled=bool(row["enabled"]),
        max_order_quantity=row["max_order_quantity"],
        max_slippage_bps=int(row["max_slippage_bps"]),
        max_leverage=row["max_leverage"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_dead_letter_event(row: Any) -> DeadLetterEventRecord:
    return DeadLetterEventRecord(
        id=UUID(str(row["id"])),
        idempotency_key=str(row["idempotency_key"]),
        failed_subject=str(row["failed_subject"]),
        delivery_attempt=int(row["delivery_attempt"]),
        max_delivery_attempts=int(row["max_delivery_attempts"]),
        error_type=str(row["error_type"]),
        payload=row["payload"],
        status=DeadLetterStatus(str(row["status"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
