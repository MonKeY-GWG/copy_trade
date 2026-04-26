from typing import Protocol

from copy_trade_copy_engine.database import DatabasePool
from copy_trade_domain.events import CopyExecutionRequest

INSERT_COPY_EXECUTION_REQUEST_SQL = """
INSERT INTO copy_execution_requests (
    id,
    schema_version,
    occurred_at,
    observed_at,
    source_exchange,
    source_account_id,
    idempotency_key,
    trace_id,
    source_event_id,
    copy_relationship_id,
    follower_account_id,
    target_exchange,
    target_symbol,
    order_type,
    side,
    position_side,
    quantity,
    price,
    trigger_price,
    reduce_only,
    post_only,
    max_slippage_bps,
    dry_run,
    request_status
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8,
    $9, $10, $11, $12, $13, $14, $15, $16,
    $17, $18, $19, $20, $21, $22, $23, $24
)
ON CONFLICT (idempotency_key) DO NOTHING
"""

MARK_COPY_EXECUTION_REQUEST_PUBLISHED_SQL = """
UPDATE copy_execution_requests
SET request_status = 'PUBLISHED'
WHERE id = $1
    AND request_status = 'REQUESTED'
"""


class CopyExecutionRequestRecorder(Protocol):
    async def record(self, request: CopyExecutionRequest) -> None: ...

    async def mark_published(self, request: CopyExecutionRequest) -> None: ...


class NoopCopyExecutionRequestRecorder:
    async def record(self, request: CopyExecutionRequest) -> None:
        return None

    async def mark_published(self, request: CopyExecutionRequest) -> None:
        return None


class PostgresCopyExecutionRequestRecorder:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def record(self, request: CopyExecutionRequest) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                INSERT_COPY_EXECUTION_REQUEST_SQL,
                request.event_id,
                request.schema_version,
                request.occurred_at,
                request.observed_at,
                request.source_exchange.value,
                request.source_account_id,
                request.idempotency_key,
                request.trace_id,
                request.source_event_id,
                request.copy_relationship_id,
                request.follower_account_id,
                request.target_exchange.value,
                request.target_symbol,
                request.order_type.value,
                request.side.value,
                request.position_side.value,
                request.quantity,
                request.price,
                request.trigger_price,
                request.reduce_only,
                request.post_only,
                request.max_slippage_bps,
                request.dry_run,
                "REQUESTED",
            )

    async def mark_published(self, request: CopyExecutionRequest) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                MARK_COPY_EXECUTION_REQUEST_PUBLISHED_SQL,
                request.event_id,
            )
