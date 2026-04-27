from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from copy_trade_api.admin_credentials import (
    ADMIN_API_CREDENTIAL_TYPE,
    AdminCredentialCreate,
    AdminCredentialInactiveError,
    AdminCredentialRecord,
    CreatedAdminCredential,
    PostgresAdminCredentialManagementRepository,
    generate_admin_api_token,
)
from copy_trade_api.config import Settings
from copy_trade_api.identity import AuthenticatedPrincipal, hash_api_token
from copy_trade_api.main import create_app

ADMIN_TOKEN = "test-admin-token"
_DEFAULT_PRINCIPAL = object()


class FakeAuthRepository:
    def __init__(self, principal: object = _DEFAULT_PRINCIPAL) -> None:
        self.principal = make_principal() if principal is _DEFAULT_PRINCIPAL else principal

    async def authenticate_admin_token(self, _token: str) -> AuthenticatedPrincipal | None:
        if self.principal is None:
            return None
        if not isinstance(self.principal, AuthenticatedPrincipal):
            raise TypeError("principal must be an AuthenticatedPrincipal or None")
        return self.principal


class FakeAdminCredentialManagementRepository:
    def __init__(self) -> None:
        self.records: list[AdminCredentialRecord] = [make_record()]
        self.created_payloads: list[AdminCredentialCreate] = []
        self.created_principals: list[AuthenticatedPrincipal] = []
        self.deactivated: list[tuple[UUID, AuthenticatedPrincipal]] = []
        self.rotated: list[tuple[UUID, AuthenticatedPrincipal]] = []
        self.return_none = False
        self.raise_inactive = False

    async def create_admin_credential(
        self,
        payload: AdminCredentialCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential:
        self.created_payloads.append(payload)
        self.created_principals.append(principal)
        record = make_record(email=payload.email, display_name=payload.display_name)
        self.records.append(record)
        return CreatedAdminCredential(record=record, token="new-admin-token-" + ("x" * 32))

    async def list_admin_credentials(
        self,
        *,
        active: bool | None,
        limit: int,
        offset: int,
    ) -> Sequence[AdminCredentialRecord]:
        records = self.records
        if active is not None:
            records = [record for record in records if record.active is active]
        return records[offset : offset + limit]

    async def deactivate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> AdminCredentialRecord | None:
        self.deactivated.append((credential_id, principal))
        if self.return_none:
            return None
        return make_record(credential_id=credential_id, active=False)

    async def rotate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential | None:
        self.rotated.append((credential_id, principal))
        if self.raise_inactive:
            raise AdminCredentialInactiveError
        if self.return_none:
            return None
        return CreatedAdminCredential(
            record=make_record(active=True),
            token="rotated-admin-token-" + ("y" * 32),
        )


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class FakeConnection:
    def __init__(self, rows: Sequence[dict[str, object] | None]) -> None:
        self._rows = list(rows)
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchval_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[object, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self._rows.pop(0)

    async def fetchval(self, query: str, *args: object) -> object:
        self.fetchval_calls.append((query, args))
        return uuid4()

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append(args)
        return "INSERT 0 1"

    async def close(self) -> None:
        self.closed = True


def make_settings() -> Settings:
    return Settings(
        env="test",
        service_name="copy-trade-api",
        api_version="0.1.0",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        nats_url="nats://localhost:4222",
        admin_api_token=ADMIN_TOKEN,
    )


def make_principal() -> AuthenticatedPrincipal:
    user_id = uuid4()
    return AuthenticatedPrincipal(
        user_id=user_id,
        credential_id=uuid4(),
        roles=("admin",),
        actor_type="user",
        actor_id=str(user_id),
        source="database",
    )


def make_non_admin_principal() -> AuthenticatedPrincipal:
    user_id = uuid4()
    return AuthenticatedPrincipal(
        user_id=user_id,
        credential_id=uuid4(),
        roles=("trader",),
        actor_type="user",
        actor_id=str(user_id),
        source="database",
    )


def make_record(
    *,
    credential_id: UUID | None = None,
    active: bool = True,
    email: str = "admin@example.test",
    display_name: str | None = "Admin",
) -> AdminCredentialRecord:
    now = datetime.now(UTC)
    return AdminCredentialRecord(
        id=credential_id or uuid4(),
        user_id=uuid4(),
        email=email,
        display_name=display_name,
        credential_type=ADMIN_API_CREDENTIAL_TYPE,
        token_prefix="abc12345",
        active=active,
        created_at=now,
        last_used_at=None,
    )


def make_row(
    *,
    credential_id: UUID | None = None,
    user_id: UUID | None = None,
    active: bool = True,
    email: str = "admin@example.test",
    display_name: str | None = "Admin",
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": credential_id or uuid4(),
        "user_id": user_id or uuid4(),
        "email": email,
        "display_name": display_name,
        "credential_type": ADMIN_API_CREDENTIAL_TYPE,
        "token_prefix": "abc12345",
        "active": active,
        "created_at": now,
        "last_used_at": None,
    }


def make_client(
    repository: FakeAdminCredentialManagementRepository,
    *,
    auth_repository: FakeAuthRepository | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            settings=make_settings(),
            admin_credential_repository=auth_repository or FakeAuthRepository(),
            admin_credential_management_repository=repository,
        )
    )


def auth_headers() -> dict[str, str]:
    return {"X-Copy-Trade-Admin-Token": ADMIN_TOKEN}


def token_headers(token: str) -> dict[str, str]:
    return {"X-Copy-Trade-Admin-Token": token}


def test_generate_admin_api_token_is_hashable_and_not_short() -> None:
    token = generate_admin_api_token()

    assert len(token) >= 32
    assert hash_api_token(token) != token


def test_create_admin_credential_returns_token_once_without_hash() -> None:
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(repository)

    response = client.post(
        "/admin/identity/admin-credentials",
        headers=auth_headers(),
        json={"email": "Admin@Example.Test", "display_name": "Admin User"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "admin@example.test"
    assert body["display_name"] == "Admin User"
    assert body["token"].startswith("new-admin-token-")
    assert "token_hash" not in body
    assert repository.created_payloads[0].email == "admin@example.test"
    assert repository.created_principals[0].actor_type == "user"


def test_admin_credential_endpoints_require_admin_token() -> None:
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(repository)

    response = client.get("/admin/identity/admin-credentials")

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_admin_credential_endpoints_reject_non_admin_principal() -> None:
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(
        repository,
        auth_repository=FakeAuthRepository(make_non_admin_principal()),
    )

    response = client.get(
        "/admin/identity/admin-credentials",
        headers=token_headers("non-admin-token-" + ("n" * 32)),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_admin_credential_endpoints_reject_unknown_database_credential() -> None:
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(
        repository,
        auth_repository=FakeAuthRepository(principal=None),
    )

    response = client.get(
        "/admin/identity/admin-credentials",
        headers=token_headers("unknown-token-" + ("u" * 32)),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_create_admin_credential_rejects_invalid_email() -> None:
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(repository)

    response = client.post(
        "/admin/identity/admin-credentials",
        headers=auth_headers(),
        json={"email": "not-an-email"},
    )

    assert response.status_code == 422


def test_list_admin_credentials_does_not_return_token_or_hash() -> None:
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(repository)

    response = client.get(
        "/admin/identity/admin-credentials?active=true&limit=10&offset=0",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert "token" not in body["items"][0]
    assert "token_hash" not in body["items"][0]


def test_deactivate_admin_credential_returns_inactive_record() -> None:
    credential_id = uuid4()
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(repository)

    response = client.post(
        f"/admin/identity/admin-credentials/{credential_id}/deactivate",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False
    assert repository.deactivated[0][0] == credential_id


def test_deactivate_admin_credential_returns_404_for_missing_record() -> None:
    repository = FakeAdminCredentialManagementRepository()
    repository.return_none = True
    client = make_client(repository)

    response = client.post(
        f"/admin/identity/admin-credentials/{uuid4()}/deactivate",
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "admin credential not found"}


def test_rotate_admin_credential_returns_new_token() -> None:
    credential_id = uuid4()
    repository = FakeAdminCredentialManagementRepository()
    client = make_client(repository)

    response = client.post(
        f"/admin/identity/admin-credentials/{credential_id}/rotate",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active"] is True
    assert body["token"].startswith("rotated-admin-token-")
    assert "token_hash" not in body
    assert repository.rotated[0][0] == credential_id


def test_rotate_admin_credential_rejects_inactive_record() -> None:
    repository = FakeAdminCredentialManagementRepository()
    repository.raise_inactive = True
    client = make_client(repository)

    response = client.post(
        f"/admin/identity/admin-credentials/{uuid4()}/rotate",
        headers=auth_headers(),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "admin credential is inactive"}


async def test_postgres_repository_create_stores_hash_and_writes_safe_audit(
    monkeypatch,
) -> None:
    user_id = uuid4()
    credential_id = uuid4()
    user_row = make_row(credential_id=user_id, user_id=user_id)
    credential_row = make_row(credential_id=credential_id, user_id=user_id)
    connection = FakeConnection([user_row, credential_row])

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.admin_credentials.connect", fake_connect)
    monkeypatch.setattr(
        "copy_trade_api.admin_credentials.generate_admin_api_token",
        lambda: "created-token-" + ("z" * 32),
    )
    repository = PostgresAdminCredentialManagementRepository(make_settings())

    created = await repository.create_admin_credential(
        AdminCredentialCreate(email="Admin@Example.Test", display_name="Admin"),
        principal=make_principal(),
    )

    assert created.token == "created-token-" + ("z" * 32)
    insert_args = connection.fetchrow_calls[1][1]
    assert insert_args[3] == hash_api_token(created.token)
    assert insert_args[3] != created.token
    assert insert_args[4] == created.token[:8]
    audit_args = connection.execute_calls[1]
    assert audit_args[3] == "admin_credential.created"
    assert created.token not in str(audit_args)
    assert "token_hash" not in str(audit_args)
    assert connection.closed is True


async def test_postgres_repository_create_can_store_password_without_plaintext(
    monkeypatch,
) -> None:
    user_id = uuid4()
    credential_id = uuid4()
    user_row = make_row(credential_id=user_id, user_id=user_id)
    credential_row = make_row(credential_id=credential_id, user_id=user_id)
    connection = FakeConnection([user_row, credential_row])

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.admin_credentials.connect", fake_connect)
    monkeypatch.setattr(
        "copy_trade_api.admin_credentials.generate_admin_api_token",
        lambda: "created-token-" + ("z" * 32),
    )
    repository = PostgresAdminCredentialManagementRepository(make_settings())

    await repository.create_admin_credential(
        AdminCredentialCreate(
            email="Admin@Example.Test",
            display_name="Admin",
            password="correct horse battery staple",
        ),
        principal=make_principal(),
    )

    password_args = connection.execute_calls[1]
    assert password_args[1] == user_id
    assert str(password_args[2]).startswith("scrypt$")
    assert "correct horse battery staple" not in str(connection.execute_calls)


async def test_postgres_repository_rotate_audits_old_and_new_credentials(monkeypatch) -> None:
    old_id = uuid4()
    new_id = uuid4()
    user_id = uuid4()
    before_row = make_row(credential_id=old_id, user_id=user_id, active=True)
    deactivated_row = make_row(credential_id=old_id, user_id=user_id, active=False)
    new_row = make_row(credential_id=new_id, user_id=user_id, active=True)
    connection = FakeConnection([before_row, deactivated_row, new_row])

    async def fake_connect(_database_url: str) -> FakeConnection:
        return connection

    monkeypatch.setattr("copy_trade_api.admin_credentials.connect", fake_connect)
    monkeypatch.setattr(
        "copy_trade_api.admin_credentials.generate_admin_api_token",
        lambda: "rotated-token-" + ("r" * 32),
    )
    repository = PostgresAdminCredentialManagementRepository(make_settings())

    created = await repository.rotate_admin_credential(old_id, principal=make_principal())

    assert created is not None
    assert created.record.id == new_id
    assert created.token == "rotated-token-" + ("r" * 32)
    deactivate_args = connection.fetchrow_calls[1][1]
    assert deactivate_args == (old_id,)
    audit_actions = [args[3] for args in connection.execute_calls]
    audit_entity_ids = [args[5] for args in connection.execute_calls]
    assert audit_actions == [
        "admin_credential.rotated",
        "admin_credential.rotation_created",
    ]
    assert audit_entity_ids == [old_id, new_id]
    assert created.token not in str(connection.execute_calls)
    assert "token_hash" not in str(connection.execute_calls)
