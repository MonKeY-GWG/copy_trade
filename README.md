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
python -m pytest -p no:cacheprovider apps\api\tests workers\copy_engine\tests packages\domain\tests packages\exchange_adapters\tests
python -m ruff check apps\api workers\copy_engine packages\domain packages\exchange_adapters
```

## API Smoke Test

```powershell
$env:PYTHONPATH='C:\Github\copy_trade\apps\api\src;C:\Github\copy_trade\packages\domain\src;C:\Github\copy_trade\packages\exchange_adapters\src'
python -m uvicorn copy_trade_api.main:app --host 127.0.0.1 --port 8000
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/version`

## Legacy

The previous codebase is archived locally under `legacy/2026-04-26-pre-restart/` and ignored by Git.