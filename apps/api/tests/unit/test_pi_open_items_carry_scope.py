"""Q-6: where the open items (platform spec v1.4, 17.7) are read, written, carried and erased.

What the tests pin, by running the real `open_items`, `slot_carry` and `third_party` code against a
recording fake session (no database): the scope of every query, the carry of an item into a NEW
chat of the same customer (Q6-1), the tenant, environment and customer walls, the erase of an item,
and the redaction of the stored words, including a third party's name from its words (Q6-2).

One test stays an expected failure on purpose (strict xfail): a bare third-party name with nothing
around it. The fake session only evaluates the clauses these functions use (==, !=, >=, <=, IN,
ORDER BY, LIMIT); it does not prove the SQL against a real database (see the integration file).
"""

import logging
import operator
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.sql.operators import desc_op, in_op
from sqlalchemy.sql.selectable import Select

from app.modules.pi import brain_erase, open_items, open_requests, slot_carry, third_party
from app.modules.pi.open_item_models import PiOpenItem
from app.shared.scope import WorkspaceScope

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
QUESTION = "how long will the delivery of my order take to Lahore"
NO_MATCH = object()
QUIET = timedelta(hours=10)  # an earlier chat that has been quiet long enough to carry from


def scope(tenant: UUID | None = None, environment: UUID | None = None) -> WorkspaceScope:
    return WorkspaceScope(
        tenant_id=tenant or uuid4(), environment_id=environment or uuid4(), permissions=frozenset()
    )


def chat(
    scope_: WorkspaceScope,
    customer: UUID | None = None,
    chat_id: UUID | None = None,
    *,
    quiet_for: timedelta = QUIET,
):
    return SimpleNamespace(
        id=chat_id or uuid4(),
        customer_id=customer or uuid4(),
        tenant_id=scope_.tenant_id,
        environment_id=scope_.environment_id,
        service_brief={},
        last_message_at=NOW - quiet_for,
    )


def item(
    chat_: Any,
    *,
    kind: str = "owner_question",
    text: str = QUESTION,
    status: str = "open",
    created: datetime = NOW - timedelta(hours=6),
    surfaced: datetime | None = None,
    key: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=chat_.tenant_id,
        environment_id=chat_.environment_id,
        conversation_id=chat_.id,
        customer_id=chat_.customer_id,
        kind=kind,
        key=key or f"q:{uuid4()}",
        text=text,
        status=status,
        created_at=created,
        surfaced_at=surfaced,
        source_message_id=uuid4(),
        ref_id=None,
    )


def _criteria(statement: Any) -> list[tuple[str, Any, Any]]:
    found = []
    for clause in statement._where_criteria:
        name = clause.left.key
        value = clause.right.value
        found.append((name, clause.operator, value))
    return found


def _fits(row: Any, criteria: list[tuple[str, Any, Any]]) -> bool:
    for name, op, value in criteria:
        have = getattr(row, name, NO_MATCH)
        if have is NO_MATCH:
            return False
        if op is operator.eq and have != value:
            return False
        if op is operator.ne and have == value:
            return False
        if op is operator.ge and not have >= value:
            return False
        if op is operator.le and not have <= value:
            return False
        if op is in_op and have not in value:
            return False
        if op not in (operator.eq, operator.ne, operator.ge, operator.le, in_op):
            return False  # an operator this fake does not know must never pass silently
    return True


