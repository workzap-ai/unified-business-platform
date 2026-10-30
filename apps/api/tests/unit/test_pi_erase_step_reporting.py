"""Erase never reports success silently (audit of 0198c68): a step that cannot run is named in
removed["_skipped"] and logged, every step has its own savepoint, every count is always present, the
share-link delete is bounded to this workspace's conversations, and the all-chat share links are not
touched (erase decision R1 (share links) open). A fake session stands in for the database:
these tests check the statements and the reporting, not the SQL result."""

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError

from app.modules.pi import brain_erase, brain_erase_routes
from app.modules.pi.box_models import PiBoxTransition, PiMapVersion, PiOfferLog, PiSolutionBox
from app.modules.pi.business_profile_models import PiBusinessProfile
from app.modules.pi.open_item_models import PiOpenItem
from app.modules.pi.solution_models import PiIdeaFeedback, PiSolutionMemory
from app.shared.scope import WorkspaceScope


class PgError(Exception):
    """A database driver error that carries its SQLSTATE (asyncpg: sqlstate)."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__("db error")
        self.sqlstate = sqlstate


class PsycopgError(Exception):
    """The psycopg variant: the SQLSTATE is called pgcode."""

    def __init__(self, pgcode: str) -> None:
        super().__init__("db error")
        self.pgcode = pgcode


def failure(sql: str, sqlstate: str | None = "42P01") -> ProgrammingError:
    """A ProgrammingError whose driver error carries `sqlstate`; None means unreadable."""
    orig = PgError(sqlstate) if sqlstate else Exception("db error")
    return ProgrammingError(sql, {}, orig)


class Savepoint:
    def __init__(self, owner: "FakeSession") -> None:
        self.owner = owner

    async def __aenter__(self) -> None:
        self.owner.savepoints += 1

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeSession:
    def __init__(self, fail_on: tuple[str, ...] = (), raises: Any = None) -> None:
        self.fail_on = fail_on
        self.raises = raises or failure
        self.savepoints = 0
        self.statements: list[str] = []

    def begin_nested(self) -> Savepoint:
        return Savepoint(self)

    async def execute(self, statement: object) -> SimpleNamespace:
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        for marker in self.fail_on:
            if marker in sql:
                raise self.raises(sql)
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

    def __init__(self, fail_on: tuple[str, ...] = (), raises: Any = None) -> None:
        super().__init__(fail_on, raises)
        self.conversation_id = uuid4()

    async def scalars(self, statement: object) -> list[object]:
        sql = " ".join(str(statement).split())
        for marker in self.fail_on:
            if marker in sql:
                raise self.raises(sql)
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
            "complete": False,
            "skipped": ["offer_log"],
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


# ---- only an undefined table (SQLSTATE 42P01) may be skipped; everything else fails the request


async def test_the_skip_log_carries_the_step_and_the_sqlstate_and_no_statement(caplog):
    session = FakeSession(fail_on=("DELETE FROM pi_pending_actions",))
    with caplog.at_level(logging.WARNING, logger=brain_erase.logger.name):
        await texts(session)
    (record,) = [r for r in caplog.records if r.getMessage() == "pi_erase_step_skipped"]
    assert record.step == "pending_actions" and record.sqlstate == "42P01"
    assert "DELETE" not in record.getMessage() and not hasattr(record, "statement")


def test_the_sqlstate_is_read_from_asyncpg_psycopg_and_a_chained_cause():
    assert brain_erase._sqlstate(ProgrammingError("x", {}, PgError("42P01"))) == "42P01"
    assert brain_erase._sqlstate(ProgrammingError("x", {}, PsycopgError("42P01"))) == "42P01"
    chained = Exception("wrapper")
    chained.__cause__ = PgError("42P01")
    assert brain_erase._sqlstate(ProgrammingError("x", {}, chained)) == "42P01"
    assert brain_erase._sqlstate(ProgrammingError("x", {}, Exception("none"))) is None


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        pytest.param(lambda sql: failure(sql, "42703"), ProgrammingError, id="undefined column"),
        pytest.param(lambda sql: failure(sql, "42501"), ProgrammingError, id="permission denied"),
        pytest.param(lambda sql: failure(sql, None), ProgrammingError, id="no readable sqlstate"),
        pytest.param(
            lambda sql: IntegrityError(sql, {}, PgError("23503")), IntegrityError, id="integrity"
        ),
        pytest.param(lambda sql: DataError(sql, {}, PgError("22001")), DataError, id="data"),
        pytest.param(lambda sql: RuntimeError("boom"), RuntimeError, id="any other exception"),
    ],
)
async def test_any_other_error_propagates_so_nothing_is_committed(make, expected):
    marker = "DELETE FROM pi_pending_actions"
    session = WholeEraseSession(fail_on=(marker,), raises=make)
    with pytest.raises(expected) as caught:
        await brain_erase.erase_customer(session, scope(), uuid4())
    assert type(caught.value) is expected  # exactly this type: not wrapped, not swallowed
    assert any(marker in sql for sql in session.statements)  # the failing step was reached
    # and the erase stopped there: no later step ran
    assert not any(sql.startswith("UPDATE pi_tasks") for sql in session.statements)


async def test_a_step_runner_failure_that_is_not_a_missing_table_is_never_counted_as_skipped():
    session = FakeSession(
        fail_on=("DELETE FROM pi_pending_actions",), raises=lambda sql: failure(sql, "42703")
    )
    with pytest.raises(ProgrammingError):
        await texts(session)


async def test_the_hypotheses_deletion_is_counted():
    result = await brain_erase.erase_customer(WholeEraseSession(), scope(), uuid4())
    assert "hypotheses" in brain_erase.REMOVED_KEYS and result["removed"]["hypotheses"] == 2


async def test_erase_customer_says_complete_when_nothing_was_skipped_and_incomplete_otherwise():
    clean = await brain_erase.erase_customer(WholeEraseSession(), scope(), uuid4())
    assert clean["complete"] is True and clean["skipped"] == []
    marker = f"DELETE FROM {PiOfferLog.__tablename__}"
    partial = await brain_erase.erase_customer(
        WholeEraseSession(fail_on=(marker,)), scope(), uuid4()
    )
    assert partial["complete"] is False and partial["skipped"] == ["offer_log"]


async def route_run(monkeypatch, fake_erase):
    seen: dict[str, object] = {}

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
    return seen, Session()


async def test_the_response_says_incomplete_with_the_skipped_steps_and_still_commits(monkeypatch):
    async def fake_erase(session, scope, customer_id):
        return {
            "removed": {"problems": 1, "_skipped": ["offer_log"]},
            "kept": {"documents": 0, "payments": 0},
            "kept_reasons": {},
            "conversations": 1,
            "complete": False,
            "skipped": ["offer_log"],
        }

    seen, session = await route_run(monkeypatch, fake_erase)
    result = await brain_erase_routes.erase(
        uuid4(), brain_erase_routes.EraseInput(confirm=True), scope(), session
    )
    assert result["complete"] is False and result["skipped"] == ["offer_log"]
    assert "INCOMPLETE" in result["warning"] and "offer_log" in result["warning"]
    assert seen["details"]["complete"] is False and seen["details"]["skipped"] == ["offer_log"]
    assert seen["committed"] is True  # only a missing table was skipped: the rest is erased


async def test_a_complete_erase_has_no_warning(monkeypatch):
    async def fake_erase(session, scope, customer_id):
        return {
            "removed": {"problems": 1, "_skipped": []},
            "kept": {},
            "kept_reasons": {},
            "conversations": 1,
            "complete": True,
            "skipped": [],
        }

    seen, session = await route_run(monkeypatch, fake_erase)
    result = await brain_erase_routes.erase(
        uuid4(), brain_erase_routes.EraseInput(confirm=True), scope(), session
    )
    assert result["complete"] is True and "warning" not in result
    assert seen["details"]["complete"] is True


async def test_a_failing_erase_neither_records_nor_commits(monkeypatch):
    async def fake_erase(session, scope, customer_id):
        raise failure("UPDATE pi_tasks", "42703")

    seen, session = await route_run(monkeypatch, fake_erase)
    with pytest.raises(ProgrammingError):
        await brain_erase_routes.erase(
            uuid4(), brain_erase_routes.EraseInput(confirm=True), scope(), session
        )
    assert "event" not in seen and "committed" not in seen
