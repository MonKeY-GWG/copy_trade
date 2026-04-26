from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from copy_trade_api.audit import insert_audit_log
from copy_trade_api.auth import AdminDependency
from copy_trade_api.config import Settings
from copy_trade_api.database import connect
from copy_trade_api.identity import AuthenticatedPrincipal
from copy_trade_domain.events import Exchange

CREATE_COPY_RELATIONSHIP_SQL = """
INSERT INTO copy_relationships (
    id,
    source_exchange,
    source_account_id,
    source_symbol,
    follower_account_id,
    target_exchange,
    target_symbol,
    max_slippage_bps,
    active,
    effective_from
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING *
"""

SELECT_COPY_RELATIONSHIPS_SQL = """
SELECT *
FROM copy_relationships
"""

SELECT_COPY_RELATIONSHIP_BY_ID_SQL = """
SELECT *
FROM copy_relationships
WHERE id = $1
"""

SELECT_COPY_RELATIONSHIP_BY_ID_FOR_UPDATE_SQL = """
SELECT *
FROM copy_relationships
WHERE id = $1
FOR UPDATE
"""

AUDIT_ENTITY_COPY_RELATIONSHIP = "copy_relationship"
AUDIT_ACTION_COPY_RELATIONSHIP_CREATED = "copy_relationship.created"
AUDIT_ACTION_COPY_RELATIONSHIP_UPDATED = "copy_relationship.updated"


class DuplicateCopyRelationshipError(Exception):
    pass


@dataclass(frozen=True)
class CopyRelationshipRecord:
    id: UUID
    source_exchange: Exchange
    source_account_id: str
    source_symbol: str | None
    follower_account_id: str
    target_exchange: Exchange
    target_symbol: str
    max_slippage_bps: int
    active: bool
    effective_from: datetime
    created_at: datetime
    updated_at: datetime


class CopyRelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_exchange: Exchange
    source_account_id: str = Field(min_length=1, max_length=128)
    source_symbol: str | None = Field(default=None, min_length=1, max_length=64)
    follower_account_id: str = Field(min_length=1, max_length=128)
    target_exchange: Exchange
    target_symbol: str = Field(min_length=1, max_length=64)
    max_slippage_bps: int = Field(default=100, ge=0, le=1000)
    active: bool = True
    effective_from: datetime

    @field_validator("effective_from")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("effective_from must be timezone-aware")
        return value


class CopyRelationshipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool | None = None
    max_slippage_bps: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> "CopyRelationshipUpdate":
        if self.active is None and self.max_slippage_bps is None:
            raise ValueError("at least one field must be provided")
        return self


class CopyRelationshipResponse(BaseModel):
    id: UUID
    source_exchange: Exchange
    source_account_id: str
    source_symbol: str | None
    follower_account_id: str
    target_exchange: Exchange
    target_symbol: str
    max_slippage_bps: int
    active: bool
    effective_from: datetime
    created_at: datetime
    updated_at: datetime


class CopyRelationshipListResponse(BaseModel):
    items: list[CopyRelationshipResponse]
    limit: int
    offset: int