class _Nested:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeSession:
    """Only what `open_items`, `slot_carry` and `brain_erase._erase_conversation_extras` call. A
    statement is answered from `tables[name]` by its WHERE clauses; the clauses seen are kept."""

    def __init__(self, **tables: list[Any]) -> None:
        self.tables = tables
        self.added: list[Any] = []
        self.seen: list[list[tuple[str, Any, Any]]] = []

    def _rows(self, name: str) -> list[Any]:
        return self.tables.setdefault(name, [])

    def _found(self, statement: Any) -> list[Any]:
        name = statement.column_descriptions[0]["entity"].__tablename__
        criteria = _criteria(statement)
        self.seen.append(criteria)
        found = [r for r in self._rows(name) if _fits(r, criteria)]
        for clause in reversed(getattr(statement, "_order_by_clauses", ()) or ()):
            column = getattr(clause, "element", clause)  # a plain column sorts ascending
            found.sort(
                key=lambda r, k=column.key: getattr(r, k),
                reverse=getattr(clause, "modifier", None) is desc_op,
            )
        limit = getattr(statement, "_limit_clause", None)
        return found[: int(limit.value)] if limit is not None else found

    async def scalars(self, statement: Any) -> list[Any]:
        found = self._found(statement)
        described = statement.column_descriptions[0]
        if described["expr"] is described["entity"]:  # select(Model): the rows
            return found
        return [getattr(r, described["name"]) for r in found]  # select(Model.column): the values

    async def scalar(self, statement: Any) -> Any:
        found = await self.scalars(statement)
        return found[0] if found else None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def begin_nested(self) -> _Nested:
        return _Nested()

    async def execute(self, statement: Any) -> Any:
        if isinstance(statement, Select):
            names = [d["name"] for d in statement.column_descriptions]
            rows = [tuple(getattr(r, n) for n in names) for r in self._found(statement)]
            return SimpleNamespace(all=lambda: rows)
        name = statement.table.name
        criteria = _criteria(statement)
        self.seen.append(criteria)
        rows = self._rows(name)
        gone = [r for r in rows if _fits(r, criteria)]
        self.tables[name] = [r for r in rows if r not in gone]
        return SimpleNamespace(rowcount=len(gone))


async def named(session: FakeSession, scope_: WorkspaceScope, chat_: Any, hours: int = 6):
    return await open_items.load_for_return(session, scope_, chat_, hours_away=hours, now=NOW)


def world(items: list[Any], *chats: Any) -> FakeSession:
    """A fake workspace: these open items and these conversations."""
    return FakeSession(pi_open_items=list(items), pi_conversations=list(chats), pi_offer_log=[])


# --- the scope of the read -------------------------------------------------------------------


async def test_the_read_is_scoped_by_tenant_environment_conversation_and_status():
    s = scope()
    here = chat(s)
    session = FakeSession(pi_open_items=[item(here)])
    await named(session, s, here)
    [criteria] = session.seen
    assert {name for name, _, _ in criteria} == {
        "tenant_id",
        "environment_id",
        "conversation_id",
        "status",
    }
    assert ("status", operator.eq, "open") in criteria


async def test_an_open_item_of_this_chat_is_named_on_return_after_the_gap():
    s = scope()
    here = chat(s)
    session = FakeSession(pi_open_items=[item(here)])
    [one] = await named(session, s, here)
    assert one["kind"] == "owner_question" and one["text"] == QUESTION


async def test_nothing_is_named_before_the_gap_and_a_named_item_waits_four_hours():
    s = scope()
    here = chat(s)
    fresh = item(here, surfaced=NOW - timedelta(hours=1))
    session = FakeSession(pi_open_items=[fresh])
    assert await named(session, s, here, hours=3) == []  # not away long enough
    assert await named(session, s, here, hours=6) == []  # named one hour ago
    fresh.surfaced_at = NOW - timedelta(hours=5)
    assert len(await named(session, s, here, hours=6)) == 1


async def test_answered_and_dropped_items_are_never_named():
    s = scope()
    here = chat(s)
    session = FakeSession(
        pi_open_items=[item(here, status="answered"), item(here, status="dropped")]
    )
    assert await named(session, s, here) == []


# --- carry into a new chat (gap Q6-1) --------------------------------------------------------


async def carry(session: FakeSession, s: WorkspaceScope, new: Any) -> int:
    return await open_items.carry_into(session, s, new, now=NOW)


async def test_an_item_of_an_earlier_chat_of_the_same_customer_is_named_in_a_new_chat():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    session = world([item(earlier)], earlier, new)
    assert await carry(session, s, new) == 1
    assert len(await named(session, s, new)) == 1
    assert await named(session, s, earlier) == []  # one row, moved: never a copy


async def test_a_carried_item_is_under_the_new_conversation_keeps_its_age_and_loses_its_pointer():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    row = item(earlier, created=NOW - timedelta(days=12))
    session = world([row], earlier, new)
    await carry(session, s, new)
    assert row.conversation_id == new.id
    assert row.created_at == NOW - timedelta(days=12)  # the age limit counts from the ask
    assert row.source_message_id is None  # it pointed into the earlier chat


