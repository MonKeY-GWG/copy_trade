# Offene Implementierungsplaene

Stand: 2026-04-27

Diese Datei konkretisiert die zentralen `OFFEN`-Punkte aus `docs/restart/04_environment_verification.md`.
Die Reihenfolge entspricht der aktuellen Prioritaet von oben nach unten.

## 1. UI-Verwaltung und Login-/Sessionfluss

### Ziel

Eine echte Verwaltungsoberflaeche schaffen, die nicht mehr direkt mit Bootstrap-Admin-Token bedient werden muss.
Die UI soll Foundation-Controls nutzbar machen, ohne Security-Regeln aufzuweichen.

### Vorschlag fuer Architektur

- Frontend als Next.js/TypeScript-App unter `apps/web`.
- API bleibt FastAPI unter `apps/api`.
- Browser-Auth ueber sichere `HttpOnly` Session-Cookies.
- DB-gestuetzte Sessions statt reiner LocalStorage/JWT-Token im Browser.
- Kurzlebige Session mit Rotation und explizitem Logout.
- Admin-API-Token bleiben fuer Maschinen-/Bootstrap-Admin-Zugriff erhalten, werden aber nicht als normaler UI-Login missbraucht.

### Backend-Schritte

1. Migration fuer Login-Fundament anlegen:
   - `password_credentials`
   - `user_sessions`
   - optional `password_reset_tokens`
   - Indizes fuer `user_id`, `session_token_hash`, `expires_at`
2. Password-Hashing einfuehren:
   - Argon2id bevorzugt, bcrypt als akzeptable Alternative
   - keine Plaintext-Passwoerter speichern oder loggen
3. Auth-Endpunkte ergaenzen:
   - `POST /auth/login`
   - `POST /auth/logout`
   - `GET /auth/session`
   - optional `POST /auth/change-password`
4. Admin-Dependency erweitern:
   - bestehende DB-Admin-Credentials behalten
   - zusaetzlich Session-Cookie-Principals akzeptieren
   - Rollen weiterhin aus DB lesen
5. Schutzmechanismen:
   - Login-Rate-Limit
   - Audit-Log fuer erfolgreiche Logins, Logouts und fehlgeschlagene Login-Versuche
   - CSRF-Schutz fuer Cookie-basierte Mutationen
   - SameSite/secure Cookie-Konfiguration je Umgebung

### UI-Schritte

1. App-Shell erstellen:
   - Login-Screen
   - geschuetztes Admin-Layout
   - Navigation fuer Foundation-Controls
2. Seiten in dieser Reihenfolge:
   - Dashboard/Systemstatus
   - Admin-Credentials
   - Users/Roles
   - Subscriptions
   - Exchange-Accounts
   - Copy-Relationships
   - Risk Settings
   - DLQ-Events
   - Audit Logs
3. API-Client mit typisierten Contracts erstellen.
4. Fehler- und Ladezustaende konsequent bauen:
   - 401/403
   - Rate Limit
   - Validation Errors
   - Backend unavailable

### Akzeptanzkriterien

- UI kann ohne manuelles Header-Token Foundation-Controls bedienen.
- Login erzeugt keine Tokens im LocalStorage.
- Logout invalidiert die Session serverseitig.
- Alle mutierenden UI-Aktionen werden auditiert.
- Unauthorized und Forbidden sind fuer User klar unterscheidbar.
- Tests decken Login, Logout, Session-Refresh, Rollenpruefung und CSRF/Rate-Limit-Basics ab.

### Verifikation

- Backend: Pytest fuer Auth-Repository, API-Routen und Session-Ablauf.
- Frontend: TypeScript-Check, Lint, Komponenten-/API-Client-Tests.
- E2E: Login, Navigation, Create/Update von Foundation-Controls, Logout.

## 2. DLQ-Reprocessing, Alerting und Retention

### Ziel

Dead-Letter-Events duerfen nicht nur sichtbar sein. Operatoren muessen sie triagieren, erneut verarbeiten, ignorieren und ueber kritische Haeufungen informiert werden koennen.

### Backend-Schritte

1. DLQ-Datenmodell erweitern:
   - `status` bleibt: `open`, `acknowledged`, `reprocessed`, `ignored`
   - `resolved_at`
   - `resolved_by`
   - `resolution_note`
   - `reprocess_attempts`
   - `last_reprocess_error`
   - optional `locked_until` und `locked_by` fuer parallele Operatoren/Worker
2. API-Endpunkte ergaenzen:
   - `POST /admin/operations/dead-letter-events/{id}/acknowledge`
   - `POST /admin/operations/dead-letter-events/{id}/ignore`
   - `POST /admin/operations/dead-letter-events/{id}/reprocess`
3. Reprocessing-Service bauen:
   - Original-Subject aus `failed_subject` lesen
   - redigierte Payload nur reprocessen, wenn sie technisch vollstaendig ist
   - sonst Status mit `last_reprocess_error` aktualisieren
   - neues Idempotency-Key-Schema fuer Replays verwenden, z. B. `replay:<dlq_id>:<attempt>`
