# Sprint 1 Backlog: Neustart Foundation

Stand: 2026-04-26
Sprint-Ziel: Ein sauberes, lauffaehiges Grundgeruest fuer API, Worker, Events, Datenbank und erste Adapter-Spikes schaffen.

## 1. Repository Reset vorbereiten

Akzeptanzkriterien:

- Entscheidung dokumentiert, dass alter Code nicht migriert wird.
- Keine alten Dateien geloescht ohne Freigabe.
- Zielstruktur fuer `apps`, `workers`, `packages`, `infra`, `docs` angelegt.
- Lokales Git-Repository initialisiert oder mit GitHub-Remote verbunden, sobald gewuenscht.

## 2. FastAPI API Skeleton

Akzeptanzkriterien:

- `apps/api` enthaelt Python-Projekt mit FastAPI.
- Endpoints: `/health`, `/ready`, `/version`.
- Strukturierte Logs mit request id/trace id.
- Konfiguration ueber Environment Settings.
- Test fuer Healthcheck vorhanden.

## 3. Docker Compose Foundation

Akzeptanzkriterien:

- Services: postgres, redis, nats, api.
- NATS JetStream aktiviert.
- Healthchecks fuer alle Infrastrukturservices.
- `.env.example` ohne Secrets.

## 4. Database Foundation

Akzeptanzkriterien:

- SQLAlchemy oder SQLModel Entscheidung dokumentiert.
- Alembic eingerichtet.
- Erste Migration fuer users, roles, audit_logs, exchange_accounts, api_credentials.
- API credentials nur als verschluesselte Payload modelliert, keine Plaintext-Felder.

## 5. Shared Domain Events

Akzeptanzkriterien:

- Pydantic-Modelle fuer normalized trade/order event, copy execution request/result, notification request.
- `schema_version`, `event_id`, `idempotency_key`, `trace_id` verpflichtend.
- Unit Tests fuer Schema-Validation.

## 6. NATS Event Bus Wrapper

Akzeptanzkriterien:

- Publish/Subscribe Wrapper fuer JetStream.
- Consumer naming convention dokumentiert.
- Retry/DLQ-Konzept als TODO/ADR-Notiz erfasst.
- Lokaler Smoke Test publiziert und konsumiert ein Event.

## 7. Exchange Adapter Interfaces

Akzeptanzkriterien:

- Python Protocol/ABC fuer Adapter Contract.
- Gemeinsame Error-Typen: `UNSUPPORTED_FEATURE`, `AUTH_FAILED`, `RATE_LIMITED`, `EXCHANGE_UNAVAILABLE`, `UNKNOWN_EXECUTION_STATUS`, `VALIDATION_FAILED`.
- Kein Exchange-spezifischer Code in Copy Engine Packages.

## 8. Hyperliquid Spike

Akzeptanzkriterien:

- Auth/signing Pfad verifiziert.
- Markets laden.
- Account State/Positions lesen.
- Private Stream fuer Order/Fills konzeptionell oder mit Test-Account verifiziert.
- Rate/User-Limit-Notizen aktualisiert.

## 9. Aster Spike

Akzeptanzkriterien:

- V3 Endpoint-Konfiguration verifiziert.
- Signatur mit user/signer/nonce prototypisiert.
- Markets laden.
- User Data Stream Ansatz dokumentiert.
- 503 unknown status Reconciliation-Plan dokumentiert.

## 10. BloFin Spike

Akzeptanzkriterien:

- REST Auth Header/Signature prototypisiert.
- Demo Trading Verbindung getestet, wenn Credentials vorhanden.
- API-Key-Permission-Check entworfen.
- Entscheidungsvorlage: regular trading endpoints vs native copy trading endpoints.

## 11. Minimal Copy Engine Skeleton

Akzeptanzkriterien:

- Worker startet und subscribed auf `exchange.trade_event.normalized`.
- Idempotency Store konzeptionell vorbereitet.
- Noch keine echten Orders ohne explizite Test/Dry-Run-Konfiguration.
- Failure Events werden geschrieben/publiziert.

## 12. Verification Workflow

Akzeptanzkriterien:

- Jede externe API-Behauptung in Docs mit Quelle oder Spike-Status.
- Offene Annahmen in Backlog/ADR markiert.
- Vor Umsetzung von Exchange-Execution wird Doku erneut geprueft.
