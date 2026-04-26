# Shared Events

Schema package boundary for NATS JetStream subjects and event versioning.

Concrete domain event schemas live in `packages/domain`.

This package currently owns:

- NATS JetStream subject constants
- the `COPY_TRADE_EVENTS` stream subject list
- a small JSON JetStream wrapper
- `Nats-Msg-Id` header generation from event `idempotency_key`
- durable consumer names for Copy Engine trade and execution-result handling
- retry configuration for durable consumers
- dead-letter publishing to `system.dead_letter.created` after final delivery failure

The wrapper is intentionally narrow. It is for internal service-to-service events and does not contain exchange-specific behavior.
