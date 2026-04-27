import logging
from collections.abc import Sequence
from dataclasses import dataclass

from copy_trade_copy_engine.handler import (
    build_dry_run_execution_request,
    event_is_after_follow_start,
)
from copy_trade_copy_engine.idempotency import IdempotencyStore
from copy_trade_copy_engine.relationships import CopyRelationship, CopyRelationshipProvider
from copy_trade_domain.events import CopyExecutionRequest, NormalizedOrderEvent

logger = logging.getLogger("copy_trade.copy_engine")


@dataclass(frozen=True)
class ProcessingResult:
    requests: tuple[CopyExecutionRequest, ...]
    skipped_duplicates: int
    skipped_inactive: int
    skipped_before_follow_start: int
    skipped_exchange_account: int = 0
    skipped_subscription: int = 0
    skipped_risk: int = 0


class CopyEventProcessor:
    def __init__(
        self,
        relationship_provider: CopyRelationshipProvider,
        idempotency_store: IdempotencyStore,
    ) -> None:
        self._relationship_provider = relationship_provider
        self._idempotency_store = idempotency_store

    async def process_normalized_order_event(
        self,
        event: NormalizedOrderEvent,
    ) -> ProcessingResult:
        relationships = await self._relationship_provider.list_active_for_event(event)
        return await self._build_requests_for_relationships(event, relationships)

    async def release_idempotency_key(self, key: str) -> None:
        await self._idempotency_store.release(key)

    async def _build_requests_for_relationships(
        self,
        event: NormalizedOrderEvent,
        relationships: Sequence[CopyRelationship],
    ) -> ProcessingResult:
        requests: list[CopyExecutionRequest] = []
        skipped_duplicates = 0
        skipped_inactive = 0
        skipped_before_follow_start = 0
        skipped_exchange_account = 0
        skipped_subscription = 0
        skipped_risk = 0

        for relationship in relationships:
            if not relationship.active:
                skipped_inactive += 1
                continue
            if not relationship_has_active_exchange_accounts(relationship):
                skipped_exchange_account += 1
                continue
            if not relationship_has_active_subscription(relationship):
                skipped_subscription += 1
                continue
            if not relationship_passes_risk_settings(event, relationship):
                skipped_risk += 1
                continue
            if not event_is_after_follow_start(event, relationship.effective_from):
                skipped_before_follow_start += 1
                continue

            request = build_dry_run_execution_request(
                event=event,
                copy_relationship_id=relationship.copy_relationship_id,
                follower_account_id=relationship.follower_account_id,
                target_exchange=relationship.target_exchange,
                target_symbol=relationship.target_symbol,
            )
            if not await self._idempotency_store.reserve(request.idempotency_key):
                skipped_duplicates += 1
                continue
            requests.append(request)

        logger.info(
            "normalized trade event processed event_id=%s trace_id=%s requests=%s "
            "duplicates=%s inactive=%s before_follow_start=%s exchange_account=%s "
            "subscription=%s risk=%s",
            event.event_id,
            event.trace_id,
            len(requests),
            skipped_duplicates,
            skipped_inactive,
            skipped_before_follow_start,
            skipped_exchange_account,
            skipped_subscription,
            skipped_risk,
        )

        return ProcessingResult(
            requests=tuple(requests),
            skipped_duplicates=skipped_duplicates,
            skipped_inactive=skipped_inactive,
            skipped_before_follow_start=skipped_before_follow_start,
            skipped_exchange_account=skipped_exchange_account,
            skipped_subscription=skipped_subscription,
            skipped_risk=skipped_risk,
        )


def relationship_has_active_exchange_accounts(relationship: CopyRelationship) -> bool:
    return (
        relationship.source_account_status == "active"
        and relationship.follower_account_status == "active"
        and relationship.follower_user_status == "active"
    )


def relationship_has_active_subscription(relationship: CopyRelationship) -> bool:
    return (
        relationship.subscription_status in {"active", "trialing"}
        and relationship.copy_trading_enabled
    )


def relationship_passes_risk_settings(
    event: NormalizedOrderEvent,
    relationship: CopyRelationship,
) -> bool:
    if not relationship.risk_enabled:
        return False
    if relationship.risk_max_slippage_bps is None:
        return False
    if relationship.max_slippage_bps > relationship.risk_max_slippage_bps:
        return False
    if (
        relationship.risk_max_order_quantity is not None
        and event.quantity > relationship.risk_max_order_quantity
    ):
        return False
    if relationship.risk_max_leverage is not None and event.leverage is not None:
        return event.leverage <= relationship.risk_max_leverage
    return True
