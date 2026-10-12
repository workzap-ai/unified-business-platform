"""pi knows the customer: what they say about themselves (name, business) is saved to
their record and kept for every later chat, so a returning customer is never asked
again."""

import json

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.customers.models import Customer
from app.modules.pi.models import PiConversation

pytestmark = pytest.mark.integration


async def test_the_customer_is_remembered_across_chats(api, business_db, monkeypatch):
    contexts = mock_turns(
        monkeypatch,
        turn(
            reply="Nice to meet you Ali! What does Crescent Bakers need?",
            customer_profile={
                "name": "Ali Raza",
                "business_name": "Crescent Bakers",
                "business_type": "Bakery in Lahore selling cakes",
            },
        ),
        turn(reply="Welcome back Ali! How can I help Crescent Bakers today?"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Hi, I'm Ali from Crescent Bakers, a bakery in Lahore", "prof-1")
    first = json.loads(contexts[0])
    assert first["returning_customer"] is False

    conversation = await pi.conversation()
    customer = await business_db.scalar(
        select(Customer).where(Customer.id == conversation.customer_id)
    )
    assert customer.name == "Ali Raza" and customer.company == "Crescent Bakers"
    assert conversation.service_brief["customer_profile"]["business_type"].startswith("Bakery")

    # A later chat (the first one closed): pi already knows who this is.
    row = await business_db.get(PiConversation, conversation.id)
    row.status = "closed"
    await business_db.commit()
    await pi.process("Hello again", "prof-2")
    later = json.loads(contexts[1])
    assert later["returning_customer"] is True
    assert later["customer_profile"]["business_name"] == "Crescent Bakers"
    assert later["customer_profile"]["name"] == "Ali Raza"
    await pi.close()
