import inspect
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from copy_trade_domain.events import (
    Exchange,
    NormalizedOrderEvent,
    OrderSide,
    OrderType,
    PositionSide,
)
from copy_trade_shared_events import (
    EXCHANGE_TRADE_EVENT_NORMALIZED,
    NATS_MSG_ID_HEADER,
    EventRetryPolicy,
    build_publish_headers,
    encode_json_payload,
)
from copy_trade_shared_events.bus import (
    EventBusMessage,
    build_consumer_config,
    build_message_callback,
    handle_message,
)
from copy_trade_shared_events.subjects import ALL_EVENT_SUBJECTS, DEAD_LETTER_EVENT_CREATED


class FakeMessage:
    def __init__(self, data: bytes, *, num_delivered: int = 1, stream_sequence: int = 1) -> None:
        self.subject = EXCHANGE_TRADE_EVENT_NORMALIZED
        self.data = data
        self.acked = False
        self.nacked = False
        self.metadata = FakeMetadata(num_delivered, stream_sequence)

    async def ack(self) -> None:
        self.acked = True

    async def nak(self) -> None:
        self.nacked = True


class FakeSequence:
    def __init__(self, stream: int) -> None:
        self.stream = stream


class FakeMetadata:
    def __init__(self, num_delivered: int, stream_sequence: int) -> None:
        self.num_delivered = num_delivered
        self.sequence = FakeSequence(stream_sequence)


def make_event() -> NormalizedOrderEvent:
    return NormalizedOrderEvent(
        occurred_at=datetime.now(UTC),
        source_exchange=Exchange.HYPERLIQUID,
        source_account_id="trader-1",
        idempotency_key="hyperliquid-fill-1",
        symbol="BTC-USD",
        base_asset="BTC",
        quote_asset="USD",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )


def test_event_subjects_include_normalized_trade_subject() -> None:
    assert EXCHANGE_TRADE_EVENT_NORMALIZED in ALL_EVENT_SUBJECTS
    assert DEAD_LETTER_EVENT_CREATED in ALL_EVENT_SUBJECTS


def test_build_consumer_config_uses_retry_policy() -> None:
    config = build_consumer_config(
        "copy_engine_test",
        EventRetryPolicy(max_deliver=5, ack_wait_seconds=12.5),
        subject=EXCHANGE_TRADE_EVENT_NORMALIZED,
        deliver_subject="_INBOX.test",
    )

    assert config.durable_name == "copy_engine_test"
    assert config.max_deliver == 5
    assert config.ack_wait == 12.5
    assert config.filter_subject == EXCHANGE_TRADE_EVENT_NORMALIZED
    assert config.deliver_subject == "_INBOX.test"


def test_encode_json_payload_serializes_pydantic_event() -> None:
    payload = json.loads(encode_json_payload(make_event()).decode("utf-8"))

    assert payload["schema_version"] == "v1"
    assert payload["source_exchange"] == "hyperliquid"
    assert payload["quantity"] == "0.01"


def test_build_publish_headers_uses_idempotency_key_for_jetstream_dedupe() -> None:
    headers = build_publish_headers(make_event())

    assert headers == {NATS_MSG_ID_HEADER: "hyperliquid-fill-1"}


def test_build_message_callback_returns_async_callback() -> None:
    async def handler(_message: EventBusMessage) -> None:
        return None

    assert inspect.iscoroutinefunction(build_message_callback(handler))


async def test_handle_message_acks_after_successful_handler() -> None:
    received: list[dict[str, Any]] = []

    async def handler(message: EventBusMessage) -> None:
        received.append(message.data)

    message = FakeMessage(b'{"event_id":"event-1"}')

    await handle_message(message, handler)  # type: ignore[arg-type]

    assert received == [{"event_id": "event-1"}]
    assert message.acked is True
    assert message.nacked is False


async def test_handle_message_naks_when_handler_fails() -> None:
    async def handler(_message: EventBusMessage) -> None:
        raise RuntimeError("handler failed")

    message = FakeMessage(b'{"event_id":"event-1"}')

    with pytest.raises(RuntimeError):
        await handle_message(message, handler)  # type: ignore[arg-type]

    assert message.acked is False
    assert message.nacked is True


async def test_handle_message_naks_without_raising_during_configured_retry() -> None:
    async def handler(_message: EventBusMessage) -> None:
        raise RuntimeError("handler failed")

    async def dead_letter_publisher(_subject: str, _payload: dict[str, Any]) -> None:
        return None

    message = FakeMessage(b'{"event_id":"event-1"}', num_delivered=1)

    await handle_message(
        message,  # type: ignore[arg-type]
        handler,
        retry_policy=EventRetryPolicy(max_deliver=3),
        dead_letter_publisher=dead_letter_publisher,
    )

    assert message.acked is False
    assert message.nacked is True


async def test_handle_message_sends_to_dead_letter_after_final_attempt() -> None:
    async def handler(_message: EventBusMessage) -> None:
        raise RuntimeError("secret-ish detail should not be copied")

    published: list[dict[str, Any]] = []

    async def dead_letter_publisher(subject: str, payload: dict[str, Any]) -> None:
        published.append({"subject": subject, "payload": payload})

    message = FakeMessage(
        b'{"event_id":"event-1","idempotency_key":"source-key-1"}',
        num_delivered=3,
        stream_sequence=42,
    )

    await handle_message(
        message,  # type: ignore[arg-type]
        handler,
        retry_policy=EventRetryPolicy(max_deliver=3),
        dead_letter_publisher=dead_letter_publisher,
    )

    assert message.acked is True
    assert message.nacked is False
    assert published == [
        {
            "subject": DEAD_LETTER_EVENT_CREATED,
            "payload": {
                "idempotency_key": "dlq:exchange.trade_event.normalized:source-key-1",
                "failed_subject": EXCHANGE_TRADE_EVENT_NORMALIZED,
                "delivery_attempt": 3,
                "max_delivery_attempts": 3,
                "error_type": "RuntimeError",
                "payload": {
                    "event_id": "event-1",
                    "idempotency_key": "source-key-1",
                },
            },
        },
    ]
