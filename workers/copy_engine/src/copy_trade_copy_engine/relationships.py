from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from copy_trade_copy_engine.database import DatabasePool
from copy_trade_domain.events import Exchange, NormalizedOrderEvent

SELECT_ACTIVE_COPY_RELATIONSHIPS_SQL = """
SELECT
    relationships.id,
    relationships.follower_account_id,
    relationships.target_exchange,
    relationships.target_symbol,
    relationships.max_slippage_bps,
    relationships.effective_from,
    relationships.active,
    source_account.status AS source_account_status,
    follower_account.status AS follower_account_status,
    follower_user.status AS follower_user_status,
    subscription.status AS subscription_status,
    subscription.copy_trading_enabled,
    risk_settings.enabled AS risk_enabled,
    risk_settings.max_order_quantity AS risk_max_order_quantity,
    risk_settings.max_slippage_bps AS risk_max_slippage_bps,
    risk_settings.max_leverage AS risk_max_leverage
FROM copy_relationships AS relationships
LEFT JOIN exchange_accounts AS source_account
    ON source_account.exchange = relationships.source_exchange
    AND source_account.account_id = relationships.source_account_id
LEFT JOIN exchange_accounts AS follower_account
    ON follower_account.exchange = relationships.target_exchange
    AND follower_account.account_id = relationships.follower_account_id
LEFT JOIN users AS follower_user
    ON follower_user.id = follower_account.user_id
LEFT JOIN user_subscriptions AS subscription
    ON subscription.user_id = follower_account.user_id
LEFT JOIN copy_relationship_risk_settings AS risk_settings
    ON risk_settings.copy_relationship_id = relationships.id
WHERE relationships.active IS TRUE
    AND relationships.source_exchange = $1
    AND relationships.source_account_id = $2
    AND (relationships.source_symbol IS NULL OR relationships.source_symbol = $3)
    AND relationships.effective_from <= $4
ORDER BY relationships.effective_from ASC, relationships.created_at ASC
"""


@dataclass(frozen=True)
class CopyRelationship:
    copy_relationship_id: UUID
    follower_account_id: str
    target_exchange: Exchange
    target_symbol: str
    effective_from: datetime
    max_slippage_bps: int = 100
    active: bool = True
    source_account_status: str | None = "active"
    follower_account_status: str | None = "active"
    follower_user_status: str | None = "active"
    subscription_status: str | None = "active"
    copy_trading_enabled: bool = True
    risk_enabled: bool = True
    risk_max_order_quantity: Decimal | None = None
    risk_max_slippage_bps: int | None = 1000
    risk_max_leverage: Decimal | None = None


class CopyRelationshipProvider(Protocol):
    async def list_active_for_event(
        self,
        event: NormalizedOrderEvent,
    ) -> Sequence[CopyRelationship]:
        raise NotImplementedError


class EmptyCopyRelationshipProvider:
    async def list_active_for_event(
        self,
        event: NormalizedOrderEvent,
    ) -> Sequence[CopyRelationship]:
        return ()


class PostgresCopyRelationshipProvider:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def list_active_for_event(
        self,
        event: NormalizedOrderEvent,
    ) -> Sequence[CopyRelationship]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                SELECT_ACTIVE_COPY_RELATIONSHIPS_SQL,
                event.source_exchange.value,
                event.source_account_id,
                event.symbol,
                event.occurred_at,
            )
        return tuple(_row_to_relationship(row) for row in rows)


def _row_to_relationship(row: Any) -> CopyRelationship:
    return CopyRelationship(
        copy_relationship_id=UUID(str(row["id"])),
        follower_account_id=str(row["follower_account_id"]),
        target_exchange=Exchange(str(row["target_exchange"])),
        target_symbol=str(row["target_symbol"]),
        effective_from=row["effective_from"],
        max_slippage_bps=int(_row_get(row, "max_slippage_bps", 100)),
        active=bool(row["active"]),
        source_account_status=_row_get(row, "source_account_status", "active"),
        follower_account_status=_row_get(row, "follower_account_status", "active"),
        follower_user_status=_row_get(row, "follower_user_status", "active"),
        subscription_status=_row_get(row, "subscription_status", "active"),
        copy_trading_enabled=bool(_row_get(row, "copy_trading_enabled", True)),
        risk_enabled=bool(_row_get(row, "risk_enabled", True)),
        risk_max_order_quantity=_row_get(row, "risk_max_order_quantity", None),
        risk_max_slippage_bps=(
            int(_row_get(row, "risk_max_slippage_bps", 1000))
            if _row_get(row, "risk_max_slippage_bps", 1000) is not None
            else None
        ),
        risk_max_leverage=_row_get(row, "risk_max_leverage", None),
    )


def _row_get(row: Any, key: str, default: Any) -> Any:
    try:
        return row[key]
    except KeyError:
        return default
