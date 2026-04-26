import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from copy_trade_api.config import Settings
from copy_trade_api.database import connect

ADMIN_ROLE = "admin"
ADMIN_API_CREDENTIAL_TYPE = "admin_api_token"
MIN_ADMIN_API_TOKEN_LENGTH = 32

SELECT_ADMIN_CREDENTIAL_SQL = """
SELECT
    users.id AS user_id,
    api_credentials.id AS credential_id,
    array_agg(roles.name ORDER BY roles.name) AS roles
FROM api_credentials
JOIN users ON users.id = api_credentials.user_id
JOIN user_roles ON user_roles.user_id = users.id
JOIN roles ON roles.id = user_roles.role_id
WHERE api_credentials.credential_type = $1
  AND api_credentials.token_hash = $2
  AND api_credentials.active IS TRUE
  AND users.status = 'active'
GROUP BY users.id, api_credentials.id
"""

UPDATE_CREDENTIAL_LAST_USED_SQL = """
UPDATE api_credentials
SET last_used_at = now()
WHERE id = $1
"""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: UUID | None
    credential_id: UUID | None
    roles: tuple[str, ...]
    actor_type: str
    actor_id: str | None
    source: str


class AdminCredentialRepository(Protocol):
    async def authenticate_admin_token(self, token: str) -> AuthenticatedPrincipal | None: ...


class PostgresAdminCredentialRepository:
    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url

    async def authenticate_admin_token(self, token: str) -> AuthenticatedPrincipal | None:
        if not is_admin_api_token_candidate(token):
            return None

        token_hash = hash_api_token(token)
        connection = await connect(self._database_url)
        try:
            row = await connection.fetchrow(
                SELECT_ADMIN_CREDENTIAL_SQL,
                ADMIN_API_CREDENTIAL_TYPE,
                token_hash,
            )
            if row is None:
                return None

            roles = _roles_from_row(row)
            if ADMIN_ROLE not in roles:
                return None

            credential_id = UUID(str(row["credential_id"]))
            user_id = UUID(str(row["user_id"]))
            await connection.execute(UPDATE_CREDENTIAL_LAST_USED_SQL, credential_id)
        finally:
            await connection.close()

        return AuthenticatedPrincipal(
            user_id=user_id,
            credential_id=credential_id,
            roles=roles,
            actor_type="user",
            actor_id=str(user_id),
            source="database",
        )


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_admin_api_token_candidate(token: str) -> bool:
    return len(token) >= MIN_ADMIN_API_TOKEN_LENGTH


def _roles_from_row(row: Any) -> tuple[str, ...]:
    roles = row["roles"] or ()
    return tuple(str(role) for role in roles)
