# Foundation Runbook

Stand: 2026-04-27

## Lokaler Start

```powershell
cd D:\VSC_Projekte\Copy_Trade
docker compose -f infra\docker\docker-compose.yml --env-file infra\docker\.env.example up --build
```

API danach lokal:

- `http://localhost:8000/health`
- `http://localhost:8000/ready`
- `http://localhost:8000/version`

## Lokale Python-Tests

```powershell
cd D:\VSC_Projekte\Copy_Trade
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r requirements.in
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\ruff.exe check apps\api workers\copy_engine packages\domain packages\exchange_adapters packages\shared_events infra\migrations
```

## Datenbank-Migrationen

PostgreSQL muss ueber Docker Compose laufen. Danach:

```powershell
cd D:\VSC_Projekte\Copy_Trade
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

## Admin Copy-Relationship API

Die Admin-API ist ueber den Header `X-Copy-Trade-Admin-Token` geschuetzt.

Authentifizierung:

- Primaer: DB-gestuetzte Admin-Credentials in `api_credentials`.
- Tokens werden nicht im Klartext gespeichert, sondern als SHA-256-Hash.
- DB-Admin-Tokens muessen mindestens 32 Zeichen lang sein.
- Ein Credential ist nur gueltig, wenn `api_credentials.active=true`, der User `active` ist und die Rolle `admin` besitzt.
- Der lokale Env-Token `COPY_TRADE_ADMIN_API_TOKEN` aus `infra/docker/.env.example` ist nur ein Bootstrap-Fallback, wenn `COPY_TRADE_ALLOW_ENV_ADMIN_TOKEN=true` gesetzt ist und `COPY_TRADE_ENV` auf `local`/`test`/`dev` steht. Das ist kein Produktivpfad.

Bei DB-Auth schreibt die API Audit-Logs mit `actor_type=user` und `actor_id=<user_id>`. Beim lokalen Env-Fallback bleibt der Actor `admin_api`.

Verfuegbare Foundation-Endpunkte:

- `POST /admin/identity/admin-credentials`
- `GET /admin/identity/admin-credentials`
- `POST /admin/identity/admin-credentials/{credential_id}/deactivate`
- `POST /admin/identity/admin-credentials/{credential_id}/rotate`
- `PUT /admin/identity/users/{user_id}/subscription`
- `GET /admin/identity/subscriptions`
- `POST /admin/exchange-accounts`
- `GET /admin/exchange-accounts`
- `PATCH /admin/exchange-accounts/{account_id}`
- `POST /admin/copy-relationships`
- `GET /admin/copy-relationships`
- `PATCH /admin/copy-relationships/{relationship_id}`
- `PUT /admin/copy-relationships/{relationship_id}/risk-settings`
- `GET /admin/copy-relationships/{relationship_id}/risk-settings`
- `GET /admin/audit-logs`
- `GET /admin/operations/dead-letter-events`

Admin-Credential-Erzeugung gibt den Klartext-Token nur einmal in der Create- oder Rotate-Response zurueck. Listen-, Deactivate-, Rotate- und Audit-Responses enthalten keinen Token-Hash und keinen Klartext-Token.
Rotation schreibt Audit-Events fuer das alte deaktivierte Credential und das neu erzeugte Credential, damit beide Credential-IDs forensisch auffindbar bleiben.
Exchange-Account-Responses enthalten nur `has_secret` und `secret_fingerprint_prefix`; vollstaendige Secret-Referenzen, Fingerprints und Exchange-Secrets werden nicht ausgegeben.
Die Copy Engine erzeugt Copy-Execution-Requests nur, wenn Relationship, Exchange-Accounts, User, Subscription und Risk Settings aktiv beziehungsweise gueltig sind.

Es gibt bewusst kein `DELETE`. Beziehungen werden deaktiviert, damit Verlauf und Auditierbarkeit erhalten bleiben.
Create- und Patch-Aktionen fuer Copy-Relationships schreiben transaktionale Audit-Logs ohne Admin-Token oder Request-Header.

## Wiederaufbau nach PC-Neuaufsetzung

Wenn Windows nach einer Neuinstallation den `python`-Befehl auf den Microsoft-Store-Alias legt, die Projekt-venv direkt verwenden oder Python 3.11 neu installieren.

Pruefen:

```powershell
Get-Command git -ErrorAction SilentlyContinue
Get-Command docker -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
```

Wenn `pip` in der vorhandenen venv fehlt:

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r requirements.in
```

## Was bewusst noch nicht produktiv ist

- Es gibt noch keine echten Exchange-Adapter.
- Die Copy Engine erzeugt nur Dry-Run-`CopyExecutionRequest`s.
- Es gibt noch keine echte Exchange-Order-Ausfuehrung.
- Copy-Relationship-Verwaltung existiert als Admin-API, aber noch nicht ueber UI.
- Identity-Foundation mit Users/Roles/API-Credentials existiert, aber noch ohne Login, Session, JWT, Passwortfluss oder UI-Verwaltung.
- Admin-Credentials koennen per Admin-API erzeugt, gelistet, deaktiviert und rotiert werden.
- Subscription-, Exchange-Account- und Risk-Gates existieren als Foundation-Controls.
- Dead-Letter-Events werden in PostgreSQL gespeichert und koennen administrativ gelistet werden.
- GitHub Actions CI prueft Ruff, Pytest, Alembic-Heads und einfache Secret-Pattern.
- Admin-Aenderungen an Copy-Relationships werden auditierbar gespeichert.
- Execution-Requests und Execution-Results werden persistiert.
- Result-Events koennen Request-Status auf `ACCEPTED`, `REJECTED`, `FILLED` oder `FAILED` setzen.
- NATS-Consumer haben begrenzte Retry-Zustellung und schreiben nach finalem Fehler auf `system.dead_letter.created`.
- DLQ-Reprocessing und Alerting sind noch nicht implementiert.
- Echte Secret-Verschluesselung beziehungsweise Secret-Manager-Integration ist noch nicht implementiert; aktuell wird nur eine Secret-Referenz gespeichert.
- OFFEN: Das Admin-Rate-Limit ist aktuell ein In-Memory-Limit pro API-Prozess. Vor Betrieb mit mehreren API-Instanzen muss der Rate-Limit-State zentralisiert werden, z. B. ueber Redis oder ein Gateway.
- Die konkreten Implementierungsplaene fuer diese offenen Punkte stehen in `docs/restart/05_open_implementation_plans.md`.

## Verifikationspflicht vor echter Order-Ausfuehrung

Vor jeder echten Exchange-Order muessen erneut geprueft werden:

- offizielle Exchange-Doku
- Test-/Demo-Account Verhalten
- Rate Limits
- Idempotency und Client Order IDs
- Min Notional, Lot Size, Tick Size
- Slippage und Leverage-Semantik
