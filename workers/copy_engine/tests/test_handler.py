from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from copy_trade_copy_engine.handler import (
    build_dry_run_execution_request,
    event_is_after_follow_start,
)
from copy_trade_domain.events import (
    Exchange,
    NormalizedOrderEvent,
    OrderSide,
    OrderType,
    PositionSide,
)


def make_event() -> NormalizedOrderEvent:
    return NormalizedOrderEvent(
        occurred_at=datetime.now(UTC),
        source_exchange=Exchange.HYPERLIQUID,
        source_account_id="trader-1",
        idempotency_key="fill-one",
        symbol="BTC-USD",
        base_asset="BTC",
        quote_asset="USD",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )


def test_event_is_only_copied_after_follow_start() -> None:
    event = make_event()

    assert event_is_after_follow_start(event, event.occurred_at - timedelta(seconds=1)) is True
    assert event_is_after_follow_start(event, event.occurred_at + timedelta(seconds=1)) is False


def test_build_dry_run_execution_request_keeps_traceability() -> None:
    event = make_event()
    relationship_id = uuid4()

    request = build_dry_run_execution_request(
        event=event,
        copy_relationship_id=relationship_id,
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
    )

    assert request.dry_run is True
    assert request.source_event_id == event.event_id
    assert request.copy_relationship_id == relationship_id
    assert request.idempotency_key.endswith(event.idempotency_key)
