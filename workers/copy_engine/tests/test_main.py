import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from copy_trade_copy_engine.config import Settings
from copy_trade_copy_engine.idempotency import InMemoryIdempotencyStore
from copy_trade_copy_engine.main import (
    build_copy_execution_result_handler,
    build_normalized_trade_handler,
    run,
)
from copy_trade_copy_engine.processor import CopyEventProcessor
from copy_trade_copy_engine.relationships import CopyRelationship
from copy_trade_domain.events import (
    CopyExecutionRequest,
    CopyExecutionResult,
    CopyExecutionStatus,
    Exchange,
    NormalizedOrderEvent,
    OrderSide,
    OrderType,
    PositionSide,
)
from copy_trade_shared_events import (
    COPY_ENGINE_EXECUTION_RESULT_DURABLES,
    COPY_ENGINE_NORMALIZED_TRADES_DURABLE,
    COPY_EXECUTION_FILLED,
    COPY_EXECUTION_REQUESTED,
    COPY_EXECUTION_RESULT_SUBJECTS,
    EXCHANGE_TRADE_EVENT_NORMALIZED,
    EventBusMessage,
)


class FakeEventBus:
    def __init__(self, *, fail_publish: bool = False) -> None:
        self.subscriptions: list[dict[str, Any]] = []
        self.published: list[dict[str, Any]] = []
        self.closed = False
        self.fail_publish = fail_publish

    async def publish_json(self, subject: str, payload: object) -> None:
        if self.fail_publish:
            raise RuntimeError("publish failed")
        self.published.append(
            {
                "subject": subject,
                "payload": payload,
            },
        )

    async def subscribe_json(self, subject: str, *, durable: str, handler: object) -> None:
        self.subscriptions.append(
            {
                "subject": subject,
                "durable": durable,
                "handler": handler,
            },
        )

    async def close(self) -> None:
        self.closed = True


class RecordingRequestRecorder:
    def __init__(self) -> None:
        self.requests: list[CopyExecutionRequest] = []
        self.published_requests: list[CopyExecutionRequest] = []

    async def record(self, request: CopyExecutionRequest) -> None:
        self.requests.append(request)

    async def mark_published(self, request: CopyExecutionRequest) -> None:
        self.published_requests.append(request)


class RecordingResultRecorder:
    def __init__(self) -> None:
        self.results: list[CopyExecutionResult] = []

    async def record(self, result: CopyExecutionResult) -> None:
        self.results.append(result)


class StaticRelationshipProvider:
    def __init__(self, relationships: Sequence[CopyRelationship]) -> None:
        self._relationships = relationships

    async def list_active_for_event(
        self,
        event: NormalizedOrderEvent,
    ) -> Sequence[CopyRelationship]:
        return self._relationships


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


async def test_run_subscribes_to_normalized_trade_events() -> None:
    event_bus = FakeEventBus()
    stop_event = asyncio.Event()
    stop_event.set()
    processor = CopyEventProcessor(
        relationship_provider=StaticRelationshipProvider(()),
        idempotency_store=InMemoryIdempotencyStore(),
    )

    await run(
        settings=Settings(
            nats_url="nats://test:4222",
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        ),
        event_bus=event_bus,
        processor=processor,
        stop_event=stop_event,
    )

    assert len(event_bus.subscriptions) == 1 + len(COPY_EXECUTION_RESULT_SUBJECTS)
    subscriptions = {item["subject"]: item for item in event_bus.subscriptions}
    assert subscriptions[EXCHANGE_TRADE_EVENT_NORMALIZED]["durable"] == (
        COPY_ENGINE_NORMALIZED_TRADES_DURABLE
    )
    for subject in COPY_EXECUTION_RESULT_SUBJECTS:
        assert subscriptions[subject]["durable"] == COPY_ENGINE_EXECUTION_RESULT_DURABLES[subject]
        assert callable(subscriptions[subject]["handler"])
    assert event_bus.closed is False


async def test_normalized_trade_handler_publishes_dry_run_request() -> None:
    event = make_event()
    relationship = CopyRelationship(
        copy_relationship_id=uuid4(),
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
        effective_from=event.occurred_at,
    )
    processor = CopyEventProcessor(
        relationship_provider=StaticRelationshipProvider((relationship,)),
        idempotency_store=InMemoryIdempotencyStore(),
    )
    event_bus = FakeEventBus()
    recorder = RecordingRequestRecorder()
    handler = build_normalized_trade_handler(processor, event_bus, recorder)

    await handler(
        EventBusMessage(
            subject=EXCHANGE_TRADE_EVENT_NORMALIZED,
            data=event.model_dump(mode="json"),
        ),
    )

    assert len(event_bus.published) == 1
    assert event_bus.published[0]["subject"] == COPY_EXECUTION_REQUESTED
    request = event_bus.published[0]["payload"]
    assert isinstance(request, CopyExecutionRequest)
    assert request.dry_run is True
    assert request.source_event_id == event.event_id
    assert recorder.requests == [request]
    assert recorder.published_requests == [request]


async def test_normalized_trade_handler_releases_idempotency_when_publish_fails() -> None:
    event = make_event()
    relationship = CopyRelationship(
        copy_relationship_id=uuid4(),
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
        effective_from=event.occurred_at,
    )
    processor = CopyEventProcessor(
        relationship_provider=StaticRelationshipProvider((relationship,)),
        idempotency_store=InMemoryIdempotencyStore(),
    )
    failing_handler = build_normalized_trade_handler(
        processor,
        FakeEventBus(fail_publish=True),
        RecordingRequestRecorder(),
    )

    with pytest.raises(RuntimeError, match="publish failed"):
        await failing_handler(
            EventBusMessage(
                subject=EXCHANGE_TRADE_EVENT_NORMALIZED,
                data=event.model_dump(mode="json"),
            ),
        )

    event_bus = FakeEventBus()
    succeeding_handler = build_normalized_trade_handler(
        processor,
        event_bus,
        RecordingRequestRecorder(),
    )

    await succeeding_handler(
        EventBusMessage(
            subject=EXCHANGE_TRADE_EVENT_NORMALIZED,
            data=event.model_dump(mode="json"),
        ),
    )

    assert len(event_bus.published) == 1


async def test_execution_result_handler_records_result() -> None:
    result = CopyExecutionResult(
        occurred_at=datetime.now(UTC),
        source_exchange=Exchange.BLOFIN,
        source_account_id="follower-1",
        idempotency_key="result-fill-1",
        request_id=uuid4(),
        status=CopyExecutionStatus.FILLED,
        exchange_order_id="exchange-order-1",
    )
    recorder = RecordingResultRecorder()
    handler = build_copy_execution_result_handler(recorder)

    await handler(
        EventBusMessage(
            subject=COPY_EXECUTION_FILLED,
            data=result.model_dump(mode="json"),
        ),
    )

    assert recorder.results == [result]
