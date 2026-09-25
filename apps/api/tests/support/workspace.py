"""HTTP actors and workspace builders used by the auth, RBAC, isolation and flow tests.

Every actor is a separate httpx client (its own cookie jar) talking to the same ASGI app,
so sessions, CSRF tokens and workspace selections behave exactly as for real browsers.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy.engine import make_url

ORIGIN = "http://localhost:3000"
PASSWORD = "Correct-Horse-Battery-9"


def disposable_database_url() -> str | None:
    """The disposable database URL, refusing anything that is not a *_test PostgreSQL DB."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return None
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or not (parsed.database or "").endswith("_test"):
        raise RuntimeError("Integration tests require a PostgreSQL database whose name ends _test")
    return url


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


@dataclass
class Actor:
    """One signed-in browser. Mutations carry the session-bound CSRF token automatically."""

    client: httpx.AsyncClient
    email: str
    session: dict[str, Any] = field(default_factory=dict)

    @property
    def tenant_id(self) -> str:
        return str(self.session["tenant"]["id"])

    @property
    def environment_id(self) -> str:
        return str(self.session["environment"]["id"])

    def use_csrf(self) -> None:
        self.client.headers["x-csrf-token"] = self.client.cookies["platform_csrf"]

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.client.get(f"/api/v1/{path}", **kwargs)

    async def post(self, path: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        return await self.client.post(f"/api/v1/{path}", json=json, **kwargs)

    async def patch(self, path: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        return await self.client.patch(f"/api/v1/{path}", json=json, **kwargs)

    async def put(self, path: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        return await self.client.put(f"/api/v1/{path}", json=json, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.client.delete(f"/api/v1/{path}", **kwargs)

    async def ok(self, method: str, path: str, json: Any = None) -> Any:
        response = await self.client.request(method, f"/api/v1/{path}", json=json)
        assert response.status_code in (200, 201, 204), (method, path, response.text)
        return response.json() if response.content else None

    async def create(self, path: str, json: Any) -> Any:
        return await self.ok("POST", path, json)

    async def switch(self, tenant_id: str, environment_id: str | None = None) -> dict[str, Any]:
        self.session = await self.ok(
            "PUT",
            "auth/session/workspace",
            {"tenant_id": tenant_id, "environment_id": environment_id},
        )
        return self.session


@dataclass
class Stack:
    app: FastAPI

    @asynccontextmanager
    async def browser(self, origin: str | None = ORIGIN) -> AsyncIterator[httpx.AsyncClient]:
        headers = {"origin": origin} if origin else {}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
            headers=headers,
        ) as client:
            yield client

    async def register(self, client: httpx.AsyncClient, organization: str | None = None) -> Actor:
        email = f"{unique('owner')}@example.com"
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "display_name": "Owner",
                "organization_name": organization or unique("Org"),
            },
        )
        assert response.status_code == 201, response.text
        actor = Actor(client, email, response.json())
        actor.use_csrf()
        return actor

    async def login(self, client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> Actor:
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        actor = Actor(client, email, response.json())
        actor.use_csrf()
        return actor


async def set_business(actor: Actor, **values: Any) -> dict[str, Any]:
    result: dict[str, Any] = await actor.ok("PATCH", "settings/business", values)
    return result


async def product(
    actor: Actor,
    *,
    price: str = "10.00",
    currency: str = "USD",
    tracked: bool = False,
    offering_type: str | None = None,
    category_id: str | None = None,
) -> dict[str, Any]:
    """A single-variant catalog item; tracked items are physical products."""
    body: dict[str, Any] = {
        "name": unique("Item"),
        "offering_type": offering_type or ("product" if tracked else "service"),
        "variants": [
            {
                "sku": unique("SKU").upper(),
                "name": "Default",
                "price": price,
                "currency": currency,
                "track_inventory": tracked,
            }
        ],
    }
    if category_id:
        body["category_id"] = category_id
    result: dict[str, Any] = await actor.create("catalog/products", body)
    return result


async def receive(actor: Actor, variant_id: str, quantity: int) -> dict[str, Any]:
    result: dict[str, Any] = await actor.create(
        "inventory/adjustments",
        {"variant_id": variant_id, "quantity": quantity, "kind": "receipt", "reason": "Stock in"},
    )
    return result


async def on_hand(actor: Actor, variant_id: str) -> int:
    levels = (await actor.get("inventory/levels", params={"page_size": 100})).json()["items"]
    return sum(level["on_hand"] for level in levels if level["variant_id"] == variant_id)


async def accepted_quote(actor: Actor, customer_id: str, lines: list[dict[str, Any]]) -> Any:
    quote = await actor.create("quotes", {"customer_id": customer_id, "lines": lines})
    for action in ("submit", "approve", "send", "accept"):
        if action == "approve" and quote["status"] == "approved":
            continue
        quote = await actor.create(f"quotes/{quote['id']}/actions", {"action": action})
    assert quote["status"] == "accepted"
    return quote


async def add_member(owner: Actor, role_keys: list[str], password: str = PASSWORD) -> str:
    roles = {r["key"]: r["id"] for r in (await owner.get("roles")).json()}
    email = f"{unique('member')}@example.com"
    await owner.create(
        "members",
        {
            "email": email,
            "display_name": "Member",
            "initial_password": password,
            "role_ids": [roles[k] for k in role_keys],
        },
    )
    return email


def error_code(response: httpx.Response) -> str:
    code: str = response.json()["error"]["code"]
    return code