4. Audit-Logs fuer alle DLQ-Aktionen schreiben.
5. Retention/Purge-Policy definieren:
   - offene DLQ-Events nicht automatisch loeschen
   - resolved Events nach definierter Frist archivierbar oder purgebar machen

### Alerting-Schritte

1. Metriken definieren:
   - offene DLQ-Events gesamt
   - DLQ-Events pro Subject
   - DLQ-Events pro Zeitfenster
   - Reprocess-Erfolge/Fehler
2. Health-/Operations-Signal definieren:
   - `/ready` bleibt Infrastrukturstatus
   - separater Operations-Endpunkt fuer DLQ-Warnlevel
3. Erste lokale Alerting-Stufe:
   - strukturierte Logs mit `warning` bei neuen DLQ-Events
   - spaeter Prometheus/Grafana oder externer Alertmanager

### Akzeptanzkriterien

- Operator kann DLQ-Event ack/ignore/reprocess aus API und spaeter UI ausloesen.
- Jede Aktion ist auditiert.
- Reprocessing ist idempotent.
- Failed Reprocessing erzeugt keine Endlosschleife.
- Retention/Purge-Regeln sind dokumentiert und testbar.

### Verifikation

- Unit-Tests fuer Statusuebergaenge.
- Integrationstest fuer Reprocess-Publish auf NATS.
- Test fuer paralleles Reprocessing desselben DLQ-Events.
- Test fuer Audit-Events und redigierte Payload-Ausgabe.

## 3. Echte Secret-Manager-Integration fuer Exchange-Secrets

### Ziel

Exchange-Secrets duerfen nicht in der Datenbank liegen und nicht in Logs, Audits oder DLQ-Payloads auftauchen.
Die DB speichert weiterhin nur Referenz und Fingerprint.

### Zielarchitektur

- `exchange_accounts.secret_reference` zeigt auf einen Secret-Manager-Pfad.
- `exchange_accounts.secret_fingerprint` dient nur zur Erkennung/Rotation, nicht zur Rekonstruktion.
- Exchange-Adapter bekommen Secrets nur zur Laufzeit ueber einen `SecretProvider`.
- Lokale Entwicklung nutzt einen klar markierten Dev-Provider, Produktion einen echten Secret Manager.

### Implementierungsschritte

1. Secret-Provider-Interface definieren:
   - `get_exchange_secret(reference) -> ExchangeSecret`
   - `put_exchange_secret(...) -> SecretMetadata`
   - `rotate_exchange_secret(...) -> SecretMetadata`
   - `delete_exchange_secret(reference)` nur mit strengen Regeln
2. Provider implementieren:
   - Dev: lokale verschluesselte Datei oder Docker-Secret-Stub
   - Prod-Ziel: z. B. Hetzner-kompatibler Secret Store, Vault, 1Password Connect oder Cloud-KMS-kompatibler Dienst
3. API-Flows anpassen:
   - Exchange-Account-Create nimmt Secret-Payload optional entgegen, speichert sie aber nur im Secret Provider
   - Response bleibt bei `has_secret` und Fingerprint-Prefix
   - Audit speichert keine Secret-Payload
4. Rotation-Workflow bauen:
   - neues Secret speichern
   - Fingerprint aktualisieren
   - altes Secret deaktivieren oder versionieren
   - Audit-Log fuer Rotation
5. Worker/Adapter anbinden:
   - Copy Engine loest `secret_reference` erst unmittelbar vor Exchange-Zugriff auf
   - Secret nie in Event-Payloads schreiben

### Akzeptanzkriterien

- Keine Secret-Payload in PostgreSQL.
- Keine Secret-Payload in Logs/Audit/DLQ.
- Rotation ist nachvollziehbar und bricht aktive Accounts kontrolliert ab, wenn Secret fehlt.
- Tests beweisen, dass API-Responses und Audit-Logs redigiert bleiben.

### Verifikation

- Secret-Pattern-Scan in CI.
- Unit-Tests fuer Provider-Interface und Redaction.
- Integrationstest mit Dev-Provider.
- Negativtest: fehlendes Secret blockiert echte Execution sicher.

## 4. Echte Exchange-Order-Ausfuehrung

### Ziel

Dry-Run-Requests kontrolliert in echte Exchange-Orders ueberfuehren, ohne doppelte Orders, falsche Groessen, falschen Hebel oder nicht nachvollziehbare Status zu riskieren.

### Vorbedingungen

- Secret-Manager-Integration fertig.
- Exchange-Adapter-Vertraege fuer Ziel-Exchanges implementiert.
- Demo-/Test-Account-Verhalten je Exchange dokumentiert.
- Permission-Checks fuer API-Keys vorhanden.
- Kill-Switch fuer echte Execution vorhanden.

### Implementierungsschritte

