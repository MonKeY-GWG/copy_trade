"""Shared event bus contracts for Copy Trade services."""

from copy_trade_shared_events.bus import (
    NATS_MSG_ID_HEADER,
    EventBusMessage,
    EventRetryPolicy,
    NatsJetStreamEventBus,
    build_publish_headers,
    encode_json_payload,
)
from copy_trade_shared_events.subjects import (
    ALL_EVENT_SUBJECTS,
    COPY_ENGINE_EXECUTION_RESULT_DURABLES,
    COPY_ENGINE_NORMALIZED_TRADES_DURABLE,
    COPY_EXECUTION_ACCEPTED,
    COPY_EXECUTION_FAILED,
    COPY_EXECUTION_FILLED,
    COPY_EXECUTION_REJECTED,
    COPY_EXECUTION_REQUESTED,
    COPY_EXECUTION_RESULT_SUBJECTS,
    DEAD_LETTER_EVENT_CREATED,
    EVENT_STREAM,
    EXCHANGE_TRADE_EVENT_NORMALIZED,
)

__all__ = [
    "ALL_EVENT_SUBJECTS",
    "COPY_ENGINE_EXECUTION_RESULT_DURABLES",
    "COPY_ENGINE_NORMALIZED_TRADES_DURABLE",
    "COPY_EXECUTION_ACCEPTED",
    "COPY_EXECUTION_FAILED",
    "COPY_EXECUTION_FILLED",
    "COPY_EXECUTION_REQUESTED",
    "COPY_EXECUTION_REJECTED",
    "COPY_EXECUTION_RESULT_SUBJECTS",
    "DEAD_LETTER_EVENT_CREATED",
    "EVENT_STREAM",
    "EXCHANGE_TRADE_EVENT_NORMALIZED",
    "EventBusMessage",
    "EventRetryPolicy",
    "NATS_MSG_ID_HEADER",
    "NatsJetStreamEventBus",
    "build_publish_headers",
    "encode_json_payload",
]