async def test_at_most_ten_are_carried_newest_first_and_the_rest_stay_behind():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    rows = [item(earlier, created=NOW - timedelta(hours=h + 1)) for h in range(12)]
    session = world(rows, earlier, new)
    assert open_items.CARRY_MAX == 10
    assert await carry(session, s, new) == 10
    moved = {r.id for r in rows if r.conversation_id == new.id}
    assert moved == {r.id for r in rows[:10]}  # rows[0] is the newest
    assert all(r.conversation_id == earlier.id for r in rows[10:])


async def test_the_cap_counts_what_the_new_chat_already_holds_and_comes_after_the_duplicates():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    held = [item(new, key=f"held:{i}") for i in range(3)]
    dupes = [item(earlier, key=f"held:{i}", created=NOW - timedelta(hours=i + 1)) for i in range(3)]
    others = [item(earlier, created=NOW - timedelta(hours=i + 10)) for i in range(9)]
    session = world([*held, *dupes, *others], earlier, new)
    assert await carry(session, s, new) == 7  # room is 10 minus the 3 held, duplicates skipped
    assert all(r.conversation_id == earlier.id for r in dupes)
    assert {r.id for r in others if r.conversation_id == new.id} == {r.id for r in others[:7]}
    assert await carry(session, s, new) == 0  # the chat is now full


async def test_equal_ages_are_ordered_by_id_so_the_choice_is_stable():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    held = [item(new, key=f"held:{i}") for i in range(9)]  # room for one
    a, b = item(earlier), item(earlier)  # the same creation time
    session = world([*held, a, b], earlier, new)
    assert await carry(session, s, new) == 1
    winner = max((a, b), key=lambda r: r.id)
    assert winner.conversation_id == new.id


async def test_the_thirty_day_limit_is_one_constant_and_its_boundary_holds():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    limit = timedelta(days=open_items.CARRY_DAYS)
    on_it = item(earlier, created=NOW - limit)
    past_it = item(earlier, created=NOW - limit - timedelta(seconds=1))
    session = world([on_it, past_it], earlier, new)
    assert open_items.CARRY_DAYS == 30
    assert await carry(session, s, new) == 1
    assert on_it.conversation_id == new.id and past_it.conversation_id == earlier.id


async def test_answered_dropped_and_expired_items_are_not_carried():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    rows = [
        item(earlier, status="answered"),
        item(earlier, status="dropped"),
        item(earlier, created=NOW - timedelta(days=45)),
    ]
    session = world(rows, earlier, new)
    assert await carry(session, s, new) == 0
    assert all(r.conversation_id == earlier.id for r in rows)


async def test_an_erased_item_is_not_carried():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    session = world([item(earlier)], earlier, new)
    await brain_erase._erase_conversation_extras(session, s, [earlier.id])
    assert await carry(session, s, new) == 0
    assert session.tables["pi_open_items"] == []


async def test_a_chat_that_is_still_active_is_not_raided():
    s = scope()
    customer = uuid4()
    gap = timedelta(hours=open_items.CARRY_IDLE_HOURS)
    busy = chat(s, customer, quiet_for=gap - timedelta(minutes=1))
    new = chat(s, customer)
    row = item(busy)
    session = world([row], busy, new)
    assert await carry(session, s, new) == 0 and row.conversation_id == busy.id
    busy.last_message_at = NOW - gap  # quiet for exactly the gap: it may be carried from
    assert await carry(session, s, new) == 1 and row.conversation_id == new.id


async def test_a_second_carry_moves_nothing_and_an_item_already_held_is_not_doubled():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    same = item(earlier, key="q:same")
    held = item(new, key="q:same")
    other = item(earlier, key="q:other")
    session = world([same, held, other], earlier, new)
    assert await carry(session, s, new) == 1
    assert same.conversation_id == earlier.id and other.conversation_id == new.id
    assert await carry(session, s, new) == 0


async def test_nothing_is_carried_without_a_customer():
    s = scope()
    new = chat(s)
    new.customer_id = None
    session = world([item(chat(s))], new)
    assert await carry(session, s, new) == 0


async def test_the_carry_reads_with_a_lock_so_two_new_chats_cannot_move_one_row_twice():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    seen: list[Any] = []

    class Spy(FakeSession):
        async def scalars(self, statement: Any) -> list[Any]:
            seen.append(statement)
            return await super().scalars(statement)

    session = Spy(pi_open_items=[item(earlier)], pi_conversations=[earlier, new], pi_offer_log=[])
    await carry(session, s, new)
    locking = [st for st in seen if getattr(st, "_for_update_arg", None) is not None]
    assert locking and locking[0]._for_update_arg.skip_locked is True


