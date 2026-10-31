"""Approving a solution document or quote needs `quotes.approve`, not only `quotes.write`
(R-DOC-00: a Workzap reviewer approves). Editing, revising and sending keep `quotes.write`."""

import asyncio
from uuid import uuid4

import pytest

from app.modules.access.permissions import PERMISSIONS, SYSTEM_ROLES
from app.modules.pi import brain_doc_routes
from app.shared.errors import PermissionDenied
from app.shared.scope import WorkspaceScope


class Reached(Exception):
    """Raised by the stub that stands in for the document lookup: the permission check passed."""


def scope(*permissions: str) -> WorkspaceScope:
    return WorkspaceScope(
        tenant_id=uuid4(),
        environment_id=uuid4(),
        permissions=frozenset(permissions),
        user_id=uuid4(),
    )


@pytest.fixture
def reaches_lookup(monkeypatch):
    async def enabled(session, scope):
        return {"pi": set()}

    async def lookup(session, scope, doc_id):
        raise Reached

    monkeypatch.setattr("app.modules.pi.service.enabled_products", enabled)
    monkeypatch.setattr(brain_doc_routes, "_doc", lookup)


def approve(s: WorkspaceScope):
    return asyncio.run(brain_doc_routes.approve_document(uuid4(), s, None))


def test_quotes_write_alone_cannot_approve(reaches_lookup):
    with pytest.raises(PermissionDenied):
        approve(scope("pi.read", "quotes.read", "quotes.write"))


def test_quotes_approve_can_approve(reaches_lookup):
    with pytest.raises(Reached):
        approve(scope("pi.read", "quotes.read", "quotes.approve"))


def test_the_permission_exists_in_the_catalogue():
    assert "quotes.approve" in PERMISSIONS


def test_roles_that_approve_today_keep_it():
    """Owner, administrator and manager already hold quotes.approve, so the route change takes
    approval from nobody there. Sales holds only quotes.write and loses approval: intended."""
    for role in ("owner", "admin", "manager"):
        assert "quotes.approve" in SYSTEM_ROLES[role][2], role
    assert "quotes.approve" not in SYSTEM_ROLES["sales"][2]
