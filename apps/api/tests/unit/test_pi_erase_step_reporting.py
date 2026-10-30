"""Erase never reports success silently (audit of 0198c68): a step that cannot run is named in
removed["_skipped"] and logged, every step has its own savepoint, every count is always present, the
share-link delete is bounded to this workspace's conversations, and the all-chat share links are not
touched (erase decision R1 (share links) open). A fake session stands in for the database:
these tests check the statements and the reporting, not the SQL result."""

import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import ProgrammingError

from app.modules.pi import brain_erase, brain_erase_routes
from app.modules.pi.box_models import PiBoxTransition, PiMapVersion, PiOfferLog, PiSolutionBox
from app.modules.pi.business_profile_models import PiBusinessProfile
from app.modules.pi.open_item_models import PiOpenItem
from app.modules.pi.solution_models import PiIdeaFeedback, PiSolutionMemory
from app.shared.scope import WorkspaceScope


class Savepoint:
    def __init__(self, owner: "FakeSession") -> None:
        self.owner = owner

    async def __aenter__(self) -> None:
        self.owner.savepoints += 1

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeSession:
    def __init__(self, fail_on: tuple[str, ...] = ()) -> None:
        self.fail_on = fail_on
        self.savepoints = 0
        self.statements: list[str] = []

    def begin_nested(self) -> Savepoint:
        return Savepoint(self)

    async def execute(self, statement: object) -> SimpleNamespace:
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        for marker in self.fail_on:
            if marker in sql:
                raise ProgrammingError(sql, {}, Exception("relation does not exist"))
        return SimpleNamespace(rowcount=2)


def scope() -> WorkspaceScope:
    return WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")


async def texts(session: FakeSession):
    return await brain_erase._erase_workspace_texts(session, scope(), uuid4(), [uuid4()])


async def test_a_skipped_step_is_named_logged_and_counted_as_zero(caplog):
    session = FakeSession(fail_on=("DELETE FROM pi_pending_actions",))
    with caplog.at_level(logging.WARNING, logger=brain_erase.logger.name):
        counts, skipped = await texts(session)
    assert skipped == ["pending_actions"]
    assert counts["pending_actions"] == 0  # present, and honest: it did not run
    assert counts["tickets_cleared"] == 2  # the other steps ran and are counted
    records = [r for r in caplog.records if r.getMessage() == "pi_erase_step_skipped"]
    assert len(records) == 1 and records[0].step == "pending_actions"


async def test_nothing_skipped_reports_an_empty_list():
    counts, skipped = await texts(FakeSession())
    assert skipped == []
    assert all(value == 2 for value in counts.values())


async def test_every_step_has_its_own_savepoint():
    session = FakeSession()
    counts, _ = await texts(session)
    assert session.savepoints == len(counts) == len(session.statements)
    links = FakeSession()
    link_counts, _ = await brain_erase._erase_share_links(links, scope(), [uuid4()])
    assert links.savepoints == len(link_counts) == 1


async def test_every_reported_count_is_a_declared_key():
    counts, _ = await texts(FakeSession())
    link_counts, _ = await brain_erase._erase_share_links(FakeSession(), scope(), [uuid4()])
    assert set(counts) | set(link_counts) <= set(brain_erase.REMOVED_KEYS)
    assert len(set(brain_erase.REMOVED_KEYS)) == len(brain_erase.REMOVED_KEYS)


async def test_the_share_link_delete_can_only_match_this_workspaces_conversations():
    session = FakeSession()
    await brain_erase._erase_share_links(session, scope(), [uuid4()])
    (sql,) = session.statements
    assert sql.startswith("DELETE FROM customer_share_links")
    assert "pi_conversations" in sql  # a subquery on the conversations of this workspace
    assert "pi_conversations.tenant_id" in sql and "pi_conversations.environment_id" in sql


def test_the_all_chat_share_links_are_never_updated_or_revoked_here():
    source = (Path(brain_erase.__file__)).read_text(encoding="utf-8")
    assert "update(CustomerShareLink" not in source
    assert "share_links_revoked" not in source
    assert "share_links_all_chats" in source  # the residual risk is recorded


async def test_only_the_unresolved_pending_draft_is_deleted_the_others_are_blanked():
    session = FakeSession()
    await texts(session)
    delete_sql = next(s for s in session.statements if s.startswith("DELETE FROM pi_pending"))
    update_sql = next(s for s in session.statements if s.startswith("UPDATE pi_pending"))
    assert "pi_pending_actions.status =" in delete_sql
    assert "pi_pending_actions.status !=" in update_sql
    assert "payload" in update_sql and "summary" in update_sql


