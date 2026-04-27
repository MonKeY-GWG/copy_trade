import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from copy_trade_api.audit import insert_audit_log
from copy_trade_api.auth import AdminDependency
from copy_trade_api.config import Settings
from copy_trade_api.database import connect
from copy_trade_api.identity import (
    ADMIN_API_CREDENTIAL_TYPE,
    ADMIN_ROLE,
    AuthenticatedPrincipal,
    hash_api_token,
    is_admin_api_token_candidate,
)
from copy_trade_api.sessions import hash_password

TOKEN_PREFIX_LENGTH = 8
AUDIT_ENTITY_API_CREDENTIAL = "api_credential"
AUDIT_ACTION_ADMIN_CREDENTIAL_CREATED = "admin_credential.created"
AUDIT_ACTION_ADMIN_CREDENTIAL_DEACTIVATED = "admin_credential.deactivated"
AUDIT_ACTION_ADMIN_CREDENTIAL_ROTATED = "admin_credential.rotated"
AUDIT_ACTION_ADMIN_CREDENTIAL_ROTATION_CREATED = "admin_credential.rotation_created"

SELECT_ADMIN_ROLE_ID_SQL = """
SELECT id
FROM roles
WHERE name = $1
"""

UPSERT_ACTIVE_USER_SQL = """
INSERT INTO users (id, email, display_name, status)
VALUES ($1, $2, $3, 'active')
ON CONFLICT (email) DO UPDATE
SET
    display_name = COALESCE(EXCLUDED.display_name, users.display_name),
    updated_at = now()
WHERE users.status = 'active'
RETURNING id, email, display_name, status, created_at, updated_at
"""

INSERT_USER_ROLE_SQL = """
INSERT INTO user_roles (user_id, role_id)
VALUES ($1, $2)
ON CONFLICT DO NOTHING
"""

UPSERT_PASSWORD_CREDENTIAL_SQL = """
INSERT INTO password_credentials (
    id,
    user_id,
    password_hash,
    active
) VALUES ($1, $2, $3, true)
ON CONFLICT (user_id) DO UPDATE
SET
    password_hash = EXCLUDED.password_hash,
    active = true,
    updated_at = now()
"""

INSERT_ADMIN_CREDENTIAL_SQL = """
INSERT INTO api_credentials (
    id,
    user_id,
    credential_type,
    token_hash,
    token_prefix,
    active
) VALUES ($1, $2, $3, $4, $5, true)
RETURNING id, user_id, credential_type, token_prefix, active, created_at, last_used_at
"""

SELECT_ADMIN_CREDENTIALS_SQL = """
SELECT
    api_credentials.id,
    api_credentials.user_id,
    users.email,
    users.display_name,
    api_credentials.credential_type,
    api_credentials.token_prefix,
    api_credentials.active,
    api_credentials.created_at,
    api_credentials.last_used_at
FROM api_credentials
JOIN users ON users.id = api_credentials.user_id
WHERE api_credentials.credential_type = $1
"""

SELECT_ADMIN_CREDENTIAL_BY_ID_FOR_UPDATE_SQL = """
SELECT
    api_credentials.id,
    api_credentials.user_id,
    users.email,
    users.display_name,
    api_credentials.credential_type,
    api_credentials.token_prefix,
    api_credentials.active,
    api_credentials.created_at,
    api_credentials.last_used_at
FROM api_credentials
JOIN users ON users.id = api_credentials.user_id
WHERE api_credentials.id = $1
  AND api_credentials.credential_type = $2
FOR UPDATE
"""

DEACTIVATE_ADMIN_CREDENTIAL_SQL = """
UPDATE api_credentials
SET active = false
WHERE id = $1
RETURNING id, user_id, credential_type, token_prefix, active, created_at, last_used_at
"""


class AdminCredentialUserDisabledError(Exception):
    pass


class AdminCredentialInactiveError(Exception):
    pass


@dataclass(frozen=True)
class AdminCredentialRecord:
    id: UUID
    user_id: UUID
    email: str
    display_name: str | None
    credential_type: str
    token_prefix: str | None
    active: bool
    created_at: datetime
    last_used_at: datetime | None


@dataclass(frozen=True)
class CreatedAdminCredential:
    record: AdminCredentialRecord
    token: str


class AdminCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be valid")
        return normalized


class AdminCredentialResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    display_name: str | None
    credential_type: str
    token_prefix: str | None
    active: bool
    created_at: datetime
    last_used_at: datetime | None


class AdminCredentialCreateResponse(AdminCredentialResponse):
    token: str


class AdminCredentialListResponse(BaseModel):
    items: list[AdminCredentialResponse]
    limit: int
    offset: int


