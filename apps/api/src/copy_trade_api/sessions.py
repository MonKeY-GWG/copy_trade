import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from copy_trade_api.audit import insert_audit_log
from copy_trade_api.config import Settings
from copy_trade_api.database import connect
from copy_trade_api.identity import ADMIN_ROLE, AuthenticatedPrincipal, hash_api_token

SESSION_COOKIE_NAME = "copy_trade_session"
CSRF_COOKIE_NAME = "copy_trade_csrf"
CSRF_HEADER_NAME = "X-Copy-Trade-CSRF-Token"
PASSWORD_HASH_ALGORITHM = "scrypt"
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
AUDIT_ACTION_LOGIN_SUCCEEDED = "auth.login.succeeded"
AUDIT_ACTION_LOGIN_FAILED = "auth.login.failed"
AUDIT_ACTION_LOGOUT = "auth.logout"
AUDIT_ENTITY_AUTH_LOGIN = "auth_login"
AUDIT_ENTITY_USER_SESSION = "user_session"

SELECT_PASSWORD_LOGIN_SQL = """
SELECT
    users.id AS user_id,
    users.email,
    users.display_name,
    password_credentials.id AS password_credential_id,
    password_credentials.password_hash,
    array_agg(roles.name ORDER BY roles.name) AS roles
FROM users
JOIN password_credentials ON password_credentials.user_id = users.id
JOIN user_roles ON user_roles.user_id = users.id
JOIN roles ON roles.id = user_roles.role_id
WHERE users.email = $1
  AND users.status = 'active'
  AND password_credentials.active IS TRUE
GROUP BY
    users.id,
    users.email,
    users.display_name,
    password_credentials.id,
    password_credentials.password_hash
"""

INSERT_SESSION_SQL = """
INSERT INTO user_sessions (
    id,
    user_id,
    session_token_hash,
    csrf_token_hash,
    expires_at,
    user_agent,
    ip_address
) VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING id, user_id, expires_at
"""

SELECT_SESSION_SQL = """
SELECT
    user_sessions.id AS session_id,
    user_sessions.csrf_token_hash,
    user_sessions.expires_at,
    users.id AS user_id,
    users.email,
    users.display_name,
    array_agg(roles.name ORDER BY roles.name) AS roles
FROM user_sessions
JOIN users ON users.id = user_sessions.user_id
JOIN user_roles ON user_roles.user_id = users.id
JOIN roles ON roles.id = user_roles.role_id
WHERE user_sessions.session_token_hash = $1
  AND user_sessions.revoked_at IS NULL
  AND user_sessions.expires_at > now()
  AND users.status = 'active'
GROUP BY
    user_sessions.id,
    user_sessions.csrf_token_hash,
    user_sessions.expires_at,
    users.id,
    users.email,
    users.display_name
"""

UPDATE_PASSWORD_LAST_USED_SQL = """
UPDATE password_credentials
SET last_used_at = now()
WHERE id = $1
"""

UPDATE_SESSION_LAST_SEEN_SQL = """
UPDATE user_sessions
SET last_seen_at = now()
WHERE id = $1
"""

REVOKE_SESSION_SQL = """
UPDATE user_sessions
SET revoked_at = now()
WHERE session_token_hash = $1
  AND revoked_at IS NULL
RETURNING id, user_id
"""


class LoginFailedError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedSession:
    principal: AuthenticatedPrincipal
    email: str
    display_name: str | None
    expires_at: datetime


@dataclass(frozen=True)
class CreatedUserSession:
    session_token: str
    csrf_token: str
    authenticated_session: AuthenticatedSession


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be valid")
        return normalized


class LoginResponse(BaseModel):
    authenticated: bool = True
    user_id: UUID
    email: str
    display_name: str | None
    roles: tuple[str, ...]
    expires_at: datetime
    csrf_token: str


class SessionResponse(BaseModel):
    authenticated: bool = True
    user_id: UUID
    email: str
    display_name: str | None
    roles: tuple[str, ...]
    expires_at: datetime


class LogoutResponse(BaseModel):
    status: str


