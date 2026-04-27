from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from copy_trade_api.admin_credentials import (
    ADMIN_API_CREDENTIAL_TYPE,
    AdminCredentialCreate,
    AdminCredentialRecord,
    CreatedAdminCredential,
)
from copy_trade_api.config import Settings
from copy_trade_api.identity import AuthenticatedPrincipal
from copy_trade_api.main import create_app
from copy_trade_api.sessions import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    AuthenticatedSession,
    CreatedUserSession,
    LoginFailedError,
    LoginRequest,
    hash_password,
    verify_password,
)

ADMIN_TOKEN = "test-admin-token"
SESSION_TOKEN = "session-token-" + ("s" * 32)
CSRF_TOKEN = "csrf-token-" + ("c" * 32)


class FakeUserSessionRepository:
    def __init__(self) -> None:
        self.login_payloads: list[LoginRequest] = []
        self.authenticate_calls: list[tuple[str, str | None, bool]] = []
        self.revoked_tokens: list[str] = []
        self.fail_login = False

    async def login(
        self,
        payload: LoginRequest,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> CreatedUserSession:
        self.login_payloads.append(payload)
        if self.fail_login:
            raise LoginFailedError
        return CreatedUserSession(
            session_token=SESSION_TOKEN,
            csrf_token=CSRF_TOKEN,
            authenticated_session=make_authenticated_session(),
        )

    async def authenticate_session(
        self,
        session_token: str,
        *,
        csrf_token: str | None = None,
        require_csrf: bool = False,
    ) -> AuthenticatedSession | None:
        self.authenticate_calls.append((session_token, csrf_token, require_csrf))
        if session_token != SESSION_TOKEN:
            return None
        if require_csrf and csrf_token != CSRF_TOKEN:
            return None
        return make_authenticated_session()

    async def revoke_session(self, session_token: str) -> None:
        self.revoked_tokens.append(session_token)


class FakeAdminCredentialRepository:
    async def authenticate_admin_token(self, _token: str) -> AuthenticatedPrincipal | None:
        return make_principal()


class FakeAdminCredentialManagementRepository:
    def __init__(self) -> None:
        self.created_payloads: list[AdminCredentialCreate] = []

    async def create_admin_credential(
        self,
        payload: AdminCredentialCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential:
        self.created_payloads.append(payload)
        return CreatedAdminCredential(
            record=make_admin_credential_record(email=payload.email),
            token="new-admin-token-" + ("x" * 32),
        )

    async def list_admin_credentials(
        self,
        *,
        active: bool | None,
        limit: int,
        offset: int,
    ) -> Sequence[AdminCredentialRecord]:
        return [make_admin_credential_record()][offset : offset + limit]

    async def deactivate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> AdminCredentialRecord | None:
        return make_admin_credential_record(credential_id=credential_id, active=False)

    async def rotate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential | None:
        return CreatedAdminCredential(
            record=make_admin_credential_record(credential_id=credential_id),
            token="rotated-admin-token-" + ("r" * 32),
        )


def make_settings() -> Settings:
    return Settings(
        env="test",
        service_name="copy-trade-api",
        api_version="0.1.0",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        nats_url="nats://localhost:4222",
        admin_api_token=ADMIN_TOKEN,
        session_cookie_secure=False,
    )


def make_principal() -> AuthenticatedPrincipal:
    user_id = uuid4()
    return AuthenticatedPrincipal(
        user_id=user_id,
        credential_id=None,
        roles=("admin",),
        actor_type="user",
        actor_id=str(user_id),
        source="session",
        session_id=uuid4(),
    )


def make_authenticated_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        principal=make_principal(),
        email="admin@example.test",
        display_name="Admin",
        expires_at=datetime.now(UTC) + timedelta(hours=8),
    )


def make_admin_credential_record(
    *,
    credential_id: UUID | None = None,
    email: str = "admin@example.test",
    active: bool = True,
) -> AdminCredentialRecord:
    now = datetime.now(UTC)
    return AdminCredentialRecord(
        id=credential_id or uuid4(),
        user_id=uuid4(),
        email=email,
        display_name="Admin",
        credential_type=ADMIN_API_CREDENTIAL_TYPE,
        token_prefix="abc12345",
        active=active,
        created_at=now,
        last_used_at=None,
    )


def make_client(session_repository: FakeUserSessionRepository) -> TestClient:
    return TestClient(
        create_app(
            settings=make_settings(),
            admin_credential_repository=FakeAdminCredentialRepository(),
            admin_credential_management_repository=FakeAdminCredentialManagementRepository(),
            session_repository=session_repository,
        )
    )


def test_password_hash_uses_scrypt_and_verifies_without_plaintext() -> None:
    password = "correct horse battery staple"

    password_hash = hash_password(password)

    assert password_hash.startswith("scrypt$")
    assert password not in password_hash
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong password", password_hash) is False


def test_login_sets_http_only_session_cookie_and_returns_csrf_token() -> None:
    repository = FakeUserSessionRepository()
    client = make_client(repository)

    response = client.post(
        "/auth/login",
        json={"email": "Admin@Example.Test", "password": "correct-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin@example.test"
    assert body["csrf_token"] == CSRF_TOKEN
    assert SESSION_TOKEN not in str(body)
    assert repository.login_payloads[0].email == "admin@example.test"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        SESSION_COOKIE_NAME in header and "HttpOnly" in header for header in set_cookie_headers
    )
    assert any(
        CSRF_COOKIE_NAME in header and "HttpOnly" not in header for header in set_cookie_headers
    )


def test_login_rejects_invalid_credentials_without_cookie() -> None:
    repository = FakeUserSessionRepository()
    repository.fail_login = True
    client = make_client(repository)

    response = client.post(
        "/auth/login",
        json={"email": "admin@example.test", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}
    assert "set-cookie" not in response.headers


def test_get_session_returns_cookie_backed_principal() -> None:
    repository = FakeUserSessionRepository()
    client = make_client(repository)
    client.cookies.set(SESSION_COOKIE_NAME, SESSION_TOKEN)

    response = client.get("/auth/session")

    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.test"
    assert repository.authenticate_calls[0] == (SESSION_TOKEN, None, False)


def test_logout_requires_csrf_and_revokes_session() -> None:
    repository = FakeUserSessionRepository()
    client = make_client(repository)
    client.cookies.set(SESSION_COOKIE_NAME, SESSION_TOKEN)

    missing_csrf_response = client.post("/auth/logout")
    response = client.post("/auth/logout", headers={CSRF_HEADER_NAME: CSRF_TOKEN})

    assert missing_csrf_response.status_code == 401
    assert response.status_code == 200
    assert repository.revoked_tokens == [SESSION_TOKEN]
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        SESSION_COOKIE_NAME in header and "Max-Age=0" in header for header in set_cookie_headers
    )
    assert any(
        CSRF_COOKIE_NAME in header and "Max-Age=0" in header for header in set_cookie_headers
    )


def test_admin_get_route_accepts_session_cookie_without_header_token() -> None:
    repository = FakeUserSessionRepository()
    client = make_client(repository)
    client.cookies.set(SESSION_COOKIE_NAME, SESSION_TOKEN)

    response = client.get("/admin/identity/admin-credentials")

    assert response.status_code == 200
    assert repository.authenticate_calls[0] == (SESSION_TOKEN, None, False)


def test_admin_mutation_requires_csrf_for_session_cookie() -> None:
    repository = FakeUserSessionRepository()
    client = make_client(repository)
    client.cookies.set(SESSION_COOKIE_NAME, SESSION_TOKEN)

    missing_csrf_response = client.post(
        "/admin/identity/admin-credentials",
        json={"email": "admin@example.test"},
    )
    response = client.post(
        "/admin/identity/admin-credentials",
        json={"email": "admin@example.test"},
        headers={CSRF_HEADER_NAME: CSRF_TOKEN},
    )

    assert missing_csrf_response.status_code == 401
    assert response.status_code == 201
    assert repository.authenticate_calls[0] == (SESSION_TOKEN, None, True)
    assert repository.authenticate_calls[1] == (SESSION_TOKEN, CSRF_TOKEN, True)
