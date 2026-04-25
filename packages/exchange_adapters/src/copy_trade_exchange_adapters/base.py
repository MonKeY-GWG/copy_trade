from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from copy_trade_domain.events import (
    Exchange,
    NormalizedOrderEvent,
    OrderSide,
    OrderType,
    PositionSide,
)


class AdapterErrorCode(StrEnum):
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    EXCHANGE_UNAVAILABLE = "EXCHANGE_UNAVAILABLE"
    UNKNOWN_EXECUTION_STATUS = "UNKNOWN_EXECUTION_STATUS"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class AdapterError(Exception):
    def __init__(self, code: AdapterErrorCode, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class Market(BaseModel):
    exchange: Exchange
    symbol: str
    base_asset: str
    quote_asset: str
    market_type: str = "PERP"
    min_quantity: Decimal | None = None
    min_notional: Decimal | None = None
    price_step: Decimal | None = None
    quantity_step: Decimal | None = None


class AccountState(BaseModel):
    exchange: Exchange
    account_id: str
    equity: Decimal
    available_margin: Decimal
    raw: dict[str, Any] = Field(default_factory=dict)


class Position(BaseModel):
    exchange: Exchange
    account_id: str
    symbol: str
    position_side: PositionSide
    quantity: Decimal
    entry_price: Decimal | None = None
    leverage: Decimal | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class OrderRequest(BaseModel):
    exchange: Exchange
    account_id: str
    symbol: str
    side: OrderSide
    position_side: PositionSide
    order_type: OrderType
    quantity: Decimal = Field(gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    trigger_price: Decimal | None = Field(default=None, gt=0)
    reduce_only: bool = False
    post_only: bool = False
    client_order_id: str


class OrderResult(BaseModel):
    exchange: Exchange
    account_id: str
    exchange_order_id: str | None = None
    accepted: bool
    status: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ExchangeAdapter(ABC):
    exchange: Exchange

    @abstractmethod
    async def get_markets(self) -> list[Market]:
        raise NotImplementedError

    @abstractmethod
    async def get_account_state(self, account_id: str) -> AccountState:
        raise NotImplementedError

    @abstractmethod
    async def get_positions(self, account_id: str) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    async def subscribe_user_orders(self, account_id: str) -> AsyncIterator[NormalizedOrderEvent]:
        raise NotImplementedError

    @abstractmethod
    async def subscribe_user_fills(self, account_id: str) -> AsyncIterator[NormalizedOrderEvent]:
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    async def place_tpsl_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(
        self,
        account_id: str,
        symbol: str,
        exchange_order_id: str,
    ) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    async def set_leverage(self, account_id: str, symbol: str, leverage: Decimal) -> None:
        raise NotImplementedError

    @abstractmethod
    def normalize_symbol(self, exchange_symbol: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def normalize_order_update(self, raw: dict[str, Any]) -> NormalizedOrderEvent:
        raise NotImplementedError

    @abstractmethod
    def normalize_fill(self, raw: dict[str, Any]) -> NormalizedOrderEvent:
        raise NotImplementedError
