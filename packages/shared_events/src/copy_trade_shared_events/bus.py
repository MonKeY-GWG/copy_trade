import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import nats
from nats.aio.client import Client as NatsClient
from nats.aio.msg import Msg
from nats.js.api import AckPolicy, ConsumerConfig, RetentionPolicy, StorageType, StreamConfig
from nats.js.client import JetStreamContext
from nats.js.errors import NotFoundError
from pydantic import BaseModel

from copy_trade_shared_events.subjects import (
    ALL_EVENT_SUBJECTS,
    DEAD_LETTER_EVENT_CREATED,
    EVENT_STREAM,
)

NATS_MSG_ID_HEADER = "Nats-Msg-Id"

JsonPayload = BaseModel | Mapping[str, Any]
EventHandler = Callable[["EventBusMessage"], Awaitable[None]]
DeadLetterPublisher = Callable[[str, Mapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class EventBusMessage:
    subject: str
    data: dict[str, Any]


@dataclass(frozen=True)
class EventRetryPolicy:
    max_deliver: int = 3
    ack_wait_seconds: float = 30.0
    dead_letter_subject: str = DEAD_LETTER_EVENT_CREATED


class NatsJetStreamEventBus:
    def __init__(
        self,
        nats_url: str,
        *,
        stream_name: str = EVENT_STREAM,
        stream_subjects: tuple[str, ...] = ALL_EVENT_SUBJECTS,
        client_name: str = "copy-trade-event-bus",
        retry_policy: EventRetryPolicy | None = None,
    ) -> None:
        self._nats_url = nats_url
        self._stream_name = stream_name
        self._stream_subjects = stream_subjects
        self._client_name = client_name
        self._retry_policy = retry_policy or EventRetryPolicy()
        self._client: NatsClient | None = None
        self._jetstream: JetStreamContext | None = None

    async def connect(self) -> "NatsJetStreamEventBus":
        self._client = await nats.connect(
            servers=self._nats_url,
            name=self._client_name,
            allow_reconnect=True,
            max_reconnect_attempts=-1,
        )
        self._jetstream = self._client.jetstream()
        return self

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def ensure_stream(self) -> None:
        jetstream = self._require_jetstream()
        stream_config = build_stream_config(
            self._stream_name,
            self._stream_subjects,
        )
        try:
            stream_info = await jetstream.stream_info(self._stream_name)
        except NotFoundError:
            await jetstream.add_stream(stream_config)
            return

        configured_subjects = set(stream_info.config.subjects or ())
        missing_subjects = set(self._stream_subjects) - configured_subjects
        if missing_subjects:
            await jetstream.update_stream(stream_config)

    async def publish_json(self, subject: str, payload: JsonPayload) -> None:
        await self.ensure_stream()
        await self._require_jetstream().publish(
            subject,
            encode_json_payload(payload),
            stream=self._stream_name,
            headers=build_publish_headers(payload),
        )

    async def subscribe_json(
        self,
        subject: str,
        *,
        durable: str,
        handler: EventHandler,
    ) -> None:
        await self.ensure_stream()
        await self.ensure_consumer_config(subject, durable)
        await self._require_jetstream().subscribe(
            subject,
            cb=build_message_callback(
                handler,
                retry_policy=self._retry_policy,
                dead_letter_publisher=self.publish_json,
            ),
            durable=durable,
            stream=self._stream_name,
            manual_ack=True,
            config=build_consumer_config(
                durable,
                self._retry_policy,
                subject=subject,
            ),
        )

    def _require_jetstream(self) -> JetStreamContext:
        if self._jetstream is None:
            raise RuntimeError("event bus is not connected")
        return self._jetstream

    async def ensure_consumer_config(self, subject: str, durable: str) -> None:
        jetstream = self._require_jetstream()
        try:
            consumer_info = await jetstream.consumer_info(self._stream_name, durable)
        except NotFoundError:
            return

        current_config = consumer_info.config
        if (
            current_config.max_deliver == self._retry_policy.max_deliver
            and current_config.ack_wait == self._retry_policy.ack_wait_seconds
            and current_config.filter_subject == subject
        ):
            return

        await jetstream.add_consumer(
            self._stream_name,
            build_consumer_config(
                durable,
                self._retry_policy,
                subject=subject,
                deliver_subject=current_config.deliver_subject,
            ),
        )


def build_stream_config(stream_name: str, subjects: tuple[str, ...]) -> StreamConfig:
    return StreamConfig(
        name=stream_name,
        subjects=list(subjects),
        retention=RetentionPolicy.LIMITS,
        storage=StorageType.FILE,
        duplicate_window=120,
    )


def build_consumer_config(
    durable: str,
    retry_policy: EventRetryPolicy,
    *,
    subject: str | None = None,
    deliver_subject: str | None = None,
) -> ConsumerConfig:
    return ConsumerConfig(
        durable_name=durable,
        ack_policy=AckPolicy.EXPLICIT,
        ack_wait=retry_policy.ack_wait_seconds,
        max_deliver=retry_policy.max_deliver,
        filter_subject=subject,
        deliver_subject=deliver_subject,
    )


def build_message_callback(
    handler: EventHandler,
    *,
    retry_policy: EventRetryPolicy | None = None,
    dead_letter_publisher: DeadLetterPublisher | None = None,
) -> Callable[[Msg], Awaitable[None]]:
    async def wrapped(message: Msg) -> None:
        await handle_message(
            message,
            handler,
            retry_policy=retry_policy,
            dead_letter_publisher=dead_letter_publisher,
        )

    return wrapped


async def handle_message(
    message: Msg,
    handler: EventHandler,
    *,
    retry_policy: EventRetryPolicy | None = None,
    dead_letter_publisher: DeadLetterPublisher | None = None,
) -> None:
    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(message.data.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("event payload must be a JSON object")
        await handler(EventBusMessage(subject=message.subject, data=payload))
    except Exception as exc:
        if await maybe_dead_letter_message(
            message,
            payload,
            exc,
            retry_policy=retry_policy,
            dead_letter_publisher=dead_letter_publisher,
        ):
            await message.ack()
            return
        await message.nak()
        if retry_policy is not None:
            return
        raise
    await message.ack()


async def maybe_dead_letter_message(
    message: Msg,
    payload: Mapping[str, Any] | None,
    exc: Exception,
    *,
    retry_policy: EventRetryPolicy | None,
    dead_letter_publisher: DeadLetterPublisher | None,
) -> bool:
    if retry_policy is None or dead_letter_publisher is None:
        return False

    delivery_attempt = get_delivery_attempt(message)
    if delivery_attempt < retry_policy.max_deliver:
        return False

    await dead_letter_publisher(
        retry_policy.dead_letter_subject,
        build_dead_letter_payload(
            message=message,
            payload=payload,
            exc=exc,
            delivery_attempt=delivery_attempt,
            max_delivery_attempts=retry_policy.max_deliver,
        ),
    )
    return True


def build_dead_letter_payload(
    *,
    message: Msg,
    payload: Mapping[str, Any] | None,
    exc: Exception,
    delivery_attempt: int,
    max_delivery_attempts: int,
) -> dict[str, Any]:
    original_idempotency_key = None
    if payload is not None:
        original_idempotency_key = payload.get("idempotency_key")
    sequence = get_stream_sequence(message)
    return {
        "idempotency_key": build_dead_letter_idempotency_key(
            message.subject,
            original_idempotency_key,
            sequence,
        ),
        "failed_subject": message.subject,
        "delivery_attempt": delivery_attempt,
        "max_delivery_attempts": max_delivery_attempts,
        "error_type": type(exc).__name__,
        "payload": dict(payload) if payload is not None else None,
    }


def build_dead_letter_idempotency_key(
    failed_subject: str,
    original_idempotency_key: object | None,
    stream_sequence: int | None,
) -> str:
    if original_idempotency_key:
        return f"dlq:{failed_subject}:{original_idempotency_key}"
    if stream_sequence is not None:
        return f"dlq:{failed_subject}:seq:{stream_sequence}"
    return f"dlq:{failed_subject}:unknown"


def get_delivery_attempt(message: Msg) -> int:
    try:
        return int(message.metadata.num_delivered)
    except Exception:
        return 1


def get_stream_sequence(message: Msg) -> int | None:
    try:
        return int(message.metadata.sequence.stream)
    except Exception:
        return None


def encode_json_payload(payload: JsonPayload) -> bytes:
    if isinstance(payload, BaseModel):
        serializable = payload.model_dump(mode="json")
    else:
        serializable = dict(payload)
    return json.dumps(serializable, separators=(",", ":"), default=str).encode("utf-8")


def build_publish_headers(payload: JsonPayload) -> dict[str, str] | None:
    if isinstance(payload, BaseModel):
        idempotency_key = getattr(payload, "idempotency_key", None)
    else:
        idempotency_key = payload.get("idempotency_key")

    if not idempotency_key:
        return None
    return {NATS_MSG_ID_HEADER: str(idempotency_key)}