async def test_carried_requests_reach_the_brief_from_the_same_rows_and_are_not_doubled():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    new.service_brief = {"open_requests": [{"kind": "human", "turns": 2}]}
    rows = [
        item(earlier, kind="owner_request", key="timeline"),
        item(earlier, kind="owner_request", key="human"),  # already in the new brief
        item(earlier, kind="owner_request", key="quote_price"),  # not a tracked request kind
        item(earlier, kind="owner_question"),
    ]
    session = world(rows, earlier, new)
    assert await carry(session, s, new) == 4
    assert [e["kind"] for e in new.service_brief["open_requests"]] == ["human", "timeline"]
    assert new.service_brief["open_requests"][1] == {"kind": "timeline", "turns": 0}


async def test_a_carried_request_is_not_forced_into_the_first_reply_but_is_tracked_after():
    entry = {"kind": "timeline", "turns": 0}  # turns 0 marks a carried entry
    assert open_requests.unanswered([entry], "Hello again.") == []
    assert open_requests.unanswered([{"kind": "timeline", "turns": 1}], "Hello again.") == [
        "timeline"
    ]
    after = open_requests.update([entry], "ok", "Hmm.", persistent=True)
    assert after == [{"kind": "timeline", "turns": 1}]  # the next turn tracks it like any other


async def test_the_carry_never_crosses_tenant_environment_or_customer():
    mine = scope()
    customer = uuid4()
    new = chat(mine, customer)
    other_tenant = scope()
    other_env = scope(mine.tenant_id)
    foreign = [chat(other_tenant, customer), chat(other_env, customer), chat(mine)]
    rows = [item(c) for c in foreign]
    before = [(r.conversation_id, r.tenant_id, r.environment_id) for r in rows]
    session = world(rows, new, *foreign)
    assert await carry(session, mine, new) == 0
    assert [(r.conversation_id, r.tenant_id, r.environment_id) for r in rows] == before
    wanted = {"tenant_id", "environment_id", "customer_id"}
    assert all(wanted <= {name for name, _, _ in c} for c in session.seen[:1] + session.seen[1:2])


async def test_the_erase_of_the_new_conversation_alone_removes_the_carried_items():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    rows = [item(earlier), item(earlier)]
    session = world(rows, earlier, new)
    await carry(session, s, new)
    assert all(r.conversation_id == new.id for r in rows)
    removed = await brain_erase._erase_conversation_extras(session, s, [new.id])  # not the old id
    assert removed["open_items"] == 2 and session.tables["pi_open_items"] == []


# --- the team's answer closes a carried question (the staff request keeps the old chat id) ------


def staff_request(
    chat_: Any, *, status="answered", resolved=NOW - timedelta(hours=1), kind="question"
):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=chat_.tenant_id,
        environment_id=chat_.environment_id,
        customer_id=chat_.customer_id,
        conversation_id=chat_.id,
        kind=kind,
        status=status,
        resolved_at=resolved,
    )


async def settle(session: FakeSession, s: WorkspaceScope, new: Any, row: Any) -> None:
    message = SimpleNamespace(id=uuid4(), body="ok")
    await open_items.sync(
        session,
        s,
        new,
        message,
        reply="Understood.",
        language="en",
        request_human=False,
        knowledge_gaps=[],
        said_ids=[],
        now=NOW,
    )


async def test_the_teams_answer_closes_a_question_that_was_carried_into_a_new_chat():
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    row = item(earlier, created=NOW - timedelta(hours=5))
    session = world([row], earlier, new)
    session.tables["pi_staff_requests"] = [staff_request(earlier)]  # under the OLD conversation id
    await carry(session, s, new)
    assert row.conversation_id == new.id
    await settle(session, s, new, row)
    assert row.status == "answered" and row.closed_reason == "reply_answered"


@pytest.mark.parametrize(
    "case", ["other_customer", "other_tenant", "still_open", "too_early", "other_kind"]
)
async def test_a_staff_request_that_is_not_this_customers_answer_does_not_close_it(case):
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    row = item(earlier, created=NOW - timedelta(hours=5))
    request = {
        "other_customer": lambda: staff_request(chat(s)),
        "other_tenant": lambda: staff_request(chat(scope(), customer)),
        "still_open": lambda: staff_request(earlier, status="open"),
        "too_early": lambda: staff_request(earlier, resolved=NOW - timedelta(hours=9)),
        "other_kind": lambda: staff_request(earlier, kind="document_review"),
    }[case]()
    session = world([row], earlier, new)
    session.tables["pi_staff_requests"] = [request]
    await carry(session, s, new)
    await settle(session, s, new, row)
    assert row.status == "open"


