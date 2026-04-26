from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from copy_trade_copy_engine.database import normalize_asyncpg_database_url
from copy_trade_copy_engine.execution_requests import PostgresCopyExecutionRequestRecorder
from copy_trade_copy_engine.execution_results import PostgresCopyExecutionResultRecorder
from copy_trade_copy_engine.handler import build_dry_run_execution_request
from copy_trade_copy_engine.idempotency import PostgresIdempotencyStore
from copy_trade_copy_engine.relationships import PostgresCopyRelationshipProvider
from copy_trade_domain.events import (
    CopyExecutionResult,
    CopyExecutionStatus,
    Exchange,
    NormalizedOrderEvent,
    OrderSide,
    OrderType,
    PositionSide,
)


class FakeConnection:
    def __init__(
        self,
        *,
        rows: Sequence[dict[str, Any]] = (),
        execute_result: str = "INSERT 0 1",
    ) -> None:
        self.rows = rows
        self.execute_result = execute_result
        self.fetch_args: tuple[object, ...] | None = None
        self.execute_args: tuple[object, ...] | None = None
        self.execute_calls: list[tuple[object, ...]] = []

    async def fetch(self, query: str, *args: object) -> Sequence[dict[str, Any]]:
        self.fetch_args = args
        return self.rows

    async def execute(self, query: str, *args: object) -> str:
        self.execute_args = args
        self.execute_calls.append(args)
        return self.execute_result


class FakeAcquire:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.closed = False

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.connection)

    async def close(self) -> None:
        self.closed = True


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


def test_normalize_asyncpg_database_url_accepts_sqlalchemy_style_url() -> None:
    assert (
        normalize_asyncpg_database_url("postgresql+asyncpg://user:pass@localhost/db")
        == "postgresql://user:pass@localhost/db"
    )
    assert (
        normalize_asyncpg_database_url("postgresql://user:pass@localhost/db")
        == "postgresql://user:pass@localhost/db"
    )


async def test_postgres_relationship_provider_loads_active_relationships_for_event() -> None:
    event = make_event()
    relationship_id = uuid4()
    connection = FakeConnection(
        rows=(
            {
                "id": relationship_id,
                "follower_account_id": "follower-1",
                "target_exchange": Exchange.BLOFIN.value,
                "target_symbol": "BTC-USDT",
                "effective_from": event.occurred_at,
                "active": True,
            },
        ),
    )
    provider = PostgresCopyRelationshipProvider(FakePool(connection))

    relationships = await provider.list_active_for_event(event)

    assert connection.fetch_args == (
        Exchange.HYPERLIQUID.value,
        "trader-1",
        "BTC-USD",
        event.occurred_at,
    )
    assert len(relationships) == 1
    assert relationships[0].copy_relationship_id == relationship_id
    assert relationships[0].target_exchange == Exchange.BLOFIN
    assert relationships[0].target_symbol == "BTC-USDT"


async def test_postgres_idempotency_store_reserves_new_key() -> None:
    connection = FakeConnection(execute_result="INSERT 0 1")
    store = PostgresIdempotencyStore(FakePool(connection))

    reserved = await store.reserve("copy:relationship:event")

    assert reserved is True
    assert connection.execute_args == ("copy:relationship:event",)


async def test_postgres_idempotency_store_rejects_duplicate_key() -> None:
    connection = FakeConnection(execute_result="INSERT 0 0")
    store = PostgresIdempotencyStore(FakePool(connection))

    reserved = await store.reserve("copy:relationship:event")

    assert reserved is False


async def test_postgres_idempotency_store_releases_key() -> None:
    connection = FakeConnection()
    store = PostgresIdempotencyStore(FakePool(connection))

    await store.release("copy:relationship:event")

    assert connection.execute_args == ("copy:relationship:event",)


async def test_postgres_execution_request_recorder_persists_dry_run_request() -> None:
    event = make_event()
    relationship_id = uuid4()
    request = build_dry_run_execution_request(
        event=event,
        copy_relationship_id=relationship_id,
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
    )
    connection = FakeConnection()
    recorder = PostgresCopyExecutionRequestRecorder(FakePool(connection))

    await recorder.record(request)

    assert connection.execute_args == (
        request.event_id,
        request.schema_version,
        request.occurred_at,
        request.observed_at,
        Exchange.HYPERLIQUID.value,
        "trader-1",
        request.idempotency_key,
        request.trace_id,
        event.event_id,
        relationship_id,
        "follower-1",
        Exchange.BLOFIN.value,
        "BTC-USDT",
        OrderType.MARKET.value,
        OrderSide.BUY.value,
        PositionSide.LONG.value,
        Decimal("0.01"),
        None,
        None,
        False,
        False,
        100,
        True,
        "REQUESTED",
    )


async def test_postgres_execution_request_recorder_marks_request_published() -> None:
    event = make_event()
    request = build_dry_run_execution_request(
        event=event,
        copy_relationship_id=uuid4(),
        follower_account_id="follower-1",
        target_exchange=Exchange.BLOFIN,
        target_symbol="BTC-USDT",
    )
    connection = FakeConnection()
    recorder = PostgresCopyExecutionRequestRecorder(FakePool(connection))

    await recorder.mark_published(request)

    assert connection.execute_args == (request.event_id,)


async def test_postgres_execution_result_recorder_persists_result_and_updates_request() -> None:
    request_id = uuid4()
    result = CopyExecutionResult(
        occurred_at=datetime.now(UTC),
        source_exchange=Exchange.BLOFIN,
        source_account_id="follower-1",
        idempotency_key="result-fill-1",
        trace_id="trace-1",
        request_id=request_id,
        status=CopyExecutionStatus.FILLED,
        exchange_order_id="exchange-order-1",
        raw_response={"exchange_status": "filled"},
    )
    connection = FakeConnection()
    recorder = PostgresCopyExecutionResultRecorder(FakePool(connection))

    await recorder.record(result)

    assert connection.execute_calls == [
        (
            result.event_id,
            result.schema_version,
            result.occurred_at,
            result.observed_at,
            Exchange.BLOFIN.value,
            "follower-1",
            "result-fill-1",
            "trace-1",
            request_id,
            CopyExecutionStatus.FILLED.value,
            "exchange-order-1",
            None,
            '{"exchange_status":"filled"}',
        ),
        (
            request_id,
            CopyExecutionStatus.FILLED.value,
        ),
    ]
