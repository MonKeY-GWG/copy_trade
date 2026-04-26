from fastapi.testclient import TestClient

from copy_trade_api.config import Settings
from copy_trade_api.main import create_app
from copy_trade_api.readiness import DependencyStatus, ReadinessReport, check_dependency


async def ready_report(_settings: Settings) -> ReadinessReport:
    return ReadinessReport(
        dependencies=(
            DependencyStatus(name="postgres", status="ok"),
            DependencyStatus(name="redis", status="ok"),
            DependencyStatus(name="nats", status="ok"),
        ),
    )


async def not_ready_report(_settings: Settings) -> ReadinessReport:
    return ReadinessReport(
        dependencies=(
            DependencyStatus(name="postgres", status="ok"),
            DependencyStatus(name="redis", status="unavailable"),
            DependencyStatus(name="nats", status="ok"),
        ),
    )


def test_ready_endpoint_returns_dependency_statuses_when_ready() -> None:
    client = TestClient(create_app(readiness_checker=ready_report))

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {
            "postgres": "ok",
            "redis": "ok",
            "nats": "ok",
        },
    }


def test_ready_endpoint_returns_503_when_dependency_is_unavailable() -> None:
    client = TestClient(create_app(readiness_checker=not_ready_report))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {
            "postgres": "ok",
            "redis": "unavailable",
            "nats": "ok",
        },
    }


async def test_check_dependency_hides_exception_details() -> None:
    async def failing_check() -> None:
        raise RuntimeError("do not expose connection details")

    status = await check_dependency("postgres", failing_check)

    assert status == DependencyStatus(name="postgres", status="unavailable")
