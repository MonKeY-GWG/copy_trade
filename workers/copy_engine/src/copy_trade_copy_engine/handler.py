from datetime import datetime
from uuid import UUID

from copy_trade_domain.events import CopyExecutionRequest, Exchange, NormalizedOrderEvent


def event_is_after_follow_start(event: NormalizedOrderEvent, effective_from: datetime) -> bool:
    return event.occurred_at >= effective_from


def build_dry_run_execution_request(
    event: NormalizedOrderEvent,
    copy_relationship_id: UUID,
    follower_account_id: str,
    target_exchange: Exchange,
    target_symbol: str,
) -> CopyExecutionRequest:
    return CopyExecutionRequest(
        occurred_at=event.occurred_at,
        observed_at=event.observed_at,
        source_exchange=event.source_exchange,
        source_account_id=event.source_account_id,
        idempotency_key=f"copy:{copy_relationship_id}:{event.idempotency_key}",
        trace_id=event.trace_id,
        source_event_id=event.event_id,
        copy_relationship_id=copy_relationship_id,
        follower_account_id=follower_account_id,
        target_exchange=target_exchange,
        target_symbol=target_symbol,
        order_type=event.order_type,
        side=event.side,
        position_side=event.position_side,
        quantity=event.quantity,
        price=event.price,
        trigger_price=event.trigger_price,
        reduce_only=event.reduce_only,
        post_only=event.post_only,
        dry_run=True,
    )