# --- slot_carry itself ---------------------------------------------------------------------------


async def test_slot_carry_copies_the_slots_moves_the_items_and_sets_its_mark_once():
    s = scope()
    customer = uuid4()
    earlier = chat(s, customer)
    earlier.service_brief = {"closed_slots": [{"slot": "shops.where", "q": "Which shop is it?"}]}
    new = chat(s, customer)
    row = item(earlier)
    session = world([row], earlier, new)
    assert await slot_carry.carry_into(session, s, new, NOW) is True
    brief = new.service_brief
    assert brief[slot_carry.MARK] is True and brief["closed_slots"][0]["carried"] is True
    assert row.conversation_id == new.id
    assert await slot_carry.carry_into(session, s, new, NOW) is False  # made once


async def test_a_failed_item_carry_leaves_the_mark_unset_logs_ids_only_and_is_tried_again(caplog):
    s = scope()
    customer = uuid4()
    earlier, new = chat(s, customer), chat(s, customer)
    secret = "delivery to Gulberg for Mr Raza on 0300-1234567"
    row = item(earlier, text=secret)
    ok = world([row], earlier, new)

    class Broken(FakeSession):
        async def scalars(self, statement: Any) -> list[Any]:
            raise RuntimeError(secret)

    broken = Broken(pi_open_items=[row], pi_conversations=[earlier, new], pi_offer_log=[])
    with caplog.at_level(logging.WARNING):
        await slot_carry.carry_into(broken, s, new, NOW)
    assert slot_carry.MARK not in (new.service_brief or {})
    assert row.conversation_id == earlier.id
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in text and str(new.id) in text and "Gulberg" not in text
    assert not any(r.exc_info for r in caplog.records)  # no traceback with parameters
    await slot_carry.carry_into(ok, s, new, NOW)  # the next turn
    assert new.service_brief[slot_carry.MARK] is True and row.conversation_id == new.id


async def test_a_failure_in_the_item_carry_never_reaches_the_chat():
    s = scope()
    new = chat(s)

    class Broken(FakeSession):
        async def scalars(self, statement: Any) -> list[Any]:
            raise RuntimeError("database trouble")

    assert await slot_carry._carry_open_items(Broken(), s, new, NOW) is False


async def test_an_item_of_another_customer_is_never_named_here():
    """Must still hold after any carry fix: the customer is part of the wall."""
    s = scope()
    mine = chat(s)
    theirs = chat(s)  # another customer, another chat, same workspace
    session = FakeSession(pi_open_items=[item(theirs)])
    assert await named(session, s, mine) == []


# --- the tenant and environment walls ---------------------------------------------------------


async def test_the_same_conversation_and_customer_ids_in_another_workspace_are_not_named():
    mine, other = scope(), scope()
    shared_chat_id, shared_customer = uuid4(), uuid4()
    here = chat(mine, shared_customer, shared_chat_id)
    there = chat(other, shared_customer, shared_chat_id)  # a collision, on purpose
    session = FakeSession(pi_open_items=[item(there)])
    assert await named(session, mine, here) == []


async def test_another_environment_of_the_same_tenant_is_not_named():
    live = scope()
    test_env = scope(live.tenant_id)
    here = chat(live)
    there = chat(test_env, here.customer_id, here.id)
    session = FakeSession(pi_open_items=[item(there)])
    assert await named(session, live, here) == []


async def test_the_staff_age_view_lists_only_this_workspace():
    mine, other = scope(), scope()
    session = FakeSession(pi_open_items=[item(chat(mine)), item(chat(other))], pi_staff_requests=[])
    rows = await open_items.age_view(session, mine, now=NOW)
    assert len(rows) == 1
    for criteria in session.seen:
        assert {"tenant_id", "environment_id"} <= {name for name, _, _ in criteria}


# --- erase ----------------------------------------------------------------------------------


