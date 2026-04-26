# Environment Verification

Stand: 2026-04-26

## Git

Verifiziert:

- Lokales Repository initialisiert.
- Branch: `main`.
- Lokaler Git-User: `MonKeY-GWG`.
- Lokale Git-Mail: `monkeygoesnft@gmail.com`.
- Remote: `https://github.com/MonKeY-GWG/copy_trade.git`.
- Initial-Commit `a104875d4c1f5337a2bf23ef225e5bef6e84fdf4` wurde nach `origin/main` gepusht und per `git ls-remote origin refs/heads/main` verifiziert.

## Legacy Archive

Verifiziert:

- Alte NestJS/Next.js/Prisma-Codebasis wurde nach `legacy/2026-04-26-pre-restart/` verschoben.
- `legacy/` ist in `.gitignore` eingetragen und wird nicht Teil des neuen Git-Standes.
- Das Produkt-PDF bleibt im Projektwurzelordner.

## Ruff

Verifiziert:

- `ruff` wurde per `python -m pip install --user ruff` installiert. Verifizierte Version: `ruff 0.15.12`.
- `ruff` ist in `requirements.in` aufgenommen.
- `python -m ruff check apps\api workers\copy_engine packages\domain packages\exchange_adapters packages\shared_events` laeuft erfolgreich.

## Tests

Verifiziert:

- `python -m pytest -p no:cacheprovider` laeuft erfolgreich.
- Stand: 58 Tests, 58 passed.

## Docker

Verifiziert:

- Docker Desktop wurde per `winget install --id Docker.DockerDesktop --exact` installiert.
- Installierte Docker Desktop Version: `4.70.0`.
- Docker CLI ist vorhanden unter `C:\Program Files\Docker\Docker\resources\bin\docker.exe`.
- `docker --version` meldet `Docker version 29.4.0`.
- `docker compose version` meldet `Docker Compose version v5.1.2`.
- `docker compose -f infra\docker\docker-compose.yml --env-file infra\docker\.env.example config` validiert die lokale Compose-Konfiguration erfolgreich.
- `com.docker.service` ist installiert und konnte als Administrator gestartet werden.

Docker Runtime nach Neustart:

- Keine offenen Docker-Basisblocker nach Neustart.
- Docker Engine ist erreichbar.
- `docker info --format '{{.ServerVersion}} {{.OperatingSystem}} {{.NCPU}}'` meldet `29.4.0 Docker Desktop 32`.
- Der lokale Compose-Stack wurde mit `docker compose -f infra\docker\docker-compose.yml --env-file infra\docker\.env.example up --build -d` erfolgreich gestartet.
- Containerstatus:
  - `api`: running, Port `8000`
  - `copy_engine`: running
  - `nats`: running, healthy, Ports `4222` und `8222`
  - `postgres`: running, healthy, Port `5432`
  - `redis`: running, healthy, Port `6379`
- API-Smoke-Test im Docker-Stack erfolgreich:
  - `/health` gibt `{"status":"ok","service":"copy-trade-api"}` zurueck
  - `/ready` gibt `{"status":"ready","dependencies":{"postgres":"ok","redis":"ok","nats":"ok"}}` zurueck
  - `/version` gibt `{"version":"0.1.0","env":"local"}` zurueck
- Admin Copy-Relationship API-Smoke-Test im Docker-Stack erfolgreich:
  - Alembic steht auf `20260426_0006 (head)`
  - `POST /admin/copy-relationships` mit lokalem Admin-Token erzeugte eine Test-Beziehung
  - `GET /admin/copy-relationships?active=true&source_account_id=...` gab die Test-Beziehung zurueck
  - `PATCH /admin/copy-relationships/{id}` konnte die Test-Beziehung deaktivieren
  - `GET /admin/audit-logs?entity_type=copy_relationship&entity_id=...` gab zwei Audit-Events zurueck
  - Audit-Response enthielt den lokalen Admin-Token nicht
  - Smoke-Datensaetze wurden nach der Verifikation aus `audit_logs` und `copy_relationships` entfernt
- DB-gestuetzter Admin-Auth-Smoke-Test im Docker-Stack erfolgreich:
  - Test-User mit Rolle `admin` angelegt
  - Admin-API-Credential nur als SHA-256-Hash in `api_credentials` gespeichert
  - `POST /admin/copy-relationships` mit DB-Token erfolgreich
  - `PATCH /admin/copy-relationships/{id}` mit DB-Token erfolgreich
  - `GET /admin/audit-logs` gab zwei Audit-Events mit `actor_type=user` und passender `actor_id` zurueck
  - Smoke-Datensaetze wurden aus `audit_logs`, `copy_relationships`, `api_credentials`, `user_roles` und `users` entfernt
- NATS-Healthcheck ueber `http://127.0.0.1:8222/healthz` gibt `{"status":"ok"}` zurueck.
- JetStream-Smoke-Test erfolgreich:
  - Test-Event auf `exchange.trade_event.normalized` publiziert
  - Copy Engine hat das Event ueber durable Consumer `copy_engine_normalized_trades` empfangen
  - Copy Engine hat das Event verarbeitet und Verarbeitungszaehler geloggt
  - Im ersten Smoke-Test ohne Copy-Beziehung wurden erwartungsgemaess `requests=0` erzeugt
  - Copy Engine loggt keine Raw-Payloads und keine Account-IDs
