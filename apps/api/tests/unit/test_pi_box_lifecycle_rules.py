"""The Solution Box lifecycle: the guards that need no database (spec 5.3 to 5.7)."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.pi import box, box_lifecycle
from app.shared.errors import BusinessRuleViolation


def run(coro):
    return asyncio.run(coro)


class FakeSession:
    """Just enough session for `move`: it counts earlier moves to offered and records adds."""

    def __init__(self, offered_before: int = 0) -> None:
        self.offered_before = offered_before
        self.added: list = []

    async def scalar(self, *_a, **_k):
        return self.offered_before

    def add(self, row) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


def row(state: str, **extra):
    return SimpleNamespace(id=uuid4(), state=state, reviewer=None, offered_at=None, **extra)


def scope():
    from app.shared.scope import WorkspaceScope

    return WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")


def test_flag_off_means_off() -> None:
    assert box_lifecycle.enabled_for(None) is False
    assert box_lifecycle.enabled_for({"pi_mode": "brain"}) is False
    assert box_lifecycle.enabled_for({"pi_mode": "brain", "brain": {"box_offer": True}}) is True


def test_a_legal_move_writes_a_dated_transition() -> None:
    session, box_row = FakeSession(), row("collecting")
    at = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
    moved = run(box_lifecycle.move(session, scope(), box_row, "ready", "pi", now=at))
    assert (moved.from_state, moved.to_state) == ("collecting", "ready")
    assert box_row.state == "ready"
    written = session.added[0]
    assert (written.from_state, written.to_state, written.actor) == ("collecting", "ready", "pi")
    assert written.created_at == at


def test_an_illegal_move_is_refused_and_changes_nothing() -> None:
    session, box_row = FakeSession(), row("collecting")
    with pytest.raises(BusinessRuleViolation) as caught:
        run(box_lifecycle.move(session, scope(), box_row, "sent", "staff"))
    assert caught.value.code == "BOX_MOVE_REFUSED"
    assert box_row.state == "collecting" and session.added == []


def test_the_offer_is_made_once() -> None:
    with pytest.raises(BusinessRuleViolation, match="once"):
        run(
            box_lifecycle.move(
                FakeSession(offered_before=1), scope(), row("ready"), "offered", "pi"
            )
        )
    assert run(box_lifecycle.move(FakeSession(), scope(), row("ready"), "offered", "pi")).to_state


def test_drafting_needs_an_explicit_yes() -> None:
    with pytest.raises(BusinessRuleViolation, match="explicit yes"):
        run(box_lifecycle.move(FakeSession(), scope(), row("offered"), "drafting", "pi"))
    moved = run(
        box_lifecycle.move(
            FakeSession(), scope(), row("offered"), "drafting", "pi", explicit_yes=True
        )
    )
    assert moved.to_state == "drafting"


@pytest.mark.parametrize("actor", ["pi", "owner"])
def test_only_staff_sends(actor: str) -> None:
    with pytest.raises(BusinessRuleViolation):
        run(
            box_lifecycle.move(
                FakeSession(), scope(), row("in_review"), "sent", actor,
                actor_ref="reviewer", approved_document=True,
            )
        )  # fmt: skip


def test_sent_needs_an_approved_document_and_a_named_reviewer() -> None:
    for kwargs in ({"actor_ref": "r1"}, {"approved_document": True}):
        with pytest.raises(BusinessRuleViolation, match="reviewer"):
            run(
                box_lifecycle.move(
                    FakeSession(), scope(), row("in_review"), "sent", "staff", **kwargs
                )
            )
    box_row = row("in_review")
    run(
        box_lifecycle.move(
            FakeSession(), scope(), box_row, "sent", "staff",
            actor_ref="r1", approved_document=True,
        )
    )  # fmt: skip
    assert box_row.state == "sent" and box_row.reviewer == "r1"


def test_decline_quiet_window_counts_eight_pi_messages() -> None:
    brief = {box_lifecycle.DECLINE_KEY: 5}
    assert box_lifecycle.quiet_after_decline(brief, 12) is True
    assert box_lifecycle.quiet_after_decline(brief, 13) is False
    assert box_lifecycle.quiet_after_decline({}, 0) is False


def test_offer_facts_hold_the_offer_for_eight_messages_after_a_decline() -> None:
    def ctx(ai_after: int):
        history = [{"role": "ai", "at": "2026-10-28 09:00"}] * 8 + [
            {"role": "ai", "at": "2026-10-28 10:05"}
        ] * ai_after
        return {
            "noted_problems": [{"since": "x", "raised_voluntarily": True}] * 3,
            "brief": {"map_reviewed": True, "ranked": True, "box_declined_at": "2026-10-28 10:00"},
            "history": history,
        }

    assert box.offer_facts(ctx(3)).declined_recently is True
    assert box.offer_facts(ctx(8)).declined_recently is False
