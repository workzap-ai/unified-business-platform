"""PI Meeting Brain data layer on a real database (migration 0057): rows are workspace scoped, the
database refuses an AI conclusion that claims to be stated, a replayed import writes nothing twice,
transcript search finds words as written, and erasing a customer removes their meetings (and only
theirs) while returning the recording keys that still have to leave the object store."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from test_pi_pipeline import pi_workspace

from app.modules.pi import brain_erase
from app.modules.pi.models import PiMessage
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingInsight,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


async def workspace(api, db, number):
    pi = await pi_workspace(api, db, number=number)
    await pi.process("My shop stock keeps running out", f"mtg-{number}")
    conversation = await pi.conversation()
    scope = WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )
    assert await db.scalar(
        select(PiMessage.id).where(PiMessage.conversation_id == conversation.id).limit(1)
    )
    return pi, conversation, scope


def meeting(scope, customer_id, **kw):
    return PiMeeting(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        title=kw.pop("title", "Kickoff call"),
        **kw,
    )


def insight(scope, meeting_id, **kw):
    values = dict(kind="problem", basis="stated", text="stock runs out", confidence=80)
    values.update(kw)
    return PiMeetingInsight(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting_id,
        **values,
    )


async def count(db, model, scope):
    return await db.scalar(
        select(func.count())
        .select_from(model)
        .where(model.tenant_id == scope.tenant_id, model.environment_id == scope.environment_id)
    )


async def test_the_database_refuses_an_ai_conclusion_that_claims_to_be_stated(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "311111111")
    m = meeting(scope, conv.customer_id)
    business_db.add(m)
    await business_db.flush()
    # a stated item may carry who and when
    business_db.add(insight(scope, m.id, owner_label="Customer", due_text="by Friday"))
    await business_db.flush()
    # an inferred one may not: that would present a guess as something the customer said
    for bad in (
        {"basis": "inferred", "owner_label": "Customer"},
        {"basis": "estimate", "due_text": "next week"},
        {"basis": "recommendation", "owner_label": "Staff", "due_text": "soon"},
    ):
        with pytest.raises(IntegrityError):
            async with business_db.begin_nested():
                business_db.add(insight(scope, m.id, **bad))
                await business_db.flush()
    # an unknown basis or kind, and a confidence outside 0..100, are refused too
    for bad in ({"basis": "certain"}, {"kind": "gossip"}, {"confidence": 101}):
        with pytest.raises(IntegrityError):
            async with business_db.begin_nested():
                business_db.add(insight(scope, m.id, **bad))
                await business_db.flush()
    assert await count(business_db, PiMeetingInsight, scope) == 1
    await pi.close()


async def test_a_meeting_cannot_point_at_another_workspaces_customer(api, business_db):
    pi_a, conv_a, scope_a = await workspace(api, business_db, "322222222")
    pi_b, conv_b, scope_b = await workspace(api, business_db, "333333333")
    with pytest.raises(IntegrityError):
        async with business_db.begin_nested():
            # workspace A's scope with workspace B's customer: the composite key refuses it
            business_db.add(meeting(scope_a, conv_b.customer_id))
            await business_db.flush()
    await pi_a.close()
    await pi_b.close()


async def test_the_same_external_meeting_is_imported_once_and_search_finds_words(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "344444444")
    first = meeting(scope, conv.customer_id, source="zoom", external_ref="zoom-123")
    business_db.add(first)
    await business_db.flush()
    with pytest.raises(IntegrityError):
        async with business_db.begin_nested():
            business_db.add(
                meeting(scope, conv.customer_id, source="zoom", external_ref="zoom-123")
            )
            await business_db.flush()
    # a different source may reuse the reference; a meeting without one is never deduped
    business_db.add(meeting(scope, conv.customer_id, source="meet", external_ref="zoom-123"))
    business_db.add(meeting(scope, conv.customer_id))
    business_db.add(meeting(scope, conv.customer_id))
    await business_db.flush()

    label = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=first.id,
        label="Speaker 1",
    )
    business_db.add(label)
    await business_db.flush()
    for ordinal, said in enumerate(["hamari dukaan mein stock khatam ho jata hai", "ok theek hai"]):
        business_db.add(
            PiMeetingSegment(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=first.id,
                ordinal=ordinal,
                start_ms=ordinal * 1000,
                end_ms=ordinal * 1000 + 900,
                participant_id=label.id,
                text=said,
            )
        )
    await business_db.flush()
    found = list(
        await business_db.scalars(
            select(PiMeetingSegment.ordinal).where(
                PiMeetingSegment.tenant_id == scope.tenant_id,
                PiMeetingSegment.tsv.op("@@")(func.plainto_tsquery("simple", "khatam")),
            )
        )
    )
    assert found == [0]
    # a segment ordinal is unique within a meeting and a segment never ends before it starts
    for bad in ({"ordinal": 0}, {"ordinal": 5, "start_ms": 900, "end_ms": 100}):
        values = dict(ordinal=9, start_ms=0, end_ms=10, text="x") | bad
        with pytest.raises(IntegrityError):
            async with business_db.begin_nested():
                business_db.add(
                    PiMeetingSegment(
                        tenant_id=scope.tenant_id,
                        environment_id=scope.environment_id,
                        meeting_id=first.id,
                        **values,
                    )
                )
                await business_db.flush()
    await pi.close()


async def test_erasing_a_customer_removes_their_meetings_and_only_theirs(api, business_db):
    pi_a, conv_a, scope_a = await workspace(api, business_db, "355555555")
    pi_b, conv_b, scope_b = await workspace(api, business_db, "366666666")
    mine = meeting(scope_a, conv_a.customer_id, recording_key="t/a/rec-1.webm")
    other = meeting(scope_b, conv_b.customer_id, recording_key="t/b/rec-9.webm")
    business_db.add_all([mine, other])
    await business_db.flush()
    for scope, m in ((scope_a, mine), (scope_b, other)):
        speaker = PiMeetingParticipant(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            meeting_id=m.id,
            label="Speaker 1",
        )
        business_db.add(speaker)
        await business_db.flush()
        business_db.add_all(
            [
                PiMeetingSegment(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    meeting_id=m.id,
                    ordinal=0,
                    start_ms=0,
                    end_ms=500,
                    participant_id=speaker.id,
                    text="stock runs out",
                ),
                insight(scope, m.id, participant_id=speaker.id),
            ]
        )
    await business_db.flush()

    result = await brain_erase.erase_customer(business_db, scope_a, conv_a.customer_id)
    removed = result["removed"]
    assert removed["meetings"] == 1 and removed["meeting_segments"] == 1
    assert removed["meeting_insights"] == 1 and removed["meeting_participants"] == 1
    assert removed["meeting_recordings_to_delete"] == 1
    assert result["meeting_object_keys"] == ["t/a/rec-1.webm"]
    assert "meetings" not in removed["_skipped"] and result["complete"]
    for model in (PiMeeting, PiMeetingSegment, PiMeetingInsight, PiMeetingParticipant):
        assert await count(business_db, model, scope_a) == 0
        assert await count(business_db, model, scope_b) == 1  # the other workspace is untouched
    await pi_a.close()
    await pi_b.close()


async def test_erasing_unmaps_a_speaker_mapped_to_the_customer_in_another_meeting(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "377777777")
    m = meeting(scope, None, title="Unlinked call")
    business_db.add(m)
    await business_db.flush()
    speaker = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=m.id,
        label="Speaker 2",
        role="customer",
        mapped_customer_id=conv.customer_id,
    )
    business_db.add(speaker)
    await business_db.flush()
    await brain_erase.erase_customer(business_db, scope, conv.customer_id)
    mapped = await business_db.scalar(
        text("select mapped_customer_id from pi_meeting_participants where id = :i").bindparams(
            i=speaker.id
        )
    )
    assert mapped is None
    # the meeting itself stays: it was never this customer's
    assert await count(business_db, PiMeeting, scope) == 1
    await pi.close()
