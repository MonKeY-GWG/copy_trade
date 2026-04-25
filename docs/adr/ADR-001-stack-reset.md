# ADR-001: Neustart-Stack

Status: Vorgeschlagen
Datum: 2026-04-26

## Kontext

Das PDF definiert eine Copy-Trading-Plattform mit mehreren Exchanges, separater Copy Engine, Event-Verarbeitung, Auditierbarkeit, Billing und Admin/Ops. Der bestehende NestJS-Code bildet diese Zielarchitektur nicht sinnvoll ab und wird nicht als Basis uebernommen.

## Entscheidung

Wir bauen V1 neu mit:

- Next.js + TypeScript fuer das Frontend
- Python + FastAPI fuer die Backend API
- separaten Python-Workern fuer Copy Engine, Exchange Streams, Billing und Notifications
- PostgreSQL + Alembic fuer persistente Daten
- NATS JetStream fuer durable Events
- Redis fuer Cache, Locks und Rate-State
- Docker Compose fuer lokale und initiale Server-Deployments

## Verifizierte Grundlagen

- Das PDF nennt Python/FastAPI, PostgreSQL, Redis, NATS JetStream, WebSockets, Docker und Monitoring als empfohlene Zielarchitektur.
- Hyperliquid dokumentiert eine oeffentliche API mit Mainnet `https://api.hyperliquid.xyz` und Testnet `https://api.hyperliquid-testnet.xyz`.
- Aster empfiehlt V3 fuer neue Integrationen und markiert V1 fuer neue API Keys ab 2026-03-25 als nicht mehr unterstuetzt.
- BloFin dokumentiert REST und WebSocket APIs mit Production REST `https://openapi.blofin.com` und Demo REST `https://demo-trading-openapi.blofin.com`.

## Konsequenzen

- Keine Migration des bestehenden NestJS-Backends.
- Der API-Prozess darf keine Copy-Execution-Schleifen enthalten.
- Exchange-Anbindungen werden als Adapter isoliert.
- Entscheidungen mit Exchange-Risiko werden zuerst als Spike verifiziert.

## Risiken

- Mehr Infrastrukturkomponenten bedeuten hoeheren Ops-Aufwand.
- NATS/Redis/PostgreSQL muessen lokal und auf Hetzner sauber betreibbar sein.
- Python-Exchange-SDKs koennen unvollstaendig sein; Adapter muessen HTTP/WebSocket direkt koennen.
