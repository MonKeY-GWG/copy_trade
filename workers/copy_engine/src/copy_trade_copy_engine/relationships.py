from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from copy_trade_copy_engine.database import DatabasePool
from copy_trade_domain.events import Exchange, NormalizedOrderEvent

SELECT_ACTIVE_COPY_RELATIONSHIPS_SQL = """
SELECT
    id,
    follower_account_id,
    target_exchange,
    target_symbol,
    effective_from,
    active
FROM copy_relationships
WHERE active IS TRUE
    AND source_exchange = $1
    AND source_account_id = $2
    AND (source_symbol IS NULL OR source_symbol = $3)
    AND effective_from <= $4
ORDER BY effective_from ASC, created_at ASC
"""


@dataclass(frozen=True)
class CopyRelationship:
    copy_relationship_id: UUID
    follower_account_id: str
    target_exchange: Exchange
    target_symbol: str
    effective_from: datetime
    active: bool = True


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
        active=bool(row["active"]),
    )
