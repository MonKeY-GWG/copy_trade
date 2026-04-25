# Exchange API Research Log

Stand: 2026-04-26
Zweck: Verifizierte technische Stichpunkte fuer Adapter-Spikes. Keine Implementierungsdetails ohne erneute Pruefung uebernehmen.

## Hyperliquid

Quelle: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api

Verifiziert:

- Offizielle API-Dokumentation verweist auf Python SDK.
- Beispiel-Calls verwenden Mainnet `https://api.hyperliquid.xyz` und Testnet `https://api.hyperliquid-testnet.xyz`.
- Dokumentationsbereiche umfassen Info endpoint, Exchange endpoint, WebSocket, Signing, Rate limits und User limits.

Adapter-Fokus:

- API wallet signing pruefen.
- Private trader events ueber WebSocket verifizieren.
- User-spezifische Subscription Limits fuer Streamer-Sharding beachten.
- Reconciliation ueber Info endpoints planen.

## Aster

Quelle: https://github.com/asterdex/api-docs/blob/master/README.md
Quelle V3 Futures: https://github.com/asterdex/api-docs/blob/master/V3%28Recommended%29/EN/aster-finance-futures-api-v3.md

Verifiziert:

- Aster empfiehlt V3 fuer neue Integrationen.
- Neue V1 API-Key-Erstellung wird ab 2026-03-25 nicht mehr unterstuetzt.
- V3 Futures dokumentiert `https://fapi.asterdex.com` als base endpoint; Beispiele verwenden auch `https://fapi3.asterdex.com`.
- Signierte Requests nutzen `user`, `signer`, `nonce` in Mikrosekunden und `signature`.
- Fuer 503 muss der Ausfuehrungsstatus als unbekannt behandelt und nachrecherchiert werden.

Adapter-Fokus:

- Endpoint-Konfiguration als Umgebungseinstellung halten.
- Nonce-Generator thread-safe und monoton genug bauen.
- Unknown execution status nach 503 ueber Query/Reconciliation aufloesen.
- User Data Stream auf Reihenfolge und Idempotenz testen.

## BloFin

Quelle: https://docs.blofin.com/index.html#overview

Verifiziert:

- Production REST: `https://openapi.blofin.com`.
- Demo REST: `https://demo-trading-openapi.blofin.com`.
- Private WebSocket: `wss://openapi.blofin.com/ws/private`.
- Demo Private WebSocket: `wss://demo-trading-openapi.blofin.com/ws/private`.
- Private REST Requests nutzen `ACCESS-KEY`, `ACCESS-SIGN`, `ACCESS-TIMESTAMP`, `ACCESS-NONCE` und `ACCESS-PASSPHRASE`.
- API-Key-Rechte: READ, TRADE, TRANSFER. TRANSFER darf fuer Copy Trading nicht zugelassen werden.
- Nicht IP-gebundene API Keys laufen laut Doku nach 90 Tagen ab.
- Trading REST bietet u.a. Positions, Leverage, Place Order, Place TPSL Order, Cancel und Order History.
- BloFin dokumentiert zusaetzlich native Copy-Trading-Bereiche.

Adapter-Fokus:

- API-Key-Permission-Check implementieren: READ+TRADE erlaubt, TRANSFER ablehnen.
- IP-Bindung in UX/Security sichtbar machen.
- Klaeren, ob regulaere Trading-Endpoints oder native Copy-Trading-Endpoints fuer unser Produktmodell korrekt sind.
- Demo Trading fuer sichere Integrationstests nutzen.
