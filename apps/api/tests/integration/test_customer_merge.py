"""Duplicate customers: the WhatsApp one and one typed in by hand are found as the same
person, and merging moves the chat, deals and notes to one record."""

from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import _customer_in_chat, _lead
from test_pi_pipeline import pi_workspace

from app.modules.customers.models import Customer
from app.modules.pi.models import PiConversation
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration
CUSTOMERS = "/api/v1/customers"


async def test_the_hand_typed_duplicate_is_found_and_merged(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    whatsapp_id, conversation = await _customer_in_chat(pi)  # "Ayesha Khan", with phone
    typed = (await api.post(CUSTOMERS, json={"name": "Aysha", "company": "Crescent Bakers"})).json()
    lead_id = await _lead(pi, typed["id"], conversation)  # a deal made on the typed one
    note = await api.post(f"{CUSTOMERS}/{typed['id']}/notes", json={"body": "Called him"})
    assert note.status_code == 201, note.text
    await api.post(CUSTOMERS, json={"name": "Bilal Ahmed"})  # someone else

    found = (await api.get(f"{CUSTOMERS}/{whatsapp_id}/duplicates")).json()
    assert [d["customer"]["id"] for d in found] == [typed["id"]]
    assert found[0]["reason"].startswith("Similar name")

    merged = await api.post(f"{CUSTOMERS}/{whatsapp_id}/merge", json={"duplicate_id": typed["id"]})
    assert merged.status_code == 200, merged.text
    kept = merged.json()
    assert kept["name"] == "Ayesha Khan" and kept["company"] == "Crescent Bakers"
    assert kept["phone"]  # the WhatsApp number stays
    assert await business_db.get(Customer, UUID(typed["id"])) is None
    lead = await business_db.get(SalesLead, UUID(lead_id))
    await business_db.refresh(lead)
    assert str(lead.customer_id) == whatsapp_id
    chat = await business_db.scalar(
        select(PiConversation).where(PiConversation.id == conversation.id)
    )
    assert str(chat.customer_id) == whatsapp_id
    notes = (await api.get(f"{CUSTOMERS}/{whatsapp_id}/notes")).json()["items"]
    assert any(n["body"] == "Called him" for n in notes)
    assert (await api.get(f"{CUSTOMERS}/{whatsapp_id}/duplicates")).json() == []
    same = await api.post(f"{CUSTOMERS}/{whatsapp_id}/merge", json={"duplicate_id": whatsapp_id})
    assert same.status_code == 422
    await pi.close()


def test_who_looks_like_the_same_person():
    from app.modules.customers.merge import likeness

    def c(name, company=None, phone=None):
        return Customer(name=name, company=company, phone=phone, tags=[])

    assert likeness(c("Mukarram Hazari"), c("Mukkaram", "Hazari Impex"))
    assert likeness(c("Ali Khan", phone="+923001112233"), c("A.K.", phone="03001112233"))
    assert likeness(c("Ali Khan"), c("Bilal Ahmed")) is None
    assert likeness(c("Saqib K"), c("Sara K")) is None
