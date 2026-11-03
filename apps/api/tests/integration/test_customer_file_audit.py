"""BL-15: a customer file upload and delete leave an audit event, like the other customer writes.

The entry names the actor, workspace, customer, file, name and size; never the file's bytes.
"""

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_pi_teach_files import make_pdf

from app.modules.audit.models import AuditEvent
from tests.support.workspace import add_member

pytestmark = pytest.mark.integration

ACTIONS = ("customer.file_added", "customer.file_removed")
MARKER = "SECRET-MARKER-4f9c1e"


async def file_events(stack, tenant_id: str) -> list[AuditEvent]:
    async with AsyncSession(
        bind=stack.app.state.test_connection, join_transaction_mode="create_savepoint"
    ) as session:
        rows = await session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == UUID(tenant_id), AuditEvent.action.in_(ACTIONS))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return list(rows)


async def upload(actor, customer_id: str, name: str = "agreement.pdf", body: bytes | None = None):
    pdf = body if body is not None else make_pdf([MARKER])
    return await actor.client.post(
        f"/api/v1/customers/{customer_id}/files",
        files={"file": (name, pdf, "application/octet-stream")},
    )


def flat(event: AuditEvent) -> str:
    return " ".join(str(v) for v in (event.details, event.action, event.actor_label))


async def test_upload_and_delete_write_audit_events(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        customer = await owner.create("customers", {"name": "Sara Malik", "phone": "+923001112233"})
        pdf = make_pdf([MARKER])
        made = await upload(owner, customer["id"], body=pdf)
        assert made.status_code == 201, made.text
        row = made.json()

        added = await file_events(stack, owner.tenant_id)
        assert [e.action for e in added] == ["customer.file_added"]
        event = added[0]
        assert event.tenant_id == UUID(owner.tenant_id)
        assert event.environment_id == UUID(owner.environment_id)
        assert event.actor_type == "user" and event.actor_user_id is not None
        assert event.outcome == "success"
        assert event.entity_type == "customer_file" and event.entity_id == UUID(row["id"])
        assert event.details["customer_id"] == customer["id"]
        assert event.details["name"] == "agreement.pdf" and event.details["size"] == len(pdf)

        gone = await owner.delete(f"customer-files/{row['id']}")
        assert gone.status_code == 204
        both = await file_events(stack, owner.tenant_id)
        # one outer test transaction gives both rows the same created_at, so match by action
        assert sorted(e.action for e in both) == ["customer.file_added", "customer.file_removed"]
        removed = next(e for e in both if e.action == "customer.file_removed")
        assert removed.entity_type == "customer_file" and removed.entity_id == UUID(row["id"])
        assert removed.environment_id == UUID(owner.environment_id)
        assert removed.details["customer_id"] == customer["id"]
        assert removed.details["name"] == "agreement.pdf" and removed.details["size"] == len(pdf)


async def test_no_entry_for_a_denied_or_failed_request(stack):
    async with stack.browser() as browser, stack.browser() as viewer_browser:
        owner = await stack.register(browser)
        customer = await owner.create("customers", {"name": "Sara Malik", "phone": "+923001112244"})
        kept = (await upload(owner, customer["id"])).json()
        before = len(await file_events(stack, owner.tenant_id))

        viewer = await stack.login(viewer_browser, await add_member(owner, ["viewer"]))
        assert (await upload(viewer, customer["id"])).status_code == 403
        assert (await viewer.delete(f"customer-files/{kept['id']}")).status_code == 403

        bad = await upload(owner, customer["id"], "tool.exe", b"MZ\x90\x00\x03" + b"\x00" * 40)
        assert bad.status_code == 415
        empty = await upload(owner, customer["id"], "empty.pdf", b"")
        assert empty.status_code == 422
        missing = await owner.delete("customer-files/00000000-0000-4000-8000-000000000000")
        assert missing.status_code == 404

        assert len(await file_events(stack, owner.tenant_id)) == before


async def test_a_kept_receipt_is_not_removed_and_not_audited(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        customer = await owner.create("customers", {"name": "Sara Malik", "phone": "+923001112255"})
        made = (await upload(owner, customer["id"])).json()
        await _mark_receipt(stack, made["id"])
        before = len(await file_events(stack, owner.tenant_id))
        refused = await owner.delete(f"customer-files/{made['id']}")
        assert refused.status_code == 409
        assert len(await file_events(stack, owner.tenant_id)) == before


async def _mark_receipt(stack, file_id: str) -> None:
    from app.modules.customers.models import CustomerFile

    async with AsyncSession(
        bind=stack.app.state.test_connection, join_transaction_mode="create_savepoint"
    ) as session:
        row = await session.get(CustomerFile, UUID(file_id))
        assert row is not None
        row.source = "receipt"
        await session.commit()


async def test_entries_stay_in_their_own_workspace(stack):
    async with stack.browser() as a_browser, stack.browser() as b_browser:
        a = await stack.register(a_browser)
        b = await stack.register(b_browser)
        a_customer = await a.create("customers", {"name": "Only in A", "phone": "+923001119901"})
        a_file = (await upload(a, a_customer["id"])).json()

        stolen = await b.delete(f"customer-files/{a_file['id']}")
        assert stolen.status_code == 404
        cross = await upload(b, a_customer["id"])
        assert cross.status_code == 404

        assert [e.action for e in await file_events(stack, a.tenant_id)] == ["customer.file_added"]
        assert await file_events(stack, b.tenant_id) == []
        assert (await a.get(f"customers/{a_customer['id']}/files")).json()[0]["id"] == a_file["id"]

        b_customer = await b.create("customers", {"name": "Only in B", "phone": "+923001119902"})
        await upload(b, b_customer["id"])
        assert len(await file_events(stack, a.tenant_id)) == 1
        assert len(await file_events(stack, b.tenant_id)) == 1


async def test_an_entry_never_holds_the_file_content_or_a_secret(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        customer = await owner.create("customers", {"name": "Sara Malik", "phone": "+923001112266"})
        made = (await upload(owner, customer["id"])).json()
        await owner.delete(f"customer-files/{made['id']}")
        events = await file_events(stack, owner.tenant_id)
        assert len(events) == 2
        for event in events:
            text = flat(event)
            assert MARKER not in text and "%PDF" not in text
            details: dict[str, Any] = event.details
            assert set(details) <= {"customer_id", "name", "size", "mime", "source"}
            assert "data" not in details and "content" not in details