class UserSessionRepository(Protocol):
    async def login(
        self,
        payload: LoginRequest,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> CreatedUserSession: ...

    async def authenticate_session(
        self,
        session_token: str,
        *,
        csrf_token: str | None = None,
        require_csrf: bool = False,
    ) -> AuthenticatedSession | None: ...

    async def revoke_session(self, session_token: str) -> None: ...


class PostgresUserSessionRepository:
    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url
        self._session_ttl_minutes = settings.session_ttl_minutes

    async def login(
        self,
        payload: LoginRequest,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> CreatedUserSession:
        connection = await connect(self._database_url)
        try:
            row = await connection.fetchrow(SELECT_PASSWORD_LOGIN_SQL, payload.email)
            if row is None:
                await record_failed_login(connection, email=payload.email, user_id=None)
                raise LoginFailedError

            user_id = UUID(str(row["user_id"]))
            if not verify_password(payload.password, str(row["password_hash"])):
                await record_failed_login(connection, email=payload.email, user_id=user_id)
                raise LoginFailedError

            roles = roles_from_row(row)
            session_token = generate_session_token()
            csrf_token = generate_session_token()
            session_id = uuid4()
            expires_at = datetime.now(UTC) + timedelta(minutes=self._session_ttl_minutes)
            async with connection.transaction():
                await connection.fetchrow(
                    INSERT_SESSION_SQL,
                    session_id,
                    user_id,
                    hash_api_token(session_token),
                    hash_api_token(csrf_token),
                    expires_at,
                    user_agent,
                    ip_address,
                )
                await connection.execute(
                    UPDATE_PASSWORD_LAST_USED_SQL,
                    UUID(str(row["password_credential_id"])),
                )
                await insert_audit_log(
                    connection,
                    actor_type="user",
                    actor_id=str(user_id),
                    action=AUDIT_ACTION_LOGIN_SUCCEEDED,
                    entity_type=AUDIT_ENTITY_USER_SESSION,
                    entity_id=session_id,
                    before_state=None,
                    after_state={"user_id": str(user_id), "roles": roles},
                    metadata={"email": payload.email},
                )
        finally:
            await connection.close()

        principal = AuthenticatedPrincipal(
            user_id=user_id,
            credential_id=None,
            roles=roles,
            actor_type="user",
            actor_id=str(user_id),
            source="session",
            session_id=session_id,
        )
        return CreatedUserSession(
            session_token=session_token,
            csrf_token=csrf_token,
            authenticated_session=AuthenticatedSession(
                principal=principal,
                email=str(row["email"]),
                display_name=row["display_name"],
                expires_at=expires_at,
            ),
        )

    async def authenticate_session(
        self,
        session_token: str,
        *,
        csrf_token: str | None = None,
        require_csrf: bool = False,
    ) -> AuthenticatedSession | None:
        connection = await connect(self._database_url)
        try:
            row = await connection.fetchrow(SELECT_SESSION_SQL, hash_api_token(session_token))
            if row is None:
                return None
            if require_csrf:
                if csrf_token is None:
                    return None
                if not hmac.compare_digest(
                    hash_api_token(csrf_token),
                    str(row["csrf_token_hash"]),
                ):
                    return None
            session_id = UUID(str(row["session_id"]))
            user_id = UUID(str(row["user_id"]))
            roles = roles_from_row(row)
            await connection.execute(UPDATE_SESSION_LAST_SEEN_SQL, session_id)
        finally:
            await connection.close()

        return AuthenticatedSession(
            principal=AuthenticatedPrincipal(
                user_id=user_id,
                credential_id=None,
                roles=roles,
                actor_type="user",
                actor_id=str(user_id),
                source="session",
                session_id=session_id,
            ),
            email=str(row["email"]),
            display_name=row["display_name"],
            expires_at=row["expires_at"],
        )

    async def revoke_session(self, session_token: str) -> None:
        connection = await connect(self._database_url)
        try:
            row = await connection.fetchrow(REVOKE_SESSION_SQL, hash_api_token(session_token))
            if row is None:
                return
            await insert_audit_log(
                connection,
                actor_type="user",
                actor_id=str(row["user_id"]),
                action=AUDIT_ACTION_LOGOUT,
                entity_type=AUDIT_ENTITY_USER_SESSION,
                entity_id=UUID(str(row["id"])),
                before_state=None,
                after_state={"revoked": True},
            )
        finally:
            await connection.close()


async def record_failed_login(connection: Any, *, email: str, user_id: UUID | None) -> None:
    await insert_audit_log(
        connection,
        actor_type="system",
        actor_id=None,
        action=AUDIT_ACTION_LOGIN_FAILED,
        entity_type=AUDIT_ENTITY_AUTH_LOGIN,
        entity_id=user_id,
        before_state=None,
        after_state=None,
        metadata={"email": email, "reason": "invalid_credentials"},
    )


def get_user_session_repository(request: Request) -> UserSessionRepository:
    repository = getattr(request.app.state, "session_repository", None)
    if repository is None:
        raise RuntimeError("session repository is not configured")
    return repository


UserSessionRepositoryDependency = Annotated[
    UserSessionRepository,
    Depends(get_user_session_repository),
]
CsrfHeader = Annotated[str | None, Header(alias=CSRF_HEADER_NAME)]


def create_auth_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/login", response_model=LoginResponse)
    async def login(
        payload: LoginRequest,
        response: Response,
        request: Request,
        repository: UserSessionRepositoryDependency,
    ) -> LoginResponse:
        try:
            created = await repository.login(
                payload,
                user_agent=request.headers.get("user-agent"),
                ip_address=client_host(request),
            )
        except LoginFailedError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid credentials",
            ) from exc
        set_session_cookies(response, created, settings)
        return login_response(created)

    @router.get("/session", response_model=SessionResponse)
    async def get_session(
        request: Request,
        repository: UserSessionRepositoryDependency,
    ) -> SessionResponse:
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if session_token is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        session = await repository.authenticate_session(session_token)
        if session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        return session_response(session)

    @router.post("/logout", response_model=LogoutResponse)
    async def logout(
        request: Request,
        response: Response,
        repository: UserSessionRepositoryDependency,
        csrf_token: CsrfHeader = None,
    ) -> LogoutResponse:
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if session_token is not None:
            session = await repository.authenticate_session(
                session_token,
                csrf_token=csrf_token,
                require_csrf=True,
            )
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="unauthorized",
                )
            await repository.revoke_session(session_token)
        clear_session_cookies(response, settings)
        return LogoutResponse(status="ok")

    return router


