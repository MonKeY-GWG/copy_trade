from copy_trade_copy_engine.dead_letters import PostgresDeadLetterEventRecorder


class FakeAcquire:
    def __init__(self, connection: "FakeConnection") -> None:
        self._connection = connection

    async def __aenter__(self) -> "FakeConnection":
        return self._connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.connection)


class FakeConnection:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[object, ...]] = []

    async def execute(self, _query: str, *args: object) -> str:
        self.execute_calls.append(args)
        return "INSERT 0 1"


async def test_postgres_dead_letter_recorder_persists_safe_operational_payload() -> None:
    pool = FakePool()
    recorder = PostgresDeadLetterEventRecorder(pool)

    await recorder.record(
        {
            "idempotency_key": "dlq:test",
            "failed_subject": "exchange.trade_event.normalized",
            "delivery_attempt": 3,
            "max_delivery_attempts": 3,
            "error_type": "RuntimeError",
            "payload": {
                "api_secret": "hidden",
                "event_id": "event-1",
                "raw_event": {"token": "hidden"},
            },
        }
    )

    args = pool.connection.execute_calls[0]
    assert args[0] == "dlq:test"
    assert args[1] == "exchange.trade_event.normalized"
    assert args[2] == 3
    assert args[3] == 3
    assert args[4] == "RuntimeError"
    assert args[5] == (
        '{"api_secret":"[redacted]","event_id":"event-1","raw_event":"[redacted]"}'
    )
