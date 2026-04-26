from decimal import Decimal

import pytest
from pydantic import ValidationError

from copy_trade_domain.events import Exchange, OrderSide, OrderType, PositionSide
from copy_trade_exchange_adapters.base import AdapterError, AdapterErrorCode, OrderRequest


def test_adapter_error_keeps_code_and_details() -> None:
    error = AdapterError(
        AdapterErrorCode.RATE_LIMITED,
        "exchange rate limit exceeded",
        {"retry_after_seconds": 10},
    )

    assert str(error) == "exchange rate limit exceeded"
    assert error.code == AdapterErrorCode.RATE_LIMITED
    assert error.details == {"retry_after_seconds": 10}


def test_order_request_requires_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            exchange=Exchange.BLOFIN,
            account_id="follower-1",
            symbol="BTC-USDT",
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,
            order_type=OrderType.MARKET,
            quantity=Decimal("0"),
            client_order_id="copy-test-1",
        )
