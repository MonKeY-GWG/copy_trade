from fastapi import FastAPI

from copy_trade_api import __version__
from copy_trade_api.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Copy Trade API", version=settings.api_version)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/ready", tags=["system"])
    async def ready() -> dict[str, str]:
        # The first real readiness check will validate postgres, redis and nats.
        return {"status": "ready"}

    @app.get("/version", tags=["system"])
    async def version() -> dict[str, str]:
        return {"version": __version__, "env": settings.env}

    return app


app = create_app()
