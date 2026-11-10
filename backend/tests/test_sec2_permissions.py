"""SEC-2: every endpoint checks authentication on the backend."""

import re

from httpx import AsyncClient

from app.main import app

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/token"),
    ("POST", "/api/v1/auth/refresh"),
}


def protected_routes() -> list[tuple[str, str]]:
    routes = []
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if (method.upper(), path) not in PUBLIC:
                routes.append((method.upper(), re.sub(r"\{[^}]+\}", "1", path)))
    return routes


async def test_every_non_public_endpoint_requires_a_token(client: AsyncClient) -> None:
    routes = protected_routes()
    assert routes, "no routes discovered"
    for method, path in routes:
        resp = await client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}"
