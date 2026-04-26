# Copy Trade Platform

Fresh V1 foundation for a multi-exchange perpetual futures copy-trading platform.

Product source of truth:

- `copy_trading_platform_concept_v1.pdf`
- `docs/restart/00_verified_restart_plan.md`
- `docs/adr/`

## Current Stack Direction

- Web: Next.js + TypeScript
- API: Python + FastAPI
- Workers: Python
- Database: PostgreSQL + Alembic
- Event bus: NATS JetStream
- Cache/rate state: Redis
- Deployment: Docker Compose first, Hetzner-ready later

## Local Checks

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r requirements.in
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\ruff.exe check apps\api workers\copy_engine packages\domain packages\exchange_adapters packages\shared_events infra\migrations
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## API Smoke Test

```powershell
$env:PYTHONPATH="$PWD\apps\api\src;$PWD\packages\domain\src;$PWD\packages\exchange_adapters\src"
.\.venv\Scripts\python.exe -m uvicorn copy_trade_api.main:app --host 127.0.0.1 --port 8000
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/version`

## Legacy

The previous codebase is archived locally under `legacy/2026-04-26-pre-restart/` and ignored by Git.