async def test_erasing_the_conversations_removes_their_open_items_in_this_workspace_only():
    mine, other = scope(), scope()
    a, b = chat(mine), chat(mine)
    outsider = chat(other, a.customer_id, a.id)  # same ids in another workspace
    keep = chat(mine)
    session = FakeSession(
        pi_open_items=[item(a), item(b), item(outsider), item(keep)], pi_offer_log=[]
    )
    removed = await brain_erase._erase_conversation_extras(session, mine, [a.id, b.id])
    assert removed["open_items"] == 2
    left = session.tables["pi_open_items"]
    assert {r.conversation_id for r in left} == {outsider.id, keep.id}


async def test_the_erase_selects_every_chat_of_the_customer_so_all_their_items_go():
    """Read from the source: the erase deletes by the customer's conversation ids, all of them,
    not by the latest chat (brain_erase.erase_customer, the PiConversation.customer_id select)."""
    import inspect

    source = inspect.getsource(brain_erase.erase_customer)
    assert "PiConversation.customer_id == customer_id" in source
    assert "_erase_conversation_extras(session, scope, conversation_ids)" in source


# --- no age limit today (pinned) ---------------------------------------------------------------


async def test_there_is_no_age_limit_today_a_year_old_open_item_is_still_named():
    """By design (spec 17.7: 'no counter drops it'); pinned so that a retention rule is added on
    purpose. If the owner sets an age limit for carried items (P-4 question), change this test."""
    s = scope()
    here = chat(s)
    old = item(here, created=NOW - timedelta(days=400))
    session = FakeSession(pi_open_items=[old])
    assert len(await named(session, s, here)) == 1


# --- redaction of what is stored ---------------------------------------------------------------

PHONE = "+923001234567"  # written as a third party's number below
THEIRS = "0300-1234567"
EMAIL = "ali.raza@example.com"
CARD = "4111 1111 1111 1111"


def stored(session: FakeSession) -> list[Any]:
    return [o for o in session.added if isinstance(o, PiOpenItem)]


async def sync(body: str, *, reply: str = "I'll get back to you.", gaps: list[str] | None = None):
    s = scope()
    here = chat(s)
    session = FakeSession(pi_open_items=[])
    message = SimpleNamespace(id=uuid4(), body=body)
    await open_items.sync(
        session,
        s,
        here,
        message,
        reply=reply,
        language="en",
        request_human=False,
        knowledge_gaps=gaps if gaps is not None else ["delivery"],
        said_ids=[],
        now=NOW,
    )
    return session, here, s


async def test_a_third_partys_phone_email_and_a_card_are_redacted_before_an_item_is_stored():
    body = f"his number is {THEIRS}, his email {EMAIL}, card {CARD}: {QUESTION}"
    session, here, s = await sync(body)
    rows = stored(session)
    assert rows, "an item was expected for a question pi could not answer"
    for row in rows:
        assert THEIRS not in row.text and EMAIL not in row.text and CARD not in row.text
        assert not re.search(r"\d{6,}", row.text.replace(" ", "").replace("-", ""))


async def test_the_owners_own_number_given_to_be_reached_is_kept_by_design():
    """safety.OWN_NUMBER (safety.py:779): 'call me on ...' and 'my number is ...' stay, because it
    is theirs to share. So the item text (and the staff view) holds it; it is erased with the
    customer. Pinned so that a change of that policy is made on purpose (retention decision)."""
    session, *_ = await sync(f"call me on {PHONE}: {QUESTION}")
    assert any(PHONE in row.text for row in stored(session))


async def test_the_words_are_redacted_before_they_are_cut_so_a_cut_number_cannot_escape():
    body = ("w " * 147) + f"{THEIRS} {EMAIL} " + QUESTION
    start = body.index(THEIRS)
    assert start < open_items.TEXT_CAP < start + len(THEIRS)  # the number straddles the cut
    session, *_ = await sync(body)
    for row in stored(session):
        assert len(row.text) <= open_items.TEXT_CAP
        assert not re.search(r"\d{4,}", row.text)
        assert "@" not in row.text


async def test_an_item_carries_the_workspace_chat_and_customer_it_came_from():
    session, here, s = await sync(QUESTION)
    for row in stored(session):
        assert row.tenant_id == s.tenant_id and row.environment_id == s.environment_id
        assert row.conversation_id == here.id and row.customer_id == here.customer_id


