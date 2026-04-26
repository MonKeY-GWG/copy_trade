import json
import logging
from typing import Protocol

from copy_trade_copy_engine.database import DatabasePool
from copy_trade_domain.events import CopyExecutionResult

logger = logging.getLogger("copy_trade.copy_engine")

INSERT_COPY_EXECUTION_RESULT_SQL = """
INSERT INTO copy_execution_results (
    id,
    schema_version,
    occurred_at,
    observed_at,
    source_exchange,
    source_account_id,
    idempotency_key,
    trace_id,
    request_id,
    status,
    exchange_order_id,
    reject_reason,
    raw_response
) VALUES (
    $1, $2, $3, $4, $5, $6, $7,
    $8, $9, $10, $11, $12, $13::jsonb
)
ON CONFLICT (idempotency_key) DO NOTHING
"""

UPDATE_COPY_EXECUTION_REQUEST_FROM_RESULT_SQL = """
UPDATE copy_execution_requests
SET request_status = $2
WHERE id = $1
"""


class CopyExecutionResultRecorder(Protocol):
    async def record(self, result: CopyExecutionResult) -> None: ...


class NoopCopyExecutionResultRecorder:
    async def record(self, result: CopyExecutionResult) -> None:
        return None


class PostgresCopyExecutionResultRecorder:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def record(self, result: CopyExecutionResult) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                INSERT_COPY_EXECUTION_RESULT_SQL,
                result.event_id,
                result.schema_version,
                result.occurred_at,
                result.observed_at,
                result.source_exchange.value,
                result.source_account_id,
                result.idempotency_key,
                result.trace_id,
                result.request_id,
                result.status.value,
                result.exchange_order_id,
                result.reject_reason,
                json.dumps(result.raw_response, separators=(",", ":")),
            )
            await connection.execute(
                UPDATE_COPY_EXECUTION_REQUEST_FROM_RESULT_SQL,
                result.request_id,
                result.status.value,
            )
        logger.info(
            "copy execution result recorded event_id=%s request_id=%s status=%s trace_id=%s",
            result.event_id,
            result.request_id,
            result.status.value,
            result.trace_id,
        )
