"""HR self-onboarding: shareable link -> employee submits -> HR approves or rejects."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.onboarding import EmployeeOnboarding, mask, normalize_cnic
from tests.support.workspace import add_member, error_code

pytestmark = pytest.mark.integration


def form(**overrides):
    values = {
        "full_name": "Ayesha Khan",
        "father_name": "Imran Khan",
        "cnic": "35202-1234567-8",
        "email": "ayesha@example.com",
        "designation": "Graphic Designer",
        "gender": "female",
        "date_of_joining": date.today().isoformat(),
        "date_of_birth": "1998-04-12",
        "job_type": "hybrid",
        "contact_number": "0300-1234567",
        "emergency_contact_1": {"name": "Imran Khan (father)", "phone": "0321 7654321"},
        "emergency_contact_2": {"name": "Sara Khan (sister)", "phone": "+92 333 1112223"},
        "address": "House 12, Street 4, Johar Town, near Emporium Mall, Lahore",
        "account_title": "Ayesha Khan",
        "bank_name": "Meezan Bank",
        "bank_account_number": "PK36 MEZN 0001 2345 6789 0123",
        "ntn": "1234567-8",
        "professional_reference": "Bilal Ahmed, bilal@example.com, 0301-2223334",
        "about": "I love illustration and hiking in the northern areas.",
    }
    values.update(overrides)
    return values


def with_key(stack):
    stack.app.state.settings.secrets_encryption_key = SecretStr(Fernet.generate_key().decode())


async def raw_row(stack, onboarding_id: str) -> EmployeeOnboarding:
    async with AsyncSession(
        bind=stack.app.state.test_connection, join_transaction_mode="create_savepoint"
    ) as session:
        row = await session.scalar(
            select(EmployeeOnboarding).where(EmployeeOnboarding.id == UUID(onboarding_id))
        )
        assert row is not None
        return row


async def test_link_submit_approve_creates_employee(stack):
    with_key(stack)
    async with stack.browser() as hr_browser, stack.browser() as public:
        owner = await stack.register(hr_browser, organization="Mendeez")
        link = await owner.create(
            "hr/onboarding",
            {"invited_name": "Ayesha Khan", "invited_designation": "Graphic Designer"},
        )
        assert link["path"] == f"/onboarding/{link['token']}" and len(link["token"]) >= 40
        public_path = f"/api/v1/public/onboarding/{link['token']}"

        opened = (await public.get(public_path)).json()
        assert opened["status"] == "open" and opened["organization_name"] == "Mendeez"
        assert opened["prefill"] == {
            "full_name": "Ayesha Khan",
            "designation": "Graphic Designer",
        }

        bad = await public.post(public_path, json=form(cnic="12345"))
        assert bad.status_code == 422
        missing = form()
        del missing["father_name"]
        assert (await public.post(public_path, json=missing)).status_code == 422

        submitted = await public.post(public_path, json=form())
        assert submitted.status_code == 200 and submitted.json()["status"] == "submitted"
        again = await public.post(public_path, json=form())
        assert again.status_code == 422 and error_code(again) == "ONBOARDING_LINK_CLOSED"

        # Stored encrypted: no personal detail in plaintext, token only as a digest.
        row = await raw_row(stack, link["id"])
        assert row.details_encrypted and "35202" not in row.details_encrypted
        assert "Meezan" not in row.details_encrypted and row.token_hash != link["token"]

        listed = (await owner.get("hr/onboarding", params={"status": "submitted"})).json()
        assert [i["id"] for i in listed["items"]] == [link["id"]]
        detail = (await owner.get(f"hr/onboarding/{link['id']}")).json()
        assert detail["sensitive_visible"] is True
        assert detail["details"]["cnic"] == "35202-1234567-8"
        assert detail["details"]["contact_number"] == "+923001234567"
        assert detail["details"]["bank_account_number"] == "PK36MEZN0001234567890123"

        notes = (await owner.get("notifications")).json()
        assert any(f"/hr/onboarding/{link['id']}" == (n.get("link") or "") for n in notes["items"])

        approved = await owner.create(
            f"hr/onboarding/{link['id']}/approve", {"employment_type": "full_time"}
        )
        assert approved["status"] == "approved" and approved["employee_id"]
        employee = (await owner.get(f"hr/employees/{approved['employee_id']}")).json()
        assert employee["full_name"] == "Ayesha Khan"
        assert employee["job_title"] == "Graphic Designer"
        assert employee["work_arrangement"] == "hybrid" and employee["gender"] == "female"
        assert employee["hire_date"] == date.today().isoformat()
        assert employee["has_personal_details"] is True
        personal = (await owner.get(f"hr/employees/{approved['employee_id']}/personal")).json()
        assert personal["cnic"] == "35202-1234567-8"
        assert personal["emergency_contact_2"]["phone"] == "+923331112223"

        # The same person cannot be onboarded twice.
        second = await owner.create("hr/onboarding", {})
        await public.post(f"/api/v1/public/onboarding/{second['token']}", json=form())
        duplicate_detail = (await owner.get(f"hr/onboarding/{second['id']}")).json()
        assert duplicate_detail["duplicate_employee_id"] == approved["employee_id"]
        duplicate = await owner.post(f"hr/onboarding/{second['id']}/approve", {})
        assert duplicate.status_code == 409
        rejected = await owner.create(
            f"hr/onboarding/{second['id']}/reject", {"note": "Duplicate submission"}
        )
        assert rejected["status"] == "rejected"

        audit = (await owner.get("audit/events", params={"entity_id": link["id"]})).json()
        actions = {e["action"] for e in audit["items"]}
        assert {
            "employee_onboarding.link_created",
            "employee_onboarding.submitted",
            "employee_onboarding.approved",
        } <= actions


async def test_closed_links_isolation_and_permissions(stack):
    with_key(stack)
    async with stack.browser() as a_browser, stack.browser() as b_browser, stack.browser() as p:
        owner = await stack.register(a_browser)
        other = await stack.register(b_browser)
        revoked = await owner.create("hr/onboarding", {})
        await owner.create(f"hr/onboarding/{revoked['id']}/revoke", {})
        path = f"/api/v1/public/onboarding/{revoked['token']}"
        assert (await p.get(path)).json()["status"] == "closed"
        assert error_code(await p.post(path, json=form())) == "ONBOARDING_LINK_CLOSED"

        expired = await owner.create("hr/onboarding", {"expires_in_days": 1})
        async with AsyncSession(
            bind=stack.app.state.test_connection, join_transaction_mode="create_savepoint"
        ) as session:
            await session.execute(
                update(EmployeeOnboarding)
                .where(EmployeeOnboarding.id == UUID(expired["id"]))
                .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            await session.commit()
        expired_path = f"/api/v1/public/onboarding/{expired['token']}"
        assert (await p.get(expired_path)).json()["status"] == "expired"
        assert (await p.post(expired_path, json=form())).status_code == 422
        listed = (await owner.get("hr/onboarding", params={"status": "expired"})).json()
        assert [i["id"] for i in listed["items"]] == [expired["id"]]

        unknown = await p.get("/api/v1/public/onboarding/" + "x" * 43)
        assert unknown.status_code == 404
        assert (await other.get(f"hr/onboarding/{revoked['id']}")).status_code == 404
        assert (await other.post(f"hr/onboarding/{revoked['id']}/revoke", {})).status_code == 404

        viewer_email = await add_member(owner, ["viewer"])
        async with stack.browser() as viewer_browser:
            viewer = await stack.login(viewer_browser, viewer_email)
            assert (await viewer.post("hr/onboarding", {})).status_code == 403
            assert (await viewer.get("hr/onboarding")).status_code == 403


async def test_links_require_encryption_key(stack):
    stack.app.state.settings.secrets_encryption_key = None
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        response = await owner.post("hr/onboarding", {})
        assert response.status_code == 503


def test_cnic_normalization_and_masking():
    assert normalize_cnic("3520212345678") == "35202-1234567-8"
    assert normalize_cnic("35202-1234567-8") == "35202-1234567-8"
    for bad in ("35202-123456-8", "abcde-1234567-8", ""):
        with pytest.raises(ValueError):
            normalize_cnic(bad)
    assert mask("cnic", "35202-1234567-8") == "•••••-•••••••-8"
    assert mask("bank_account_number", "PK36MEZN0001234567890123").endswith("0123")
    assert "PK36" not in mask("bank_account_number", "PK36MEZN0001234567890123")