1. Execution Mode einfuehren:
   - `dry_run`
   - `paper`
   - `live`
   - globaler Kill-Switch per Env und DB-Setting
2. Order Planner bauen:
   - Symbol-Mapping
   - Quantity-Mapping
   - Min Notional/Lot Size/Tick Size
   - Slippage-Grenzen
   - Leverage-Regeln
   - Reduce-only/Position-Side-Semantik
3. Exchange Adapter pro Exchange implementieren:
   - Auth
   - Place Order
   - Cancel Order
   - Get Order Status
   - Account/Balance/Position Checks
   - Rate-Limit-Handling
4. Execution Worker erweitern:
   - Request `PUBLISHED` wird zu `SUBMITTED`
   - Exchange-Order-ID persistieren
   - Result-Events aus Adapter-Antworten publizieren
   - Unknown Status in Reconciliation ueberfuehren
5. Reconciliation bauen:
   - offene Orders periodisch pruefen
   - unklare 503/Timeout-Faelle nachziehen
   - finalen Status in `copy_execution_results` schreiben
6. Safety Gates vor jeder Order:
   - Subscription aktiv
   - Exchange Account aktiv
   - Secret vorhanden
   - Risk Settings aktiv
   - Balance/Position plausibel
   - Idempotency-Key noch nicht final ausgefuehrt

### Akzeptanzkriterien

- Live-Execution kann nur explizit aktiviert werden.
- Jede echte Order hat eine persistierte Exchange-Order-ID oder einen nachvollziehbaren Fehlerstatus.
- Doppelte Events fuehren nicht zu doppelten Orders.
- Unknown Execution Status wird reconciliation-pflichtig, nicht ignoriert.
- Tests decken Adapter-Fehler, Timeouts, Rate Limits, Dedupe und Risk-Gates ab.

### Verifikation

- Unit-Tests fuer Order Planner.
- Adapter-Contract-Tests mit Fake-Exchange.
- Demo-Account-Smokes je Exchange.
- Reconciliation-Test fuer Timeout/Unknown-Status.
- Manuelle Freigabe vor erster Live-Order.

## 5. Zentrales Rate-Limit fuer mehrere API-Instanzen

### Ziel

Das aktuelle In-Memory-Rate-Limit schuetzt lokale und Single-Process-Setups.
Bei mehreren API-Instanzen muss der Rate-Limit-State zentral geteilt werden.

### Implementierungsschritte

1. Rate-Limiter-Interface einfuehren:
   - `allow(key, limit, window) -> RateLimitDecision`
   - Implementierungen: `InMemoryRateLimiter`, `RedisRateLimiter`
2. Redis-Backend bauen:
   - atomare Counter per Lua-Script oder Redis-Transaktion
   - TTL pro Window
   - Key-Schema: `rate-limit:<scope>:<client-or-principal>`
3. Scope feinziehen:
   - `/auth/login`: streng nach IP und E-Mail
   - `/admin/*`: nach Principal und IP
   - optional Exchange-Adapter: separat nach Exchange/API-Key
4. Konfiguration erweitern:
   - `COPY_TRADE_RATE_LIMIT_BACKEND=memory|redis`
   - `COPY_TRADE_RATE_LIMIT_REDIS_URL`
   - Limits je Scope
5. Fallback-Regeln definieren:
   - bei Redis-Ausfall fuer Admin-Routen lieber fail-closed oder stark reduziertes Local-Limit
   - Entscheidung dokumentieren

### Akzeptanzkriterien

- Zwei API-Prozesse teilen dasselbe Rate-Limit.
- Login-Bruteforce wird instanzuebergreifend gebremst.
- `Retry-After` bleibt korrekt.
- Redis-Ausfall ist eindeutig getestet und dokumentiert.

### Verifikation

- Unit-Tests fuer Redis-Rate-Limiter mit Fake/Container.
- Integrationstest mit zwei App-Instanzen gegen denselben Redis.
- Smoke-Test fuer 429 und Window-Reset.

## Dokumentations- und Umsetzungsreihenfolge

1. UI/Login planen und bauen, weil es die Bedienung aller Foundation-Controls erleichtert.
2. DLQ-Operations bauen, damit Fehler nicht nur sichtbar, sondern bearbeitbar sind.
3. Secret Manager anschliessen, bevor echte Exchange-Execution moeglich wird.
4. Echte Exchange-Execution nur hinter Kill-Switch, Adapter-Tests und Reconciliation aktivieren.
5. Zentrales Rate-Limit spaetestens vor Multi-Instance-Betrieb umsetzen.

## Querschnittliche Tests vor Abschluss jedes Blocks

- `.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider`
- `.\.venv\Scripts\ruff.exe check apps\api workers\copy_engine packages\domain packages\exchange_adapters packages\shared_events infra\migrations`
- `.\.venv\Scripts\python.exe -m compileall -q apps workers packages`
- Docker-Smoke fuer betroffene Services
- Session-Notiz in `docs/sessions/`
