# ADR-002: Event-getriebene Copy-Architektur

Status: Vorgeschlagen
Datum: 2026-04-26

## Kontext

Copy Trading darf nicht vom API-Prozess, Frontend-Requests oder einzelnen WebSocket-Verbindungen abhaengen. Trade Events muessen nachvollziehbar, idempotent und wiederholbar verarbeitet werden.

## Entscheidung

Die Plattform nutzt eine event-getriebene Architektur mit NATS JetStream. Exchange Streamer normalisieren Trader-Orders/Fills und publizieren Events. Die Copy Engine konsumiert diese Events, berechnet pro Follower die Zielorder und schreibt Ergebnis oder Failure dauerhaft in PostgreSQL.

## Event Flow

1. Exchange Streamer beobachtet Trader-Account.
2. Streamer normalisiert Order/Fills in ein kanonisches Event.
3. Event wird durable auf NATS JetStream publiziert.
4. Copy Engine laedt aktive Copy Relationships mit `effective_from <= event_time`.
5. Engine prueft Symbol, Exchange, Sizing, Leverage, Slippage und Overrides.
6. Execution Request geht an den Adapter.
7. Resultat wird als copied trade, failure und audit log gespeichert.
8. Notification Worker informiert Follower/Trader/Admin nach Regeln.

## Idempotenz

Jedes Exchange Event und jede Copy Execution bekommt einen stabilen `idempotency_key`. Wiederholte Zustellung darf keine doppelte Order erzeugen.

## Fail-safe Verhalten

Wenn eine Aktion nicht sicher gespiegelt werden kann, wird sie abgelehnt, persistiert und gemeldet. Beispiele:

- insufficient margin
- asset unavailable
- min notional/lot size fail
- slippage exceeded
- unsupported feature
- exchange/API error
- stale event
- duplicate event

## Konsequenzen

- UI und API bleiben reaktionsfaehig, auch wenn Exchanges langsam sind.
- Fehler werden operational sichtbar statt still verschluckt.
- Reconciliation und Backfill koennen spaeter sauber ergaenzt werden.