class WholeEraseSession(FakeSession):
    """What erase_customer needs from a session: selects return ids so the conversation steps run,
    and a marker raises ProgrammingError in the statement of one step (a missing table)."""

    def __init__(self, fail_on: tuple[str, ...] = ()) -> None:
        super().__init__(fail_on)
        self.conversation_id = uuid4()

    async def scalars(self, statement: object) -> list[object]:
        sql = " ".join(str(statement).split())
        for marker in self.fail_on:
            if marker in sql:
                raise ProgrammingError(sql, {}, Exception("relation does not exist"))
        if sql.startswith("SELECT pi_conversations.id"):
            return [self.conversation_id]
        if sql.startswith("SELECT pi_messages.id"):
            return [uuid4()]
        return []


# (a statement of the step that cannot run, the step name it must be reported under)
SKIP_CASES = [
    (f"DELETE FROM {PiSolutionMemory.__tablename__}", "solution_memory"),
    (f"DELETE FROM {PiIdeaFeedback.__tablename__}", "idea_feedback"),
    (f"DELETE FROM {PiOfferLog.__tablename__}", "offer_log"),
    (f"DELETE FROM {PiOpenItem.__tablename__}", "open_items"),
    (f"DELETE FROM {PiBoxTransition.__tablename__}", "box_transitions"),
    (f"UPDATE {PiSolutionBox.__tablename__}", "box_links_cleared"),
    (f"DELETE FROM {PiSolutionBox.__tablename__}", "solution_boxes"),
    (f"DELETE FROM {PiMapVersion.__tablename__}", "map_versions"),
    (f"FROM {PiBusinessProfile.__tablename__}", "business_profiles"),
]


async def test_erase_customer_with_nothing_skipped_reports_an_empty_list_and_every_key():
    result = await brain_erase.erase_customer(WholeEraseSession(), scope(), uuid4())
    removed = result["removed"]
    assert removed["_skipped"] == []
    assert set(brain_erase.REMOVED_KEYS) <= set(removed)
    assert result["kept_reasons"]["share_links_all_chats"]


@pytest.mark.parametrize(("marker", "step"), SKIP_CASES)
async def test_erase_customer_names_every_step_that_could_not_run(marker, step, caplog):
    session = WholeEraseSession(fail_on=(marker,))
    with caplog.at_level(logging.WARNING, logger=brain_erase.logger.name):
        result = await brain_erase.erase_customer(session, scope(), uuid4())
    removed = result["removed"]
    assert removed["_skipped"] == [step]  # named, once, and nothing else was dropped
    assert removed[step] == 0
    assert removed["tickets_cleared"] == 2 and removed["problems"] == 2  # the other steps ran
    assert [r.step for r in caplog.records if r.getMessage() == "pi_erase_step_skipped"] == [step]


async def test_two_skipped_steps_in_different_groups_are_both_reported():
    markers = tuple(marker for marker, _ in SKIP_CASES[:1] + SKIP_CASES[-1:])
    result = await brain_erase.erase_customer(WholeEraseSession(fail_on=markers), scope(), uuid4())
    assert sorted(result["removed"]["_skipped"]) == ["business_profiles", "solution_memory"]


async def test_the_audit_record_carries_kept_reasons_and_the_skipped_steps(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_erase(session, scope, customer_id):
        return {
            "removed": {"problems": 1, "_skipped": ["offer_log"]},
            "kept": {"documents": 0, "payments": 0},
            "kept_reasons": {"share_links_all_chats": "erase decision R1 (share links)"},
            "conversations": 1,
        }

    async def fake_record(session, event, **kwargs):
        seen["event"], seen["details"] = event, kwargs["details"]

    async def fake_require(session, scope, permission):
        return None

    class Session:
        async def commit(self) -> None:
            seen["committed"] = True

    monkeypatch.setattr(brain_erase_routes, "erase_customer", fake_erase)
    monkeypatch.setattr(brain_erase_routes, "record", fake_record)
    monkeypatch.setattr(brain_erase_routes, "require_pi", fake_require)
    result = await brain_erase_routes.erase(
        uuid4(), brain_erase_routes.EraseInput(confirm=True), scope(), Session()
    )
    details = seen["details"]
    assert seen["event"] == "pi.brain_data_erased" and seen["committed"] is True
    assert details["skipped"] == ["offer_log"]
    assert details["kept_reasons"]["share_links_all_chats"].startswith("erase decision R1")
    assert details["removed"]["problems"] == 1 and result["removed"]["_skipped"] == ["offer_log"]
