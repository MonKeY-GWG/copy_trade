from collections import defaultdict, deque
from collections.abc import Callable
from time import monotonic
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

Clock = Callable[[], float]


class InMemoryRateLimiter:
    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: float,
        clock: Clock = monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        bucket = self._requests[key]
        window_start = now - self._window_seconds
        while bucket and bucket[0] <= window_start:
            bucket.popleft()
        if len(bucket) >= self._max_requests:
            return False
        bucket.append(now)
        return True


class AdminRateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_requests: int,
        window_seconds: float,
    ) -> None:
        self._app = app
        self._retry_after_seconds = int(window_seconds)
        self._limiter = InMemoryRateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if path.startswith("/admin/") or path == "/auth/login":
            client_key = _client_key(scope)
            if not self._limiter.allow(client_key):
                response = JSONResponse(
                    {"detail": "rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(self._retry_after_seconds)},
                )
                await response(scope, receive, send)
                return

        await self._app(scope, receive, send)


def _client_key(scope: Scope) -> str:
    client: Any = scope.get("client")
    if isinstance(client, tuple) and client:
        return str(client[0])
    return "unknown"
