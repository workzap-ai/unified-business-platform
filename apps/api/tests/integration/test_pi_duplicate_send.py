"""Platform spec Book 4 5.3 and G29: the same text is not sent twice to one person within 24 hours
by something pi starts itself (a reminder); the reply to what the person just said always goes out.
Real database; the AI is mocked."""

from datetime import UTC, datetime, timedelta

import pytest
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiMessage
from app.modules.pi.runtime import is_duplicate_send

pytestmark = pytest.mark.integration

TEXT = "Of course, I'll reply in English from here. What's your business name?"


def outbound(scope, conversation, key, status, body):
    return PiMessage(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        conversation_id=conversation.id,
        direction="outbound",
        sender_type="ai",
        body=body,
        status=status,
        idempotency_key=key,
    )


async def test_a_repeated_reminder_is_held_back_but_a_reply_never_is(api, business_db, monkeypatch):
    adaptive(monkeypatch, lambda context, n: turn(reply="Noted. Anything else?", language="en"))
    pi = await workspace(api, business_db)
    await say(pi, "stock runs out in two shops", "dup-1")
    conversation, scope = await pi.conversation(), pi.scope()
    sent = outbound(scope, conversation, "pi:anchor:1", "sent", TEXT)
    again = outbound(
        scope,
        conversation,
        "pi:anchor:2",
        "queued",
        "  of course, I'll reply in  ENGLISH from here. What's your business name? ",
    )
    reply = outbound(scope, conversation, "reply:abc", "queued", TEXT)
    other = outbound(
        scope, conversation, "pi:anchor:3", "queued", "Shall we carry on where we left off?"
    )
    business_db.add_all([sent, again, reply, other])
    await business_db.flush()

    assert await is_duplicate_send(business_db, again) is True
    assert await is_duplicate_send(business_db, reply) is False  # a reply is never held back
    assert await is_duplicate_send(business_db, other) is False

    sent.created_at = datetime.now(UTC) - timedelta(hours=25)
    await business_db.flush()
    assert await is_duplicate_send(business_db, again) is False  # older than 24 hours
    await pi.close()
