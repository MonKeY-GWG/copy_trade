# ADR-004: Event Retry und Dead Letter Queue

Status: Akzeptiert
Datum: 2026-04-26

## Kontext

Copy-Trading-Events duerfen nicht unendlich oft dieselben Worker blockieren. Gleichzeitig darf ein temporaerer Fehler nicht sofort zum Datenverlust fuehren. Besonders kritisch sind doppelte Trade-Ausfuehrung, verlorene Execution-Results und schwer nachvollziehbare Fehlerketten.

## Entscheidung

NATS JetStream Consumer fuer die Copy Engine werden mit expliziter Ack-Policy und begrenzter Zustellung konfiguriert:

- `ack_policy`: explicit
- `ack_wait`: 30 Sekunden
- `max_deliver`: 3
- Dead-Letter-Subject: `system.dead_letter.created`

Wenn ein Handler vor Erreichen von `max_deliver` fehlschlaegt, wird das Event per `nak` erneut zugestellt. Wenn der letzte Versuch fehlschlaegt, publiziert der Event-Bus eine Dead-Letter-Nachricht und bestaetigt das Originalevent per `ack`, damit der Consumer nicht dauerhaft blockiert.

## Dead-Letter Payload

Dead-Letter-Events enthalten:

- `idempotency_key`
- `failed_subject`
- `delivery_attempt`
- `max_delivery_attempts`
- `error_type`
- `payload`

Exception-Details werden nicht als freie Lognachricht ausgegeben. Der Payload bleibt fuer interne Reprocessing- und Diagnosezwecke erhalten.

## Konsequenzen

- Dauerhaft fehlerhafte Events blockieren Copy-Engine-Consumer nicht endlos.
- Operative Fehler werden ueber ein eigenes Subject sichtbar.
- Bestehende lokale Durable Consumer werden beim Start auf die erwartete Retry-Konfiguration aktualisiert.
- Reprocessing, Admin-UI fuer DLQ und Alerting sind Folgeaufgaben.

## Offene Punkte

- OFFEN: DLQ-Reprocessing-Workflow umsetzen; Implementierungsplan siehe `docs/restart/05_open_implementation_plans.md`
- OFFEN: Monitoring/Alerting fuer DLQ-Events umsetzen; Implementierungsplan siehe `docs/restart/05_open_implementation_plans.md`
- OFFEN: Aufbewahrungs- und Purge-Policy fuer DLQ-Events festlegen und umsetzen; Implementierungsplan siehe `docs/restart/05_open_implementation_plans.md`