class AdminCredentialManagementRepository(Protocol):
    async def create_admin_credential(
        self,
        payload: AdminCredentialCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential: ...

    async def list_admin_credentials(
        self,
        *,
        active: bool | None,
        limit: int,
        offset: int,
    ) -> Sequence[AdminCredentialRecord]: ...

    async def deactivate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> AdminCredentialRecord | None: ...

    async def rotate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential | None: ...


class PostgresAdminCredentialManagementRepository:
    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url

    async def create_admin_credential(
        self,
        payload: AdminCredentialCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential:
        token = generate_admin_api_token()
        credential_id = uuid4()
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                user_row = await connection.fetchrow(
                    UPSERT_ACTIVE_USER_SQL,
                    uuid4(),
                    payload.email,
                    payload.display_name,
                )
                if user_row is None:
                    raise AdminCredentialUserDisabledError
                admin_role_id = await connection.fetchval(SELECT_ADMIN_ROLE_ID_SQL, ADMIN_ROLE)
                if admin_role_id is None:
                    raise RuntimeError("admin role is not configured")
                await connection.execute(
                    INSERT_USER_ROLE_SQL,
                    user_row["id"],
                    admin_role_id,
                )
                if payload.password is not None:
                    await connection.execute(
                        UPSERT_PASSWORD_CREDENTIAL_SQL,
                        uuid4(),
                        user_row["id"],
                        hash_password(payload.password),
                    )
                credential_row = await insert_admin_credential_row(
                    connection,
                    credential_id=credential_id,
                    user_id=user_row["id"],
                    token=token,
                )
                record = _credential_row_to_record(credential_row, user_row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_ADMIN_CREDENTIAL_CREATED,
                    entity_type=AUDIT_ENTITY_API_CREDENTIAL,
                    entity_id=record.id,
                    before_state=None,
                    after_state=record_to_audit_state(record),
                )
        finally:
            await connection.close()

        return CreatedAdminCredential(record=record, token=token)

    async def list_admin_credentials(
        self,
        *,
        active: bool | None,
        limit: int,
        offset: int,
    ) -> Sequence[AdminCredentialRecord]:
        args: list[object] = [ADMIN_API_CREDENTIAL_TYPE]
        query = SELECT_ADMIN_CREDENTIALS_SQL
        if active is not None:
            args.append(active)
            query += f" AND api_credentials.active = ${len(args)}"
        args.extend((limit, offset))
        query += (
            " ORDER BY api_credentials.created_at DESC"
            f" LIMIT ${len(args) - 1} OFFSET ${len(args)}"
        )

        connection = await connect(self._database_url)
        try:
            rows = await connection.fetch(query, *args)
        finally:
            await connection.close()
        return tuple(_row_to_record(row) for row in rows)

    async def deactivate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> AdminCredentialRecord | None:
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                before_row = await connection.fetchrow(
                    SELECT_ADMIN_CREDENTIAL_BY_ID_FOR_UPDATE_SQL,
                    credential_id,
                    ADMIN_API_CREDENTIAL_TYPE,
                )
                if before_row is None:
                    return None
                before = _row_to_record(before_row)
                if not before.active:
                    return before
                after_row = await connection.fetchrow(
                    DEACTIVATE_ADMIN_CREDENTIAL_SQL,
                    credential_id,
                )
                if after_row is None:
                    return None
                after = _row_to_record({**dict(before_row), **dict(after_row)})
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_ADMIN_CREDENTIAL_DEACTIVATED,
                    entity_type=AUDIT_ENTITY_API_CREDENTIAL,
                    entity_id=after.id,
                    before_state=record_to_audit_state(before),
                    after_state=record_to_audit_state(after),
                )
        finally:
            await connection.close()

        return after

    async def rotate_admin_credential(
        self,
        credential_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CreatedAdminCredential | None:
        token = generate_admin_api_token()
        new_credential_id = uuid4()
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                before_row = await connection.fetchrow(
                    SELECT_ADMIN_CREDENTIAL_BY_ID_FOR_UPDATE_SQL,
                    credential_id,
                    ADMIN_API_CREDENTIAL_TYPE,
                )
                if before_row is None:
                    return None
                before = _row_to_record(before_row)
                if not before.active:
                    raise AdminCredentialInactiveError
                deactivated_row = await connection.fetchrow(
                    DEACTIVATE_ADMIN_CREDENTIAL_SQL,
                    credential_id,
                )
                if deactivated_row is None:
                    return None
                after_old = _row_to_record({**dict(before_row), **dict(deactivated_row)})
                new_row = await insert_admin_credential_row(
                    connection,
                    credential_id=new_credential_id,
                    user_id=before.user_id,
                    token=token,
                )
                new_record = _credential_row_to_record(new_row, before_row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_ADMIN_CREDENTIAL_ROTATED,
                    entity_type=AUDIT_ENTITY_API_CREDENTIAL,
                    entity_id=after_old.id,
                    before_state=record_to_audit_state(before),
                    after_state=record_to_audit_state(after_old),
                    metadata={"new_credential_id": str(new_record.id)},
                )
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_ADMIN_CREDENTIAL_ROTATION_CREATED,
                    entity_type=AUDIT_ENTITY_API_CREDENTIAL,
                    entity_id=new_record.id,
                    before_state=None,
                    after_state=record_to_audit_state(new_record),
                    metadata={"deactivated_credential_id": str(after_old.id)},
                )
        finally:
            await connection.close()

        return CreatedAdminCredential(record=new_record, token=token)


async def insert_admin_credential_row(
    connection: Any,
    *,
    credential_id: UUID,
    user_id: UUID,
    token: str,
) -> Any:
    return await connection.fetchrow(
        INSERT_ADMIN_CREDENTIAL_SQL,
        credential_id,
        user_id,
        ADMIN_API_CREDENTIAL_TYPE,
        hash_api_token(token),
        token[:TOKEN_PREFIX_LENGTH],
    )


def get_admin_credential_management_repository(
    request: Request,
) -> AdminCredentialManagementRepository:
    repository = getattr(request.app.state, "admin_credential_management_repository", None)
    if repository is None:
        raise RuntimeError("admin credential management repository is not configured")
    return repository


AdminCredentialManagementRepositoryDependency = Annotated[
    AdminCredentialManagementRepository,
    Depends(get_admin_credential_management_repository),
]


def create_admin_credential_router(admin_dependency: AdminDependency) -> APIRouter:
    router = APIRouter(prefix="/admin/identity/admin-credentials", tags=["admin-credentials"])

    @router.post(
        "",
        response_model=AdminCredentialCreateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_admin_credential(
        payload: AdminCredentialCreate,
        repository: AdminCredentialManagementRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> AdminCredentialCreateResponse:
        try:
            created = await repository.create_admin_credential(payload, principal=principal)
        except AdminCredentialUserDisabledError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="admin user is disabled",
            ) from exc
        return created_record_to_response(created)

    @router.get("", response_model=AdminCredentialListResponse)
    async def list_admin_credentials(
        repository: AdminCredentialManagementRepositoryDependency,
        _principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
        active: bool | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> AdminCredentialListResponse:
        items = await repository.list_admin_credentials(
            active=active,
            limit=limit,
            offset=offset,
        )
        return AdminCredentialListResponse(
            items=[record_to_response(item) for item in items],
            limit=limit,
            offset=offset,
        )

    @router.post("/{credential_id}/deactivate", response_model=AdminCredentialResponse)
    async def deactivate_admin_credential(
        credential_id: UUID,
        repository: AdminCredentialManagementRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> AdminCredentialResponse:
        record = await repository.deactivate_admin_credential(
            credential_id,
            principal=principal,
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="admin credential not found",
            )
        return record_to_response(record)

    @router.post("/{credential_id}/rotate", response_model=AdminCredentialCreateResponse)
    async def rotate_admin_credential(
        credential_id: UUID,
        repository: AdminCredentialManagementRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> AdminCredentialCreateResponse:
        try:
            created = await repository.rotate_admin_credential(
                credential_id,
                principal=principal,
            )
        except AdminCredentialInactiveError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="admin credential is inactive",
            ) from exc
        if created is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="admin credential not found",
            )
        return created_record_to_response(created)

    return router


def generate_admin_api_token() -> str:
    token = secrets.token_urlsafe(32)
    if not is_admin_api_token_candidate(token):
        raise RuntimeError("generated admin API token is too short")
    return token


def created_record_to_response(created: CreatedAdminCredential) -> AdminCredentialCreateResponse:
    response = record_to_response(created.record)
    return AdminCredentialCreateResponse(**response.model_dump(), token=created.token)


def record_to_response(record: AdminCredentialRecord) -> AdminCredentialResponse:
    return AdminCredentialResponse(
        id=record.id,
        user_id=record.user_id,
        email=record.email,
        display_name=record.display_name,
        credential_type=record.credential_type,
        token_prefix=record.token_prefix,
        active=record.active,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
    )


def record_to_audit_state(record: AdminCredentialRecord) -> dict[str, Any]:
    return json.loads(record_to_response(record).model_dump_json())


def _credential_row_to_record(credential_row: Any, user_row: Any) -> AdminCredentialRecord:
    merged = {
        **dict(credential_row),
        "email": user_row["email"],
        "display_name": user_row["display_name"],
    }
    return _row_to_record(merged)


def _row_to_record(row: Any) -> AdminCredentialRecord:
    return AdminCredentialRecord(
        id=UUID(str(row["id"])),
        user_id=UUID(str(row["user_id"])),
        email=str(row["email"]),
        display_name=row["display_name"],
        credential_type=str(row["credential_type"]),
        token_prefix=row["token_prefix"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )
