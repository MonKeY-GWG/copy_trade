# Environment Verification

Stand: 2026-04-26

## Git

Verifiziert:

- Lokales Repository initialisiert.
- Branch: `main`.
- Lokaler Git-User: `MonKeY-GWG`.
- Lokale Git-Mail: `monkeygoesnft@gmail.com`.
- Remote: `https://github.com/MonKeY-GWG/copy_trade.git`.
- `git ls-remote origin` war erfolgreich und lieferte keine Refs zurueck. Das passt zu einem erreichbaren, leeren Repository.

## Legacy Archive

Verifiziert:

- Alte NestJS/Next.js/Prisma-Codebasis wurde nach `legacy/2026-04-26-pre-restart/` verschoben.
- `legacy/` ist in `.gitignore` eingetragen und wird nicht Teil des neuen Git-Standes.
- Das Produkt-PDF bleibt im Projektwurzelordner.

## Ruff

Verifiziert:

- `ruff` wurde per `python -m pip install --user ruff` installiert.
- `ruff` ist in `requirements.in` aufgenommen.
- `python -m ruff check apps\api workers\copy_engine packages\domain packages\exchange_adapters` laeuft erfolgreich.

## Tests

Verifiziert:

- `python -m pytest -p no:cacheprovider apps\api\tests workers\copy_engine\tests packages\domain\tests packages\exchange_adapters\tests` laeuft erfolgreich.
- Stand: 6 Tests, 6 passed.

## Docker

Verifiziert:

- `docker` ist aktuell nicht im PATH.
- Docker Desktop ist an den Standardpfaden nicht gefunden worden.
- Chocolatey ist vorhanden.
- Installation via `choco install docker-desktop -y --no-progress` wurde versucht.
- Ergebnis: fehlgeschlagen wegen fehlender Administratorrechte und gesperrtem/zugriffsgeschuetztem Chocolatey-Verzeichnis unter `C:\ProgramData\chocolatey`.

Naechster manueller Admin-Schritt:

```powershell
choco install docker-desktop -y --no-progress
```

Dieser Befehl muss in einer PowerShell ausgefuehrt werden, die mit "Als Administrator ausfuehren" gestartet wurde.

Nach erfolgreicher Installation pruefen:

```powershell
docker --version
docker compose version
docker compose -f infra\docker\docker-compose.yml --env-file infra\docker\.env.example config
```