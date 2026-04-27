from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from copy_trade_api import __version__
from copy_trade_api.admin_credentials import (
    AdminCredentialManagementRepository,
    PostgresAdminCredentialManagementRepository,
    create_admin_credential_router,
)
from copy_trade_api.audit import (
    AuditLogRepository,
    PostgresAuditLogRepository,
    create_audit_log_router,
)
from copy_trade_api.auth import build_admin_dependency
from copy_trade_api.config import Settings, get_settings
from copy_trade_api.copy_relationships import (
    CopyRelationshipRepository,
    PostgresCopyRelationshipRepository,
    create_copy_relationship_router,
)
from copy_trade_api.foundation_controls import (
    FoundationControlRepository,
    PostgresFoundationControlRepository,
    create_foundation_control_router,
)
from copy_trade_api.identity import AdminCredentialRepository, PostgresAdminCredentialRepository
from copy_trade_api.rate_limit import AdminRateLimitMiddleware
from copy_trade_api.readiness import ReadinessReport, check_readiness
from copy_trade_api.sessions import (
    PostgresUserSessionRepository,
    UserSessionRepository,
    create_auth_router,
)

ReadinessChecker = Callable[[Settings], Awaitable[ReadinessReport]]


def create_app(
    readiness_checker: ReadinessChecker = check_readiness,
    *,
    settings: Settings | None = None,
    copy_relationship_repository: CopyRelationshipRepository | None = None,
    audit_log_repository: AuditLogRepository | None = None,
    admin_credential_repository: AdminCredentialRepository | None = None,
    admin_credential_management_repository: AdminCredentialManagementRepository | None = None,
    foundation_control_repository: FoundationControlRepository | None = None,
    session_repository: UserSessionRepository | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Copy Trade API", version=settings.api_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Copy-Trade-Admin-Token",
            "X-Copy-Trade-CSRF-Token",
        ],
    )
    if settings.admin_rate_limit_requests > 0 and settings.admin_rate_limit_window_seconds > 0:
        app.add_middleware(
            AdminRateLimitMiddleware,
            max_requests=settings.admin_rate_limit_requests,
            window_seconds=settings.admin_rate_limit_window_seconds,
        )
    app.state.copy_relationship_repository = (
        copy_relationship_repository or PostgresCopyRelationshipRepository(settings)
    )
    app.state.audit_log_repository = audit_log_repository or PostgresAuditLogRepository(settings)
    app.state.admin_credential_repository = (
        admin_credential_repository or PostgresAdminCredentialRepository(settings)
    )
    app.state.admin_credential_management_repository = (
        admin_credential_management_repository
        or PostgresAdminCredentialManagementRepository(settings)
    )
    app.state.foundation_control_repository = (
        foundation_control_repository or PostgresFoundationControlRepository(settings)
    )
    app.state.session_repository = session_repository or PostgresUserSessionRepository(settings)
    admin_dependency = Depends(build_admin_dependency(settings))
    admin_principal_dependency = build_admin_dependency(settings)
    app.include_router(create_auth_router(settings))
    app.include_router(
        create_admin_credential_router(admin_principal_dependency),
    )
    app.include_router(
        create_foundation_control_router(admin_principal_dependency),
    )
    app.include_router(
        create_copy_relationship_router(admin_principal_dependency),
    )
    app.include_router(
        create_audit_log_router(),
        dependencies=[admin_dependency],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/ready", tags=["system"])
    async def ready() -> JSONResponse:
        report = await readiness_checker(settings)
        payload = report.as_response()
        status_code = status.HTTP_200_OK if report.ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/version", tags=["system"])
    async def version() -> dict[str, str]:
        return {"version": __version__, "env": settings.env}

    return app


app = create_app()
