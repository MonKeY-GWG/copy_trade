import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from copy_trade_copy_engine.config import Settings, get_settings
from copy_trade_copy_engine.database import DatabasePool, create_asyncpg_pool
from copy_trade_copy_engine.dead_letters import (
    DeadLetterEventRecorder,
    NoopDeadLetterEventRecorder,
    PostgresDeadLetterEventRecorder,
)
from copy_trade_copy_engine.execution_requests import (
    CopyExecutionRequestRecorder,
    NoopCopyExecutionRequestRecorder,
    PostgresCopyExecutionRequestRecorder,
)
from copy_trade_copy_engine.execution_results import (
    CopyExecutionResultRecorder,
    NoopCopyExecutionResultRecorder,
    PostgresCopyExecutionResultRecorder,
)
from copy_trade_copy_engine.idempotency import PostgresIdempotencyStore
from copy_trade_copy_engine.processor import CopyEventProcessor
from copy_trade_copy_engine.relationships import PostgresCopyRelationshipProvider
from copy_trade_domain.events import CopyExecutionResult, NormalizedOrderEvent
from copy_trade_shared_events import (
    COPY_ENGINE_DEAD_LETTER_DURABLE,
    COPY_ENGINE_EXECUTION_RESULT_DURABLES,
    COPY_ENGINE_NORMALIZED_TRADES_DURABLE,
    COPY_EXECUTION_REQUESTED,
    COPY_EXECUTION_RESULT_SUBJECTS,
    DEAD_LETTER_EVENT_CREATED,
    EXCHANGE_TRADE_EVENT_NORMALIZED,
    EventBusMessage,
    NatsJetStreamEventBus,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("copy_trade.copy_engine")

EventHandler = Callable[[EventBusMessage], Awaitable[None]]


class EventBus(Protocol):
    async def publish_json(self, subject: str, payload: object) -> None:
        raise NotImplementedError

    async def subscribe_json(
        self,
        subject: str,
        *,
        durable: str,
        handler: EventHandler,
    ) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


async def handle_normalized_trade_event(
    message: EventBusMessage,
    *,
    processor: CopyEventProcessor,
    publisher: EventBus,
    request_recorder: CopyExecutionRequestRecorder,
) -> None:
    event = NormalizedOrderEvent.model_validate(message.data)
    result = await processor.process_normalized_order_event(event)
    for request in result.requests:
        await request_recorder.record(request)
        try:
            await publisher.publish_json(COPY_EXECUTION_REQUESTED, request)
        except Exception:
            await processor.release_idempotency_key(request.idempotency_key)
            raise
        await request_recorder.mark_published(request)


def build_normalized_trade_handler(
    processor: CopyEventProcessor,
    publisher: EventBus,
    request_recorder: CopyExecutionRequestRecorder,
) -> EventHandler:
    async def handler(message: EventBusMessage) -> None:
        await handle_normalized_trade_event(
            message,
            processor=processor,
            publisher=publisher,
            request_recorder=request_recorder,
        )

    return handler


async def handle_copy_execution_result_event(
    message: EventBusMessage,
    *,
    result_recorder: CopyExecutionResultRecorder,
) -> None:
    result = CopyExecutionResult.model_validate(message.data)
    await result_recorder.record(result)


def build_copy_execution_result_handler(
    result_recorder: CopyExecutionResultRecorder,
) -> EventHandler:
    async def handler(message: EventBusMessage) -> None:
        await handle_copy_execution_result_event(
            message,
            result_recorder=result_recorder,
        )

    return handler


async def handle_dead_letter_event(
    message: EventBusMessage,
    *,
    dead_letter_recorder: DeadLetterEventRecorder,
) -> None:
    await dead_letter_recorder.record(message.data)


def build_dead_letter_handler(
    dead_letter_recorder: DeadLetterEventRecorder,
) -> EventHandler:
    async def handler(message: EventBusMessage) -> None:
        await handle_dead_letter_event(message, dead_letter_recorder=dead_letter_recorder)

    return handler


async def run(
    *,
    settings: Settings | None = None,
    event_bus: EventBus | None = None,
    processor: CopyEventProcessor | None = None,
    database_pool: DatabasePool | None = None,
    request_recorder: CopyExecutionRequestRecorder | None = None,
    result_recorder: CopyExecutionResultRecorder | None = None,
    dead_letter_recorder: DeadLetterEventRecorder | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    settings = settings or get_settings()
    owns_event_bus = False
    owns_database_pool = False

    try:
        if processor is None:
            if database_pool is None:
                database_pool = await create_asyncpg_pool(settings.database_url)
                owns_database_pool = True
            processor = CopyEventProcessor(
                relationship_provider=PostgresCopyRelationshipProvider(database_pool),
                idempotency_store=PostgresIdempotencyStore(database_pool),
            )
            if request_recorder is None:
                request_recorder = PostgresCopyExecutionRequestRecorder(database_pool)
            if result_recorder is None:
                result_recorder = PostgresCopyExecutionResultRecorder(database_pool)
            if dead_letter_recorder is None:
                dead_letter_recorder = PostgresDeadLetterEventRecorder(database_pool)

        if request_recorder is None:
            request_recorder = NoopCopyExecutionRequestRecorder()
        if result_recorder is None:
            result_recorder = NoopCopyExecutionResultRecorder()
        if dead_letter_recorder is None:
            dead_letter_recorder = NoopDeadLetterEventRecorder()

        if event_bus is None:
            event_bus = await NatsJetStreamEventBus(
                settings.nats_url,
                client_name="copy-trade-copy-engine",
            ).connect()
            owns_event_bus = True

        await event_bus.subscribe_json(
            EXCHANGE_TRADE_EVENT_NORMALIZED,
            durable=COPY_ENGINE_NORMALIZED_TRADES_DURABLE,
            handler=build_normalized_trade_handler(processor, event_bus, request_recorder),
        )
        logger.info(
            "copy engine subscribed subject=%s durable=%s",
            EXCHANGE_TRADE_EVENT_NORMALIZED,
            COPY_ENGINE_NORMALIZED_TRADES_DURABLE,
        )
        result_handler = build_copy_execution_result_handler(result_recorder)
        for subject in COPY_EXECUTION_RESULT_SUBJECTS:
            await event_bus.subscribe_json(
                subject,
                durable=COPY_ENGINE_EXECUTION_RESULT_DURABLES[subject],
                handler=result_handler,
            )
            logger.info(
                "copy engine subscribed subject=%s durable=%s",
                subject,
                COPY_ENGINE_EXECUTION_RESULT_DURABLES[subject],
            )
        await event_bus.subscribe_json(
            DEAD_LETTER_EVENT_CREATED,
            durable=COPY_ENGINE_DEAD_LETTER_DURABLE,
            handler=build_dead_letter_handler(dead_letter_recorder),
        )
        logger.info(
            "copy engine subscribed subject=%s durable=%s",
            DEAD_LETTER_EVENT_CREATED,
            COPY_ENGINE_DEAD_LETTER_DURABLE,
        )
        await (stop_event or asyncio.Event()).wait()
    finally:
        if owns_event_bus:
            await event_bus.close()
        if owns_database_pool and database_pool is not None:
            await database_pool.close()


if __name__ == "__main__":
    asyncio.run(run())
