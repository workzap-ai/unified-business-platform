"""Customer files in the database: upload without S3, list, safe download, type sniffing,
delete; receipts are kept; a WhatsApp document is saved once and linked from the chat."""

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select
from test_pi_documents import _serve
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn
from test_pi_teach_files import make_pdf
from test_service_lifecycle import create

from app.ai.manager import LLMManager
from app.modules.customers import files
from app.modules.customers.models import CustomerActivity, CustomerFile
from app.modules.pi.models import PiMessage
from app.modules.pi.runtime import _keep_file
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


async def test_upload_list_download_and_delete(api, business_db):
    pi = await pi_workspace(api, business_db)
    customer = await create(api, "customers", {"name": "Sara Malik", "phone": "+923001112233"})
    pdf = make_pdf(["Signed agreement"])
    made = await api.post(
        f"/api/v1/customers/{customer['id']}/files",
        files={"file": ("agreement.pdf", pdf, "application/octet-stream")},
    )
    assert made.status_code == 201, made.text
    row = made.json()
    assert row["mime"] == "application/pdf" and row["source"] == "upload"
    assert row["name"] == "agreement.pdf" and row["size"] == len(pdf)

    listed = (await api.get(f"/api/v1/customers/{customer['id']}/files")).json()
    assert [f["id"] for f in listed] == [row["id"]] and "data" not in listed[0]

    got = await api.get(f"/api/v1/customer-files/{row['id']}/download")
    assert got.status_code == 200 and got.content == pdf
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"].startswith("attachment;")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in got.headers["content-security-policy"]

    bad = await api.post(
        f"/api/v1/customers/{customer['id']}/files",
        files={"file": ("tool.exe", b"MZ\x90\x00\x03" + b"\x00" * 40, "application/pdf")},
    )
    assert bad.status_code == 415

    gone = await api.delete(f"/api/v1/customer-files/{row['id']}")
    assert gone.status_code == 204
    assert (await api.get(f"/api/v1/customers/{customer['id']}/files")).json() == []
    await pi.close()


async def test_receipts_are_kept(api, business_db):
    pi = await pi_workspace(api, business_db)
    customer = await create(api, "customers", {"name": "Sara Malik", "phone": "+923001112244"})
    system = WorkspaceScope.system(UUID(pi.tenant_id), UUID(pi.environment_id), frozenset(), "PI")
    row = await files.save(
        pi.db, system, UUID(customer["id"]), make_pdf(["Receipt"]), "RCPT-1", "receipt"
    )
    await pi.db.commit()
    assert row.name == "RCPT-1.pdf"
    refused = await api.delete(f"/api/v1/customer-files/{row.id}")
    assert refused.status_code == 409
    await pi.close()


async def test_a_whatsapp_document_is_kept_once_and_linked(api, business_db, monkeypatch):
    async def complete(self, scope, **kwargs):
        return SimpleNamespace(text="Product brief: camera analytics.", attempts=[])

    monkeypatch.setattr(LLMManager, "complete", complete)
    mock_turns(monkeypatch, turn(reply="Thanks, I'm pi, the company's AI assistant. Read it."))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _serve(pi, make_pdf(["Product brief VISION", "Camera analytics"]))
    await pi.process("", "wamid.keep-1", kind="document", media_id="555666777")
    await pi.deliver_all()

    inbound = await business_db.scalar(
        select(PiMessage).where(PiMessage.provider_message_id == "wamid.keep-1")
    )
    saved = await business_db.scalar(
        select(CustomerFile).where(CustomerFile.message_id == inbound.id)
    )
    assert saved is not None and saved.source == "whatsapp" and saved.mime == "application/pdf"
    assert inbound.media["file_id"] == str(saved.id)
    download = await api.get(f"/api/v1/customer-files/{saved.id}/download")
    assert download.status_code == 200 and download.content.startswith(b"%PDF-")

    # Saving the same message again changes nothing: one file, one timeline entry.
    conversation = await pi.conversation()
    system = WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "PI"
    )
    await _keep_file(pi.db, system, conversation, inbound, make_pdf(["again"]), True)
    await pi.db.commit()
    count = await business_db.scalar(
        select(func.count()).select_from(CustomerFile).where(CustomerFile.message_id == inbound.id)
    )
    entries = await business_db.scalar(
        select(func.count())
        .select_from(CustomerActivity)
        .where(
            CustomerActivity.customer_id == conversation.customer_id,
            CustomerActivity.summary.like("Document received%"),
        )
    )
    assert count == 1 and entries == 1
    await pi.close()
