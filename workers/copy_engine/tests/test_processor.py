from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from copy_trade_copy_engine.idempotency import InMemoryIdempotencyStore
from copy_trade_copy_engine.processor import CopyEventProcessor
from copy_trade_copy_engine.relationships import CopyRelationship
from copy_trade_domain.events import (
    Exchange,
    NormalizedOrderEvent,
    OrderSide,
    OrderType,
    PositionSide,
)


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


def make_relationship(event: NormalizedOrderEvent) -> CopyRelationship:
    return CopyRelationship(
        copy_relationship_id=uuid4(),
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
        effective_from=event.occurred_at - timedelta(seconds=1),
    )


async def test_processor_builds_dry_run_request_for_active_relationship() -> None:
    event = make_event()
    relationship = make_relationship(event)
    processor = CopyEventProcessor(
        relationship_provider=StaticRelationshipProvider((relationship,)),
        idempotency_store=InMemoryIdempotencyStore(),
    )

    result = await processor.process_normalized_order_event(event)

    assert result.skipped_duplicates == 0
    assert result.skipped_before_follow_start == 0
    assert len(result.requests) == 1
    request = result.requests[0]
    assert request.dry_run is True
    assert request.source_event_id == event.event_id
    assert request.copy_relationship_id == relationship.copy_relationship_id
    assert request.target_exchange == Exchange.BLOFIN
    assert request.target_symbol == "BTC-USDT"


async def test_processor_skips_event_before_follow_start() -> None:
    event = make_event()
    relationship = CopyRelationship(
        copy_relationship_id=uuid4(),
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
        effective_from=event.occurred_at + timedelta(seconds=1),
    )
    processor = CopyEventProcessor(
        relationship_provider=StaticRelationshipProvider((relationship,)),
        idempotency_store=InMemoryIdempotencyStore(),
    )

    result = await processor.process_normalized_order_event(event)

    assert result.requests == ()
    assert result.skipped_before_follow_start == 1


async def test_processor_skips_duplicate_copy_execution_request() -> None:
    event = make_event()
    relationship = make_relationship(event)
    processor = CopyEventProcessor(
        relationship_provider=StaticRelationshipProvider((relationship,)),
        idempotency_store=InMemoryIdempotencyStore(),
    )

    first = await processor.process_normalized_order_event(event)
    second = await processor.process_normalized_order_event(event)

    assert len(first.requests) == 1
    assert second.requests == ()
    assert second.skipped_duplicates == 1


async def test_processor_skips_inactive_relationship() -> None:
    event = make_event()
    relationship = CopyRelationship(
        copy_relationship_id=uuid4(),
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
        effective_from=event.occurred_at - timedelta(seconds=1),
        active=False,
    )
    processor = CopyEventProcessor(
        relationship_provider=StaticRelationshipProvider((relationship,)),
        idempotency_store=InMemoryIdempotencyStore(),
    )

    result = await processor.process_normalized_order_event(event)

    assert result.requests == ()
    assert result.skipped_inactive == 1
