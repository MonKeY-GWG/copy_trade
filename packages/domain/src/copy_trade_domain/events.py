from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Exchange(StrEnum):
    HYPERLIQUID = "hyperliquid"
    ASTER = "aster"
    BLOFIN = "blofin"


class MarketType(StrEnum):
    PERP = "PERP"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NET = "NET"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"


class CopyExecutionStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    FAILED = "FAILED"


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    schema_version: str = Field(default="v1")
    occurred_at: datetime
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_exchange: Exchange
    source_account_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8)
    trace_id: str = Field(default_factory=lambda: uuid4().hex)

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("event timestamps must be timezone-aware")
        return value


class NormalizedOrderEvent(EventEnvelope):
    symbol: str = Field(min_length=1)
    base_asset: str = Field(min_length=1)
    quote_asset: str = Field(min_length=1)
    market_type: MarketType = Field(default=MarketType.PERP)
    side: OrderSide
    position_side: PositionSide
    order_type: OrderType
    quantity: Decimal = Field(gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    trigger_price: Decimal | None = Field(default=None, gt=0)
    reduce_only: bool = Field(default=False)
    post_only: bool = Field(default=False)
    leverage: Decimal | None = Field(default=None, gt=0)
    client_order_id: str | None = None
    raw_event: dict[str, Any] = Field(default_factory=dict)


class CopyExecutionRequest(EventEnvelope):
    source_event_id: UUID
    copy_relationship_id: UUID
    follower_account_id: str = Field(min_length=1)
    target_exchange: Exchange
    target_symbol: str = Field(min_length=1)
    order_type: OrderType
    side: OrderSide
    position_side: PositionSide
    quantity: Decimal = Field(gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    trigger_price: Decimal | None = Field(default=None, gt=0)
    reduce_only: bool = Field(default=False)
    post_only: bool = Field(default=False)
    max_slippage_bps: int = Field(default=100, ge=0)
    dry_run: bool = Field(default=True)


class CopyExecutionResult(EventEnvelope):
    request_id: UUID
    status: CopyExecutionStatus
    exchange_order_id: str | None = None
    reject_reason: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
