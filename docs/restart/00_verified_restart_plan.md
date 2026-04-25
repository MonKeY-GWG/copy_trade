# Copy Trade Neustartplan

Stand: 2026-04-26
Quelle Produktplanung: `copy_trading_platform_concept_v1.pdf` vom 2026-04-16
Status: Arbeitsgrundlage fuer Neustart, alter Code wird nicht als Architekturvorgabe uebernommen.

## Verifikationsregel

Technische Aussagen in diesem Projekt werden gegen Primarquellen verifiziert, bevor sie als Entscheidung oder Aufgabe in den Backlog gehen.

Quellenhierarchie:

1. Produktwahrheit: `copy_trading_platform_concept_v1.pdf`
2. Exchange-Wahrheit: offizielle API-Dokumentationen von Hyperliquid, Aster und BloFin
3. Code-Wahrheit: lokaler Projektstand in `C:\Github\copy_trade`
4. Annahmen: muessen explizit als Annahme oder Spike markiert werden

## Verifizierter lokaler Zustand

- Das lokale Projekt liegt unter `C:\Github\copy_trade`.
- Die Datei `copy_trading_platform_concept_v1.pdf` ist vorhanden.
- Die alte NestJS/Next.js/Prisma-Codebasis wurde nach `legacy/2026-04-26-pre-restart/` archiviert und ist lokal von Git ignoriert.
- Das neue Projektgeruest liegt in `apps/`, `workers/`, `packages/`, `infra/`, `docs/restart/` und `docs/adr/`.
- Das lokale Git-Repository ist initialisiert, Branch `main`, Remote `https://github.com/MonKeY-GWG/copy_trade.git`.
- `origin/main` ist auf GitHub gepusht und per `git ls-remote origin refs/heads/main` verifiziert.

## Produktentscheidung

Wir starten neu. Der vorhandene NestJS-Code wird nicht migriert und nicht als Referenzarchitektur verwendet. Er kann spaeter archiviert oder geloescht werden, aber nur nach expliziter Freigabe.

Begruendung:

- Das PDF verlangt eine tiefere Plattformarchitektur als der bestehende Code abbildet.
- Die empfohlene Zielarchitektur im PDF ist Python/FastAPI, separate Copy Engine, PostgreSQL, Redis, NATS JetStream, WebSockets und Docker.
- V1 fokussiert Perpetual Futures auf Hyperliquid, Aster und BloFin. Bestehende Spot- oder Binance-Ansaetze gehoeren nicht in den V1-Kern.

## Zielarchitektur V1

- Frontend: Next.js mit TypeScript
- Backend API: Python/FastAPI
- Copy Engine: separater Python-Worker, nicht Teil des API-Prozesses
- Exchange Streamer: separate Worker fuer private Exchange-Streams und Reconnect/Backfill
- Billing Worker: Zahlungserkennung und Subscription-Aktivierung
- Notification Worker: In-App und Telegram
- Datenbank: PostgreSQL mit Alembic-Migrationen
- Event Bus: NATS JetStream
- Cache/Locks/Rate State: Redis
- Observability: Prometheus/Grafana plus strukturierte Logs
- Deployment: Docker Compose fuer lokal/staging/prod, initial Hetzner-tauglich

## Vorgeschlagene Repo-Struktur

```text
copy_trade/
  apps/
    web/
    api/
  workers/
    copy_engine/
    exchange_streamer/
    billing_worker/
    notification_worker/
  packages/
    domain/
    exchange_adapters/
    shared_events/
  infra/
    docker/
    migrations/
  docs/
    adr/
    restart/
    api-research/
    product/
```

## Kernmodule

1. Identity und Rollen: Guest, Registered User, Follower, Trader, Admin
2. Wallet Binding: signierter Nonce-Flow fuer Billing-Wallets
3. Exchange Accounts: verschluesselte API-Credentials, Permission Checks, Rotation, Audit
4. Trader Profiles: manuelle Freigabe, Performance- und Risikoanzeige
5. Subscriptions: 50 USD-equivalent pro Trader/Monat, Laufzeiten 1/3/6/12 Monate, crypto-only
6. Copy Relationships: follower-spezifische Einstellungen, nur neue Trades ab Follow-Start
7. Market Registry: normalisierte Symbole, Perps-only, Exchange-Verfuegbarkeit
8. Copy Engine: Event-Normalisierung, Risiko/Sizing, Execution, Failure Handling
9. Notifications: In-App und Telegram mit User-Toggles
10. Admin/Ops: Approvals, Failures, Billing Exceptions, Health, Audit

## Datenmodell Startmenge

