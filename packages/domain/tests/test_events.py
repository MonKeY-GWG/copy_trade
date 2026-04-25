from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from copy_trade_domain.events import (
    Exchange,
    MarketType,
    NormalizedOrderEvent,
    OrderSide,
    OrderType,
    PositionSide,
)


def test_normalized_order_event_defaults_to_perps() -> None:
    event = NormalizedOrderEvent(
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

    assert event.market_type == MarketType.PERP
    assert event.schema_version == "v1"


def test_event_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        NormalizedOrderEvent(
            occurred_at=datetime.now().replace(tzinfo=None),
            source_exchange=Exchange.ASTER,
            source_account_id="trader-1",
            idempotency_key="aster-fill-1",
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            side=OrderSide.SELL,
            position_side=PositionSide.SHORT,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("70000"),
        )