async def test_a_third_party_introduced_by_a_role_becomes_the_role():
    body = f"the cashier Ahmed Khan did not give me the receipt, {QUESTION}"
    session, *_ = await sync(body)
    assert stored(session)
    for row in stored(session):
        assert "Ahmed" not in row.text and "Khan" not in row.text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN LIMIT Q6-2: third_party.protect works from the words around a name (honorific, "
        "relationship word, verb of reporting). A bare name with nothing around it ('Ahmed did "
        "not send the receipt') cannot be told from a place, a brand or a word, so it is stored "
        "as written. No name list is used; a prompt-level rule is not a privacy boundary."
    ),
)
async def test_a_bare_third_party_name_is_not_stored():
    session, *_ = await sync(f"Ahmed did not send me the receipt, {QUESTION}")
    assert stored(session)
    assert all("Ahmed" not in row.text for row in stored(session))


async def test_the_staff_view_text_of_a_handoff_is_redacted_too():
    s = scope()
    request = SimpleNamespace(
        id=uuid4(),
        tenant_id=s.tenant_id,
        environment_id=s.environment_id,
        conversation_id=uuid4(),
        customer_id=uuid4(),
        kind="human_requested",
        status="open",
        question=f"please phone Ali on {PHONE} about the order",
        created_at=NOW - timedelta(minutes=45),
    )
    session = FakeSession(pi_open_items=[], pi_staff_requests=[request])
    rows = await open_items.age_view(session, s, now=NOW)
    handoffs = [r for r in rows if r["kind"] == "pending_handoff"]
    assert len(handoffs) == 1
    assert PHONE not in handoffs[0]["text"]


# --- Q6-2: a third party's name, from the words around it ---------------------------------------


def stored_text(text: str) -> str:
    return open_items.clean(text)


@pytest.mark.parametrize(
    ("text", "gone", "kept"),
    [
        ("my brother Ahmed Khan took the stock", ["Ahmed", "Khan"], ["my brother"]),
        ("my uncle Ahmed called yesterday", ["Ahmed"], ["my uncle"]),
        ("Mr. Raza phoned me about the invoice", ["Raza"], ["a person phoned me"]),
        ("Dr Sana told me the parcel is late", ["Sana"], ["doctor told me"]),
        ("Bilal said the parcel is late", ["Bilal"], ["someone said the parcel"]),
        ("I called Sara about the price", ["Sara"], ["called someone"]),
        ("our manager Hassan refused to pay", ["Hassan"], ["our manager", "refused"]),
    ],
)
def test_english_names_next_to_a_role_or_a_verb_of_reporting_are_dropped(text, gone, kept):
    out = stored_text(text)
    assert not any(name in out for name in gone), out
    assert all(word in out for word in kept), out


@pytest.mark.parametrize(
    ("text", "gone", "kept"),
    [
        ("Ahmed bhai ne kaha ke maal kal aayega", ["Ahmed"], ["bhai ne kaha"]),
        ("Ayesha baji ko call karna hai", ["Ayesha"], ["baji ko call"]),
        ("Ali ne kaha ke paise nahi hain", ["Ali"], ["kisi ne kaha"]),
        ("Raza sahab ka phone nahi uthta", ["Raza"], ["sahab ka phone"]),
    ],
)
def test_roman_urdu_capitalised_names_before_an_honorific_or_ne_are_dropped(text, gone, kept):
    out = stored_text(text)
    assert not any(name in out for name in gone), out
    assert all(word in out for word in kept), out


@pytest.mark.parametrize(
    ("text", "gone", "kept"),
    [
        ("احمد بھائی نے کہا کہ مال کل آئے گا", ["احمد"], ["بھائی نے کہا"]),
        ("علی نے بتایا کہ پیسے نہیں ہیں", ["علی"], ["کسی نے بتایا"]),
        ("ڈاکٹر سلمان نے منع کیا", ["سلمان"], ["ڈاکٹر نے منع"]),
        ("عائشہ باجی کو فون کرنا ہے", ["عائشہ"], ["باجی کو فون"]),
    ],
)
def test_urdu_script_names_next_to_an_honorific_or_a_reporting_verb_are_dropped(text, gone, kept):
    out = stored_text(text)
    assert not any(name in out for name in gone), out
    assert all(word in out for word in kept), out