- `users`, `roles`, `sessions`
- `wallet_bindings`
- `exchange_accounts`, `api_credentials`, `api_credential_audit_logs`
- `trader_profiles`, `trader_approval_logs`
- `follower_profiles`
- `subscriptions`, `billing_orders`, `billing_transactions`, `revenue_splits`
- `copy_relationships`, `copy_settings`, `copy_settings_audit_logs`
- `exchange_symbols`, `market_registry_entries`
- `trade_events`, `copied_trades`, `trade_failures`, `order_mirror_links`
- `performance_snapshots`
- `notifications`, `notification_preferences`, `telegram_bindings`
- `audit_logs`

## Event-Schnittstellen

Alle Events bekommen mindestens:

- `event_id`
- `occurred_at`
- `observed_at`
- `source_exchange`
- `source_account_id`
- `idempotency_key`
- `schema_version`
- `trace_id`

Start-Subjects:

- `exchange.trade_event.normalized`
- `exchange.order_update.normalized`
- `copy.execution.requested`
- `copy.execution.accepted`
- `copy.execution.rejected`
- `copy.execution.filled`
- `copy.execution.failed`
- `billing.order.created`
- `billing.payment.verified`
- `notification.requested`
- `audit.event.created`

## Exchange Adapter Contract

Jeder Adapter implementiert mindestens:

- `get_markets()`
- `get_account_state()`
- `get_positions()`
- `subscribe_user_orders()`
- `subscribe_user_fills()`
- `place_order()`
- `place_tpsl_order()`
- `cancel_order()`
- `set_leverage()`
- `normalize_symbol()`
- `normalize_order_update()`
- `normalize_fill()`

Adapter duerfen Features nicht still imitieren. Wenn ein Exchange eine Funktion nicht gleichwertig unterstuetzt, liefert der Adapter `UNSUPPORTED_FEATURE`; die Copy Engine loggt und benachrichtigt.

## Roadmap

### Phase 0: Reset ohne Datenverlust

- Alte Codebasis unveraendert lassen oder nach Freigabe in `legacy/` verschieben.
- Neues Projektgeruest parallel aufbauen.
- ADRs fuer Stack, Event-Architektur und Adapter-Vertrag finalisieren.

### Phase 1: Foundation

- Python/FastAPI API mit `/health` und `/ready`.
- PostgreSQL, Redis, NATS JetStream via Docker Compose.
- Alembic, SQLAlchemy, Pydantic, strukturierte Logs.
- CI-Grundlage: Lint, Typecheck, Tests.

### Phase 2: Domain First

- Datenmodell und Migrationen fuer Identity, Exchange Accounts, Trader Profiles, Subscriptions, Copy Relationships, Events und Failures.
- Shared Event Schemas.
- Outbox Pattern fuer DB/Event-Bus-Konsistenz.

### Phase 3: Exchange Spikes

Pro Exchange verifizieren und prototypisieren:

- Authentifizierung
- Market/Symbol-Loading
- Account State und Positions
- Private Order/Fills Stream
- Test-/Demo-Order oder Dry-Run
- Rate Limits und Reconnect-Verhalten

### Phase 4: Copy Engine MVP

- Trader-Events normalisieren.
- Nur aktive Copy Relationships ab `effective_from` beruecksichtigen.
- Symbol-Mapping und Exchange-Auswahl.
- Percent-of-balance Sizing, Multiplier, Slippage, Leverage-Caps.
- Execution Requests idempotent verarbeiten.
- Failures persistieren und Notifications ausloesen.

### Phase 5: Billing MVP

- Wallet Binding per Signatur.
- Billing Order fuer Trader, Laufzeit, Betrag, Chain und Stablecoin.
- On-chain Zahlung verifizieren.
- Subscription aktivieren oder Billing Exception fuer Admin erzeugen.

### Phase 6: Frontend MVP

- Landing/Discovery als erste nutzbare Oberflaeche.
- Public Trader Dashboard mit Performance-Zeitraeumen.
- Trader Detail inkl. verzogener Trade History.
- User Dashboard, API-Key-Verwaltung, Subscribe Flow.
- Trader Dashboard und Admin Panel.
- Dark/Premium/Web3-Trading Design gemaess PDF.

### Phase 7: Hardening

- Backfill/Reconciliation nach Stream-Ausfall.
- Rate-Limit Scheduler und Exchange-spezifische Queues.
- Alerting fuer Stream Health, Copy Failures, Billing Exceptions.
- Backup-/Restore-Test.
- Security Review fuer Secrets, Logs und API-Key-Permissions.

## Offene Entscheidungen

- Chain und Stablecoin fuer V1-Billing.
- Konkretes Auth-Modell fuer User Login: Wallet-only, E-Mail plus Wallet oder Hybrid.
- Ob BloFin native Copy-Trading-Endpoints genutzt werden duerfen oder regulaere Trading-Endpoints vorzuziehen sind.
- Wo Exchange API-Credentials verschluesselt werden: DB field encryption, KMS/Vault oder Hetzner-kompatibler Secret Store.
- Ob alte Codebasis archiviert oder geloescht werden soll.
