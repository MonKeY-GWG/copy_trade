import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from copy_trade_api.config import Settings
from copy_trade_api.database import connect

INSERT_AUDIT_LOG_SQL = """
INSERT INTO audit_logs (
    id,
    actor_type,
    actor_id,
    action,
    entity_type,
    entity_id,
    before_state,
    after_state,
    metadata_json
) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb)
"""

SELECT_AUDIT_LOGS_SQL = """
SELECT *
FROM audit_logs
"""


@dataclass(frozen=True)
class AuditLogRecord:
    id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    metadata_json: dict[str, Any]


class AuditLogResponse(BaseModel):
    id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    metadata: dict[str, Any]


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    limit: int
    offset: int


class AuditLogRepository(Protocol):
    async def list(
        self,
        *,
        entity_type: str | None,
        entity_id: UUID | None,
        action: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[AuditLogRecord]: ...


class PostgresAuditLogRepository:
    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url

    async def list(
        self,
        *,
        entity_type: str | None,
        entity_id: UUID | None,
        action: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[AuditLogRecord]:
        where_clauses: list[str] = []
        args: list[object] = []
        if entity_type is not None:
            args.append(entity_type)
            where_clauses.append(f"entity_type = ${len(args)}")
        if entity_id is not None:
            args.append(entity_id)
            where_clauses.append(f"entity_id = ${len(args)}")
        if action is not None:
            args.append(action)
            where_clauses.append(f"action = ${len(args)}")

        args.extend((limit, offset))
        query = SELECT_AUDIT_LOGS_SQL
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += f" ORDER BY occurred_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}"

        connection = await connect(self._database_url)
        try:
            rows = await connection.fetch(query, *args)
        finally:
            await connection.close()
        return tuple(_row_to_audit_log_record(row) for row in rows)


async def insert_audit_log(
    connection: Any,
    *,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    before_state: Mapping[str, Any] | None,
    after_state: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    await connection.execute(
        INSERT_AUDIT_LOG_SQL,
        uuid4(),
        actor_type,
        actor_id,
        action,
        entity_type,
        entity_id,
        json.dumps(before_state, separators=(",", ":")) if before_state is not None else None,
        json.dumps(after_state, separators=(",", ":")) if after_state is not None else None,
        json.dumps(metadata or {}, separators=(",", ":")),
    )


def get_audit_log_repository(request: Request) -> AuditLogRepository:
    repository = getattr(request.app.state, "audit_log_repository", None)
    if repository is None:
        raise RuntimeError("audit log repository is not configured")
    return repository


AuditLogRepositoryDependency = Annotated[
    AuditLogRepository,
    Depends(get_audit_log_repository),
]


def create_audit_log_router() -> APIRouter:
    router = APIRouter(prefix="/admin/audit-logs", tags=["audit-logs"])

    @router.get("", response_model=AuditLogListResponse)
    async def list_audit_logs(
        repository: AuditLogRepositoryDependency,
        entity_type: str | None = Query(default=None, min_length=1, max_length=128),
        entity_id: UUID | None = None,
        action: str | None = Query(default=None, min_length=1, max_length=128),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> AuditLogListResponse:
        items = await repository.list(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            limit=limit,
            offset=offset,
        )
        return AuditLogListResponse(
            items=[record_to_response(item) for item in items],
            limit=limit,
            offset=offset,
        )

    return router


def record_to_response(record: AuditLogRecord) -> AuditLogResponse:
    return AuditLogResponse(
        id=record.id,
        occurred_at=record.occurred_at,
        actor_type=record.actor_type,
        actor_id=record.actor_id,
        action=record.action,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        before_state=record.before_state,
        after_state=record.after_state,
        metadata=record.metadata_json,
    )


def _row_to_audit_log_record(row: Any) -> AuditLogRecord:
    return AuditLogRecord(
        id=UUID(str(row["id"])),
        occurred_at=row["occurred_at"],
        actor_type=str(row["actor_type"]),
        actor_id=row["actor_id"],
        action=str(row["action"]),
        entity_type=str(row["entity_type"]),
        entity_id=UUID(str(row["entity_id"])) if row["entity_id"] is not None else None,
        before_state=parse_json_object(row["before_state"]),
        after_state=parse_json_object(row["after_state"]),
        metadata_json=parse_json_object(row["metadata_json"]) or {},
    )


def parse_json_object(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    raise ValueError("audit json value must be an object")
