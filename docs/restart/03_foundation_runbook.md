# Foundation Runbook

Stand: 2026-04-26

## Lokaler Start

```powershell
cd C:\Github\copy_trade
docker compose -f infra\docker\docker-compose.yml --env-file infra\docker\.env.example up --build
```

API danach lokal:

- `http://localhost:8000/health`
- `http://localhost:8000/ready`
- `http://localhost:8000/version`

## Lokale Python-Tests

```powershell
cd C:\Github\copy_trade
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.in
pytest
```

## Was bewusst noch nicht produktiv ist

- `/ready` prueft noch keine echten Infrastrukturverbindungen.
- Es gibt noch keine echten Exchange-Adapter.
- Die Copy Engine erzeugt noch keine Orders.
- Migrationen sind eingerichtet, aber die ersten Tabellen folgen in der naechsten Aufgabe.

## Verifikationspflicht vor echter Order-Ausfuehrung

Vor jeder echten Exchange-Order muessen erneut geprueft werden:

- offizielle Exchange-Doku
- Test-/Demo-Account Verhalten
- Rate Limits
- Idempotency und Client Order IDs
- Min Notional, Lot Size, Tick Size
- Slippage und Leverage-Semantik
