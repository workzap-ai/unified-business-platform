"""Every brain reply is stamped with the prompt, pack and build versions that produced it
(platform spec A.2 #8, A.8 check 4). Real database; the AI and WhatsApp are mocked."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi import learning_audit
from app.modules.pi.learning_models import PiReplyAudit

pytestmark = pytest.mark.integration


async def test_a_brain_reply_carries_its_prompt_and_build_version(api, business_db, monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123def4567890")
    adaptive(
        monkeypatch,
        lambda context, n: turn(reply="Thanks. What else is getting in the way?", language="en"),
    )
    pi = await workspace(api, business_db)
    await say(pi, "stock runs out in two shops", "stamp-1")
    reply = await pi.reply_to("stamp-1")
    row = await business_db.scalar(select(PiReplyAudit).where(PiReplyAudit.message_id == reply.id))
    assert row is not None
    assert row.prompt_version == learning_audit.prompt_version()
    assert row.pack_versions["build"] == "abc123def456"
    await pi.close()
