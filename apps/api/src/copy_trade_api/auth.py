import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from copy_trade_api.config import Settings
from copy_trade_api.identity import ADMIN_ROLE, AuthenticatedPrincipal

AdminDependency = Callable[..., AuthenticatedPrincipal]
ENVIRONMENT_ADMIN_TOKEN_ENVS = {"dev", "development", "local", "test"}


def build_admin_dependency(settings: Settings) -> AdminDependency:
    async def require_admin_token(
        request: Request,
        token: Annotated[str | None, Header(alias="X-Copy-Trade-Admin-Token")] = None,
    ) -> AuthenticatedPrincipal:
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
            )

        repository = getattr(request.app.state, "admin_credential_repository", None)
        if repository is not None:
            try:
                principal = await repository.authenticate_admin_token(token)
            except Exception as exc:
                if _environment_admin_token_matches(settings, token):
                    return _environment_admin_principal()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="admin identity backend is unavailable",
                ) from exc
            if principal is not None and ADMIN_ROLE in principal.roles:
                return principal

        if _environment_admin_token_matches(settings, token):
            return _environment_admin_principal()

        if repository is None and not settings.admin_api_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="admin API is not configured",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
        )

    return require_admin_token


def _environment_admin_token_matches(settings: Settings, token: str) -> bool:
    if not settings.allow_environment_admin_token:
        return False
    if settings.env.lower() not in ENVIRONMENT_ADMIN_TOKEN_ENVS:
        return False
    if not settings.admin_api_token:
        return False
    return hmac.compare_digest(token, settings.admin_api_token)


def _environment_admin_principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=None,
        credential_id=None,
        roles=(ADMIN_ROLE,),
        actor_type="admin_api",
        actor_id=None,
        source="environment",
    )
