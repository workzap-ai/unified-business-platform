"""A WhatsApp send error stays on the connection only while it's real: the next message
that goes through clears it. A billing pause is only over once a paid (template)
message goes out, because free replies inside the 24-hour window always send."""

from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.pi.models import WhatsAppConnection

pytestmark = pytest.mark.integration


async def _connection(pi) -> WhatsAppConnection:
    return await pi.db.scalar(
        select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == UUID(pi.tenant_id))
    )


async def test_a_send_that_goes_through_clears_an_old_error(api, business_db, monkeypatch):
    mock_turns(monkeypatch, turn(), turn())
    pi = await pi_workspace(api, business_db, business_type="service_business")
    connection = await _connection(pi)
    connection.last_error_code = "WHATSAPP_REJECTED"
    await pi.db.commit()
    await pi.process("Website chahiye", "send-ok-1")
    await pi.deliver_all()
    await pi.db.refresh(connection)
    assert connection.last_error_code is None

    # A free reply going out doesn't prove billing works again.
    connection.last_error_code = "WHATSAPP_BILLING_PAUSED"
    await pi.db.commit()
    await pi.process("Online shop", "send-ok-2")
    await pi.deliver_all()
    await pi.db.refresh(connection)
    assert connection.last_error_code == "WHATSAPP_BILLING_PAUSED"
    await pi.close()
