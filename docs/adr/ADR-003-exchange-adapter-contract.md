# ADR-003: Exchange Adapter Contract

Status: Vorgeschlagen
Datum: 2026-04-26

## Kontext

Hyperliquid, Aster und BloFin haben unterschiedliche Authentifizierung, Ordermodelle, WebSocket-Streams, Rate Limits und Symbolformate. Die Copy Engine darf diese Unterschiede nicht direkt kennen.

## Entscheidung

Alle Exchange-spezifischen Details liegen in Adaptern. Die Copy Engine arbeitet nur gegen kanonische Domain-Objekte und Adapter-Interfaces.

## Pflichtmethoden

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

## Kanonische Order-Felder

- exchange
- account_id
- symbol
- base_asset
- quote_asset
- market_type = `PERP`
- side = `BUY` oder `SELL`
- position_side = `LONG`, `SHORT` oder exchange-spezifisch normalisiert
- order_type = `MARKET`, `LIMIT`, `STOP`, `TAKE_PROFIT`, `TRAILING_STOP`
- quantity
- price
- trigger_price
- reduce_only
- post_only
- time_in_force
- leverage
- client_order_id

## Feature-Regel

Adapter duerfen keine riskanten Approximationen verstecken. Wenn ein Exchange eine Funktion nicht unterstuetzt oder nur anders semantisch anbietet, gibt der Adapter `UNSUPPORTED_FEATURE` mit Detailgrund zurueck.

## Exchange-spezifische verifizierte Hinweise

- Hyperliquid bietet Info-, Exchange- und WebSocket-Bereiche; Beispiele verwenden Mainnet und Testnet URLs.
- Aster V3 nutzt einen microsecond nonce, API wallet/signer und signierte TRADE/USER_DATA/USER_STREAM Requests.
- BloFin private REST Requests erfordern Key, Signatur, Timestamp, Nonce und Passphrase. API Keys koennen READ, TRADE und TRANSFER Rechte haben; TRANSFER ist fuer unsere Plattform nicht erlaubt.

## Spike-Aufgaben

- Hyperliquid: userFills/order updates, API wallet signing, user subscription limits, leverage/order behavior.
- Aster: V3 signer setup, listenKey/User Data Stream, order update ordering, demo/testnet behavior.
- BloFin: private WS order/position channels, demo trading, native copy trading vs regular trading endpoint Entscheidung.
