"""Memory ledgers, pure rules (no database): redaction before storage, the idea filter reads
rejections, constraint validity, document segments, the staff-only delivered marker, the
chat listing of decisions and rejections, and "brain mode only"."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.modules.pi import (
    context_memory,
    document_texts,
    idea_filter,
    memory_answer,
    memory_ledger,
    problem_fields,
    requirements_read,
)
from app.modules.pi.context_memory_types import (
    ContextBundle,
    DecisionItem,
    FileItem,
    RejectionItem,
)

API = Path(__file__).resolve().parents[2]
PI = API / "app" / "modules" / "pi"


# ----------------------------------------------------------------- redaction and keys
def test_owner_words_are_redacted_before_they_are_stored():
    out = memory_ledger.redacted("yes go ahead, call me on 0311 2546598 card 4111 1111 1111 1111")
    assert "2546598" not in out and "4111" not in out
    assert out.startswith("yes go ahead")


def test_redacted_text_is_cut_to_size_after_redaction():
    assert len(memory_ledger.redacted("word " * 500, 300)) <= 300
    assert memory_ledger.redacted("") == ""


def test_the_idea_hash_ignores_case_and_punctuation():
    a = memory_ledger.idea_hash("Offer a  small discount, to regulars!")
    assert a == memory_ledger.idea_hash("offer a small discount to regulars")
    assert a != memory_ledger.idea_hash("run a loyalty card")


# ----------------------------------------------------------------- rejection is not re-offered
def test_a_rejected_idea_is_not_offered_again_same_words_or_close():
    rejected = ["Offer a small discount to your regular customers every month"]
    ctx = idea_filter.with_rejections(None, rejected)
    assert ctx is not None and ctx.rejected == tuple(rejected)
    same = idea_filter.failures(rejected[0], "my sales are slow", ctx)
    assert "G7" in same
    close = idea_filter.failures(
        "Offer a small discount to your regular customers each month", "my sales are slow", ctx
    )
    assert "G7" in close


def test_a_different_idea_passes_the_rejection_check():
    ctx = idea_filter.with_rejections(
        None, ["Offer a small discount to your regular customers every month"]
    )
    other = idea_filter.failures(
        "Write down each order in one notebook at closing time", "my cash does not match", ctx
    )
    assert "G7" not in other


def test_no_rejections_change_nothing():
    ctx = idea_filter.IdeaContext(subtype="x")
    assert idea_filter.with_rejections(ctx, ()) is ctx
    assert idea_filter.with_rejections(None, [""]) is None


# ----------------------------------------------------------------- constraint validity
def test_a_replaced_budget_goes_to_history_as_superseded_with_a_time():
    first, _ = problem_fields.merge_constraints(None, "50000 rupees", "", "", [], "m1")
    second, _ = problem_fields.merge_constraints(first, "80000 rupees", "", "", [], "m2")
    (old,) = second["history"]
    assert old["status"] == "superseded" and old["valid_to"]
    assert old["text"] == "50000 rupees" and second["budget"]["text"] == "80000 rupees"


def test_a_removed_limit_is_withdrawn_in_history():
    first, _ = problem_fields.merge_constraints(None, "", "", "", ["close the shop"], "m1")
    second, _ = problem_fields.merge_constraints(first, "", "", "", [], "m2", ["close the shop"])
    (old,) = second["history"]
    assert old["status"] == "withdrawn" and "cannot_change" not in second


def test_reading_constraints_drops_ended_values_and_keeps_history():
    parsed = requirements_read.parse_constraints(
        {
            "budget": {"text": "80000", "msg": "m2"},
            "staff": {"text": "two people", "status": "withdrawn"},
            "deadline": {"text": "by Eid", "valid_to": "2020-01-01T00:00:00+00:00"},
            "history": [
                {"key": "budget", "text": "50000", "status": "superseded", "valid_to": "t"}
            ],
        }
    )
    assert parsed.budget and parsed.budget.text == "80000"
    assert parsed.staff is None and parsed.deadline is None
    assert [h.text for h in parsed.history] == ["50000"] and parsed.history[0].key == "budget"


def test_legacy_constraints_without_validity_still_read_as_in_force():
    parsed = requirements_read.parse_constraints({"budget": {"text": "50000", "msg": "m1"}})
    assert parsed.budget and parsed.budget.status == "" and parsed.history == ()


# ----------------------------------------------------------------- document segments
def test_a_text_file_is_kept_in_sections_with_references():
    raw = ("The payment is due within 14 days of the invoice date. " * 120).encode()
    found = document_texts.segments(raw)
    assert [ref for ref, _ in found] == [f"section {i}" for i in range(1, len(found) + 1)]
    assert len(found) >= 2 and all(body for _, body in found)


def test_a_spreadsheet_marker_text_splits_by_sheet_and_slide():
    split = document_texts._marked("Sheet 1:\na | b\nSheet 2:\nc | d")
    assert [ref for ref, _ in split] == ["Sheet 1", "Sheet 2"]
    assert split[1][1] == "c | d"


def test_unreadable_bytes_store_nothing():
    assert document_texts.segments(b"\x00\x01\x02 not a document") == []


# ----------------------------------------------------------------- brain mode only
class _NoSession:
    """Any database call fails the test: outside brain mode nothing may be touched."""

    def __getattr__(self, name):  # pragma: no cover - only reached on a violation
        raise AssertionError(f"session.{name} used outside brain mode")


def test_the_hooks_do_nothing_outside_brain_mode():
    conversation = SimpleNamespace(customer_id=uuid4(), id=uuid4())
    decision = SimpleNamespace(brief={"offer_declined": True}, effects=["request_solution"])
    scope = SimpleNamespace(tenant_id=uuid4(), environment_id=uuid4())
    for rules in (None, {}, {"pi_mode": "standard"}, {"constitution": True}):
        asyncio.run(memory_ledger.on_decision(_NoSession(), scope, conversation, decision, rules))
        asyncio.run(
            memory_ledger.on_document_approved(
                _NoSession(), scope, SimpleNamespace(customer_id=uuid4(), ref="Q-0001"), rules
            )
        )
        assert (
            asyncio.run(
                document_texts.on_file_saved(
                    _NoSession(),
                    scope,
                    customer_id=uuid4(),
                    file_id=uuid4(),
                    raw=b"x" * 400,
                    response_rules=rules,
                )
            )
            == 0
        )


def test_a_non_decision_writes_nothing_even_in_brain_mode():
    conversation = SimpleNamespace(customer_id=uuid4(), id=uuid4())
    decision = SimpleNamespace(brief={}, effects=[])
    scope = SimpleNamespace(tenant_id=uuid4(), environment_id=uuid4())
    asyncio.run(
        memory_ledger.on_decision(_NoSession(), scope, conversation, decision, {"pi_mode": "brain"})
    )


# ----------------------------------------------------------------- delivered only by staff
def test_only_the_staff_route_and_the_marker_module_touch_the_delivered_marker():
    """No conversation, model, learning or box code imports delivery_marker or calls the two
    marking functions: the marker can only come from the staff route."""
    allowed = {"delivery_marker.py", "brain_doc_routes.py"}
    users = []
    for path in PI.glob("*.py"):
        if path.name in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (
                node.module == "app.modules.pi.delivery_marker"
                or any(a.name == "delivery_marker" for a in node.names)
            ):
                users.append(path.name)
            if (
                isinstance(node, ast.Attribute)
                and node.attr in ("mark_delivered", "mark_verified")
                and isinstance(node.value, ast.Name)
                and node.value.id == "delivery_marker"
            ):
                users.append(path.name)
    assert users == []


def test_the_staff_routes_require_the_quotes_write_permission():
    text = (PI / "brain_doc_routes.py").read_text(encoding="utf-8")
    for name in ("mark_delivered", "mark_verified"):
        body = text.split(f"async def {name}")[1].split("@router")[0]
        assert 'require_pi(session, scope, "quotes.write")' in body


# ----------------------------------------------------------------- the chat listing
def _bundle(**kw):
    return ContextBundle(tenant_id=uuid4(), environment_id=uuid4(), customer_id=uuid4(), **kw)


def test_the_remember_answer_lists_decisions_and_rejections_with_source_and_status():
    bundle = _bundle(
        decisions=(
            DecisionItem(
                "decline", "box:offer", "superseded", "not now", "2026-11-01", "msg:abc", "owner"
            ),
            DecisionItem(
                "yes", "box:offer", "active", "yes please", "2026-11-02", "msg:def", "owner"
            ),
        ),
        rejections=(
            RejectionItem("a loyalty card", "rej:1", False, "", "t", "active", "msg:abc"),
            RejectionItem("a flyer", "rej:2", False, "", "t", "reversed", "msg:xyz"),
        ),
    )
    known = context_memory.known_records(bundle)
    text = memory_answer.reply(known, "en", "nothing")
    assert "msg:def" in " ".join(r["text"] for r in known)
    assert "status: superseded" in text and "status: active" in text
    assert "a loyalty card" in text and "taken back" in text
    assert text.count("decision") >= 2


def test_empty_ledgers_leave_the_known_records_unchanged():
    assert context_memory.known_records(_bundle()) == []
    assert memory_answer.reply([], "en", "fallback") == "fallback"


def test_stored_text_references_travel_with_the_file_item():
    item = FileItem(uuid4(), "terms.pdf", "application/pdf", 10, "whatsapp", "t")
    assert item.text_refs == () and item.text_available is False