- DB-gestuetzter Copy-Engine-Smoke-Test erfolgreich:
  - Alembic steht auf `20260426_0006 (head)`
  - Test-Relationship in PostgreSQL erzeugt
  - Test-Event auf `exchange.trade_event.normalized` publiziert
  - Copy Engine hat `requests=1`, `duplicates=0`, `inactive=0`, `before_follow_start=0` geloggt
  - `copy_execution_requests` enthielt den erzeugten Dry-Run-Request
  - `copy_execution_idempotency` enthielt die reservierte Idempotency
  - Request wurde nach erfolgreichem Publish auf `PUBLISHED` gesetzt
  - Test-Result auf `copy.execution.filled` publiziert
  - `copy_execution_results` enthielt das Result
  - Request wurde nach Result-Verarbeitung auf `FILLED` gesetzt
  - Smoke-Datensaetze wurden nach der Verifikation aus `copy_relationships`, `copy_execution_idempotency`, `copy_execution_requests` und `copy_execution_results` entfernt
- Retry-/DLQ-Smoke-Test erfolgreich:
  - `COPY_TRADE_EVENTS` enthaelt `system.dead_letter.created`
  - Copy-Engine-Durable-Consumer stehen auf `max_deliver=3` und `ack_wait=30.0`
  - Isolierter Smoke-Consumer mit `max_deliver=2` erzeugte nach finalem Fehler ein Dead-Letter-Event
  - Dead-Letter-Event enthielt `failed_subject=exchange.order_update.normalized`, `delivery_attempt=2`, `max_delivery_attempts=2`, `error_type=RuntimeError`
  - Smoke-Durable-Consumer wurden nach dem Test entfernt

Behobene Docker-Startprobleme:

- Das urspruengliche NATS-Image `nats:2.10` enthielt keine `/bin/sh`; dadurch schlug der `CMD-SHELL` Healthcheck fehl.
- `infra/docker/docker-compose.yml` nutzt fuer NATS jetzt `nats:2.10-alpine`, damit der bestehende HTTP-Healthcheck im Container ausfuehrbar ist.
- Der Copy-Engine-Skeleton bleibt jetzt als laufender Worker-Prozess aktiv, statt nach dem Start-Log direkt mit Exitcode 0 zu enden.
- Der erste nats-py Subscribe-Smoke zeigte, dass Subscription-Callbacks echte `async def` Callbacks sein muessen. Der Event-Bus-Wrapper erzeugt jetzt eine async Callback-Funktion.

Historische Diagnose vor dem erfolgreichen Neustart:

- Docker Desktop zeigte vor dem Neustart `Virtualization support not detected`.
- Hardwarepruefung:
  - CPU: `Intel(R) Core(TM) i9-14900K`
  - Mainboard/Systemmodell: `Gigabyte Technology Co., Ltd. Z790 AORUS MASTER`
  - `VirtualizationFirmwareEnabled: False`
  - `SecondLevelAddressTranslationExtensions: False`
  - `VMMonitorModeExtensions: False`

Nach dem Neustart pruefen:

```powershell
docker --version
docker compose version
docker info
docker compose -f infra\docker\docker-compose.yml --env-file infra\docker\.env.example config
```

## Rebuild-Pruefung nach PC-Neuaufsetzung

Stand: 2026-04-26

Verifiziert:

- Workspace liegt aktuell unter `D:\VSC_Projekte\Copy_Trade`.
- Git for Windows ist installiert: `D:\Git\cmd\git.exe`.
- `git --version` meldet `git version 2.54.0.windows.1`.
- Python 3.11.9 ist systemweit fuer den Benutzer verfuegbar.
- `python --version` meldet `Python 3.11.9`.
- `py --version` meldet `Python 3.11.9`.
- PowerShell `CurrentUser` ExecutionPolicy ist `RemoteSigned`, damit `npm.ps1` nutzbar ist.
- Node.js LTS wurde per Winget installiert.
- `node --version` meldet `v24.15.0`.
- `npm --version` meldet `11.12.1`.
- Docker Desktop wurde installiert, Docker CLI und Compose sind verfuegbar.
- Der Benutzer-PATH wurde fuer Python, Git, Node und Docker aktualisiert. Neue Terminals/VS Code-Fenster muessen ggf. neu gestartet werden.
- `.venv\Scripts\python.exe` funktioniert mit Python 3.11.9.
- `pip` fehlte in der vorhandenen venv und wurde mit `ensurepip` wiederhergestellt.
- `pip install -r requirements.in` wurde nach Netzwerkfreigabe erfolgreich ausgefuehrt.
- `pip check` meldet keine defekten Abhaengigkeiten.
- `pytest -p no:cacheprovider` laeuft mit 58 Tests erfolgreich.
- `ruff check apps\api workers\copy_engine packages\domain packages\exchange_adapters packages\shared_events` laeuft erfolgreich.
- API-Smoke-Test ueber Uvicorn erfolgreich:
  - `/health` gibt `{"status":"ok","service":"copy-trade-api"}` zurueck
  - `/ready` gibt `{"status":"ready","dependencies":{"postgres":"ok","redis":"ok","nats":"ok"}}` zurueck
  - `/version` gibt `{"version":"0.1.0","env":"local"}` zurueck
- Lokale Tests laufen ueber `.venv\Scripts\python.exe`.
- Ruff laeuft ueber `.venv\Scripts\ruff.exe`.

OFFEN:

- OFFEN: UI-Verwaltung, Login-/Sessionfluss und Credential-Rotation fuer Copy-Relationships fehlen noch.
- OFFEN: DLQ-Reprocessing und Alerting fehlen noch.
- OFFEN: Echte Exchange-Order-Ausfuehrung ist nicht angeschlossen.