class CopyRelationshipRepository(Protocol):
    async def create(
        self,
        payload: CopyRelationshipCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CopyRelationshipRecord: ...

    async def list(
        self,
        *,
        active: bool | None,
        source_account_id: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[CopyRelationshipRecord]: ...

    async def update(
        self,
        relationship_id: UUID,
        payload: CopyRelationshipUpdate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CopyRelationshipRecord | None: ...


class PostgresCopyRelationshipRepository:
    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url

    async def create(
        self,
        payload: CopyRelationshipCreate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CopyRelationshipRecord:
        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    CREATE_COPY_RELATIONSHIP_SQL,
                    uuid4(),
                    payload.source_exchange.value,
                    payload.source_account_id,
                    payload.source_symbol,
                    payload.follower_account_id,
                    payload.target_exchange.value,
                    payload.target_symbol,
                    payload.max_slippage_bps,
                    payload.active,
                    payload.effective_from,
                )
                if row is None:
                    raise RuntimeError("copy relationship insert returned no row")
                record = _row_to_record(row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_COPY_RELATIONSHIP_CREATED,
                    entity_type=AUDIT_ENTITY_COPY_RELATIONSHIP,
                    entity_id=record.id,
                    before_state=None,
                    after_state=record_to_audit_state(record),
                )
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateCopyRelationshipError from exc
        finally:
            await connection.close()

        return record

    async def list(
        self,
        *,
        active: bool | None,
        source_account_id: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[CopyRelationshipRecord]:
        where_clauses: list[str] = []
        args: list[object] = []
        if active is not None:
            args.append(active)
            where_clauses.append(f"active = ${len(args)}")
        if source_account_id is not None:
            args.append(source_account_id)
            where_clauses.append(f"source_account_id = ${len(args)}")

        args.extend((limit, offset))
        query = SELECT_COPY_RELATIONSHIPS_SQL
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += f" ORDER BY created_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}"

        connection = await connect(self._database_url)
        try:
            rows = await connection.fetch(query, *args)
        finally:
            await connection.close()
        return tuple(_row_to_record(row) for row in rows)

    async def update(
        self,
        relationship_id: UUID,
        payload: CopyRelationshipUpdate,
        *,
        principal: AuthenticatedPrincipal,
    ) -> CopyRelationshipRecord | None:
        assignments: list[str] = []
        args: list[object] = []
        if payload.active is not None:
            args.append(payload.active)
            assignments.append(f"active = ${len(args)}")
        if payload.max_slippage_bps is not None:
            args.append(payload.max_slippage_bps)
            assignments.append(f"max_slippage_bps = ${len(args)}")

        if not assignments:
            return await self.get(relationship_id)

        args.append(relationship_id)
        query = (
            "UPDATE copy_relationships SET "
            + ", ".join(assignments)
            + f", updated_at = now() WHERE id = ${len(args)} RETURNING *"
        )

        connection = await connect(self._database_url)
        try:
            async with connection.transaction():
                before_row = await connection.fetchrow(
                    SELECT_COPY_RELATIONSHIP_BY_ID_FOR_UPDATE_SQL,
                    relationship_id,
                )
                if before_row is None:
                    return None
                before = _row_to_record(before_row)
                row = await connection.fetchrow(query, *args)
                if row is None:
                    return None
                after = _row_to_record(row)
                await insert_audit_log(
                    connection,
                    actor_type=principal.actor_type,
                    actor_id=principal.actor_id,
                    action=AUDIT_ACTION_COPY_RELATIONSHIP_UPDATED,
                    entity_type=AUDIT_ENTITY_COPY_RELATIONSHIP,
                    entity_id=after.id,
                    before_state=record_to_audit_state(before),
                    after_state=record_to_audit_state(after),
                )
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateCopyRelationshipError from exc
        finally:
            await connection.close()

        return after

    async def get(self, relationship_id: UUID) -> CopyRelationshipRecord | None:
        connection = await connect(self._database_url)
        try:
            row = await connection.fetchrow(SELECT_COPY_RELATIONSHIP_BY_ID_SQL, relationship_id)
        finally:
            await connection.close()
        if row is None:
            return None
        return _row_to_record(row)


def get_copy_relationship_repository(request: Request) -> CopyRelationshipRepository:
    repository = getattr(request.app.state, "copy_relationship_repository", None)
    if repository is None:
        raise RuntimeError("copy relationship repository is not configured")
    return repository


CopyRelationshipRepositoryDependency = Annotated[
    CopyRelationshipRepository,
    Depends(get_copy_relationship_repository),
]


def create_copy_relationship_router(admin_dependency: AdminDependency) -> APIRouter:
    router = APIRouter(prefix="/admin/copy-relationships", tags=["copy-relationships"])

    @router.post(
        "",
        response_model=CopyRelationshipResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_copy_relationship(
        payload: CopyRelationshipCreate,
        repository: CopyRelationshipRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> CopyRelationshipRecord:
        try:
            return await repository.create(payload, principal=principal)
        except DuplicateCopyRelationshipError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="active copy relationship already exists",
            ) from exc

    @router.get("", response_model=CopyRelationshipListResponse)
    async def list_copy_relationships(
        _principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
        repository: CopyRelationshipRepositoryDependency,
        active: bool | None = None,
        source_account_id: str | None = Query(default=None, min_length=1, max_length=128),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> CopyRelationshipListResponse:
        items = await repository.list(
            active=active,
            source_account_id=source_account_id,
            limit=limit,
            offset=offset,
        )
        return CopyRelationshipListResponse(
            items=[record_to_response(item) for item in items],
            limit=limit,
            offset=offset,
        )

    @router.patch("/{relationship_id}", response_model=CopyRelationshipResponse)
    async def update_copy_relationship(
        relationship_id: UUID,
        payload: CopyRelationshipUpdate,
        repository: CopyRelationshipRepositoryDependency,
        principal: Annotated[AuthenticatedPrincipal, Depends(admin_dependency)],
    ) -> CopyRelationshipRecord:
        try:
            record = await repository.update(relationship_id, payload, principal=principal)
        except DuplicateCopyRelationshipError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="active copy relationship already exists",
            ) from exc
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="copy relationship not found",
            )
        return record

    return router


def record_to_response(record: CopyRelationshipRecord) -> CopyRelationshipResponse:
    return CopyRelationshipResponse.model_validate(record, from_attributes=True)


def record_to_audit_state(record: CopyRelationshipRecord) -> dict[str, Any]:
    return record_to_response(record).model_dump(mode="json")


def _row_to_record(row: Any) -> CopyRelationshipRecord:
    return CopyRelationshipRecord(
        id=UUID(str(row["id"])),
        source_exchange=Exchange(str(row["source_exchange"])),
        source_account_id=str(row["source_account_id"]),
        source_symbol=row["source_symbol"],
        follower_account_id=str(row["follower_account_id"]),
        target_exchange=Exchange(str(row["target_exchange"])),
        target_symbol=str(row["target_symbol"]),
        max_slippage_bps=int(row["max_slippage_bps"]),
        active=bool(row["active"]),
        effective_from=row["effective_from"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