@pytest.mark.parametrize(
    ("text", "gone", "kept"),
    [
        ("قال محمد إن البضاعة ستتأخر", ["محمد"], ["قال شخص إن"]),
        ("السيد خالد اتصل بي أمس", ["خالد"], ["السيد", "اتصل بي"]),
        ("أخي سامر رفض الدفع", ["سامر"], ["أخي", "رفض الدفع"]),
        ("الدكتورة ليلى أخبرتني بالموعد", ["ليلى"], ["الدكتورة"]),
    ],
)
def test_arabic_names_next_to_a_title_a_relation_or_a_reporting_verb_are_dropped(text, gone, kept):
    out = stored_text(text)
    assert not any(name in out for name in gone), out
    assert all(word in out for word in kept), out


LEFT_AS_WRITTEN = [
    # roles, brands, places and pronouns
    "Workzap said it will call me back",
    "Customers said the price is too high",
    "Karachi is far for the delivery",
    "WhatsApp told me the message failed",
    "Delivery took 3 days",
    "Driver said it is late",
    "Courier called me yesterday",
    "Cashier told me to wait",
    "I called Support again",
    "I asked Customer Care twice",
    "I paid Easypaisa on Monday",
    "Meezan Bank said the transfer failed",
    "the partner Workzap sent the quote",
    "our supplier Daraz is slow",
    "the customer Support team replied",
    # words that look like an honorific after a name
    "my uncle called",
    "the API is down",
    "Thank you sir",
    "The API stopped",
    "Mera bhai aaya hai",
    # Roman Urdu roles, lower-case words and pronouns
    "main ne kaha ke theek hai",
    "rider ne kaha ke kal aayega",
    "Rider ne kaha ke kal aayega",
    "dukandar ne kaha ke maal nahi hai",
    "mera bhai kal aayega",
    "mere uncle ne kaha",
    "ahmed ne kaha ke kal aayega",  # a lower-case name is not matched (stated limit)
    # Urdu script
    "اس نے کہا کہ ٹھیک ہے",
    "دکاندار نے کہا کہ مال نہیں ہے",
    "بنک نے کہا کہ ٹرانسفر نہیں ہوا",
    "میری بہن کل آئے گی",
    "میرا بھائی ٹھیک ہے",
    "ڈرائیور نے بتایا کہ دیر ہو گئی",
    # Arabic
    "قال لي المدير إن الطلب جاهز",
    "الزبون قال إن السعر مرتفع",
    "قال ان الطلب جاهز",
    "اتصل بي المندوب أمس",
    "أخي رفض الدفع",
    # stated limits: no stop-word-free name before the verb or an unlisted verb
    "Monday Ahmed said the stock is low",
    "Ahmed took the stock",
]


@pytest.mark.parametrize("text", LEFT_AS_WRITTEN)
def test_roles_brands_places_pronouns_and_the_stated_limits_are_left_as_written(text):
    assert third_party.protect(text) == text


def test_no_honorific_is_left_behind_as_a_stub():
    for text in ("Mr. Raza called", "Dr Sana called", "Mrs Hina called", "Sir Ahmed called"):
        out = third_party.protect(text)
        assert not re.search(r"\b(?:a )?(?:mr|mrs|ms|dr|sir)\b", out, re.IGNORECASE), out


def test_sentence_marks_of_the_arabic_script_are_never_swallowed_or_moved():
    for text in (
        "کیا یہ ٹھیک ہے؟ علی نے کہا ہاں۔",
        "احمد بھائی، نے کہا۔ ٹھیک ہے؟",
        "قال محمد، إن الطلب جاهز؟ نعم.",
        "ڈاکٹر سلمان؛ نے منع کیا۔",
    ):
        out = third_party.protect(text)
        for mark in "،۔؟؛":
            assert out.count(mark) == text.count(mark), (text, out)


def test_the_protection_is_idempotent_and_never_empties_a_text():
    for text in (
        "my brother Ahmed said he will pay",
        "Ali ne kaha ke paise nahi hain",
        "احمد بھائی نے کہا",
        "قال محمد إن",
    ):
        once = third_party.protect(text)
        assert once and third_party.protect(once) == once


def test_the_owners_own_number_and_a_third_partys_contact_are_still_decided_by_redaction():
    out = stored_text(f"call me on {PHONE}, and his number is {THEIRS}, mail {EMAIL}, card {CARD}")
    assert PHONE in out  # given to be reached: kept by design (safety.OWN_NUMBER)
    assert THEIRS not in out and EMAIL not in out and CARD not in out
