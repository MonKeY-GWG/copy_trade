import json
from typing import Any, Protocol

from copy_trade_copy_engine.database import DatabasePool
from copy_trade_shared_events import sanitize_dead_letter_payload

INSERT_DEAD_LETTER_EVENT_SQL = """
INSERT INTO dead_letter_events (
    idempotency_key,
    failed_subject,
    delivery_attempt,
    max_delivery_attempts,
    error_type,
    payload,
    status
) VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'open')
ON CONFLICT (idempotency_key) DO NOTHING
"""


class DeadLetterEventRecorder(Protocol):
    async def record(self, payload: dict[str, Any]) -> None: ...


class NoopDeadLetterEventRecorder:
    async def record(self, payload: dict[str, Any]) -> None:
        return None


class PostgresDeadLetterEventRecorder:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def record(self, payload: dict[str, Any]) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                INSERT_DEAD_LETTER_EVENT_SQL,
                str(payload["idempotency_key"]),
                str(payload["failed_subject"]),
                int(payload["delivery_attempt"]),
                int(payload["max_delivery_attempts"]),
                str(payload["error_type"]),
                json.dumps(
                    sanitize_dead_letter_payload(payload.get("payload")),
                    separators=(",", ":"),
                ),
            )