def set_session_cookies(
    response: Response,
    created: CreatedUserSession,
    settings: Settings,
) -> None:
    max_age = settings.session_ttl_minutes * 60
    response.set_cookie(
        SESSION_COOKIE_NAME,
        created.session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        created.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def login_response(created: CreatedUserSession) -> LoginResponse:
    session = created.authenticated_session
    return LoginResponse(
        user_id=require_user_id(session.principal),
        email=session.email,
        display_name=session.display_name,
        roles=session.principal.roles,
        expires_at=session.expires_at,
        csrf_token=created.csrf_token,
    )


def session_response(session: AuthenticatedSession) -> SessionResponse:
    return SessionResponse(
        user_id=require_user_id(session.principal),
        email=session.email,
        display_name=session.display_name,
        roles=session.principal.roles,
        expires_at=session.expires_at,
    )


def require_user_id(principal: AuthenticatedPrincipal) -> UUID:
    if principal.user_id is None:
        raise RuntimeError("session principal must have a user_id")
    return principal.user_id


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"{PASSWORD_HASH_ALGORITHM}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_hex, digest_hex = stored_hash.split("$", 5)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
            dklen=len(bytes.fromhex(digest_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def roles_from_row(row: Any) -> tuple[str, ...]:
    roles = row["roles"] or ()
    return tuple(str(role) for role in roles)


def client_host(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def principal_is_admin(principal: AuthenticatedPrincipal) -> bool:
    return ADMIN_ROLE in principal.roles
