"""Erase completeness (FT-E2b): every table in the pi, pi_saas, pi_customer and customer modules
that holds a customer_id or conversation_id is either erased by brain_erase (static check: the
model is the target of a delete() or update() there, or in business_profile_store, which it calls)
or is listed below with a reason. A new such table with neither makes this test fail.

Static, no database. `KNOWN_GAPS` are real holes found when this test was written (customer words
that erase_customer leaves behind): they are NOT approved exceptions. Each carries a TODO naming the
finding in the FT-E2b report; when one is fixed in brain_erase.py, delete it from the dict (the
stale-entry test forces that)."""

import ast
import glob
import importlib
import os
from pathlib import Path

from sqlalchemy import String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

API = Path(__file__).resolve().parents[2]
PI = API / "app" / "modules" / "pi"
SOURCES = [PI / "brain_erase.py", PI / "business_profile_store.py"]
MODULE_PREFIXES = (
    "app.modules.pi.",
    "app.modules.pi_saas.",
    "app.modules.pi_customer.",
    "app.modules.customers.",
    "app.modules.orders.",
    "app.modules.quotes.",
    "app.modules.sales.",
    "app.modules.billing.",
)
KEYS = ("customer_id", "conversation_id")

# Not erased, on purpose. One line each; the reason must say why keeping it is right.
ALLOWED: dict[str, str] = {
    "pi_brain_documents": "kept on purpose: business record (brain_erase docstring, spec 4.9)",
    "pi_brain_payments": "kept on purpose: financial record the company must show (brain_erase)",
    "pi_payment_requests": "financial record (amount, reference, proof); retained like payments",
    "pi_customer_consents": "consent evidence must outlive an erase request; no customer words",
    "pi_agent_runs": "run metadata only (intent, tokens, latency, ids); no customer words",
    "pi_reply_audits": "ids, prompt version and linter rule names only; no customer words",
    "pi_campaign_recipients": "ids and delivery status only; no customer words",
    "orders": "business record (order), kept like quotes and invoices",
    "quotes": "business record, kept on purpose (brain_erase module docstring)",
    "invoices": "business record the company must show, kept like payments",
}

# Real gaps: customer-held words or data that erase_customer does not remove. DO NOT add to
# ALLOWED to make a test pass. G1 to G10 are fixed in brain_erase.py (branch pi/u-erase-g1-g10);
# G11 to G14 wait for the owner's retention decision (docs/pi-saas/pi-erase-gaps-g1-g14.md).
KNOWN_GAPS: dict[str, str] = {
    # TODO(FT-E2b finding G11): CRM notes written about the customer
    "customer_notes": "body: staff free text about the customer",
    # TODO(FT-E2b finding G12): CRM activity lines about the customer
    "customer_activities": "summary: one line per event about the customer",
    # TODO(FT-E2b finding G13): files the customer sent (the bytes are stored in the row)
    "customer_files": "data, name: documents and photos the customer sent",
    # TODO(FT-E2b finding G14): CRM leads keep requirements and notes the owner gave pi
    "sales_leads": "requirements, notes, title: what the owner said they need",
}

# G1 to G10 and the action the erase takes (spec: docs/pi-saas/pi-erase-gaps-g1-g14.md): rows with
# no record value go, rows that are business records keep their shape and lose their words.
DELETED_ROWS = {"pi_conversation_tags", "pi_pending_actions", "customer_share_links"}
WORDS_BLANKED = {
    "pi_conversation_notes",
    "pi_tickets",
    "pi_staff_requests",
    "pi_handoffs",
    "pi_bookings",
    "pi_tasks",
    "pi_documents",
}


def load_models() -> None:
    for path in glob.glob(str(API / "app" / "modules" / "**" / "*models*.py"), recursive=True):
        rel = os.path.relpath(path, API)[:-3].replace(os.sep, ".")
        importlib.import_module(rel)


def customer_tables(registry_base: type) -> dict[str, tuple[str, list[str]]]:
    """table name -> (class name, the customer_id / conversation_id columns) for the modules in
    scope."""
    found: dict[str, tuple[str, list[str]]] = {}
    for mapper in registry_base.registry.mappers:  # type: ignore[attr-defined]
        cls = mapper.class_
        if not cls.__module__.startswith(MODULE_PREFIXES):
            continue
        columns = [k for k in KEYS if k in mapper.local_table.c]
        if columns:
            found[mapper.local_table.name] = (cls.__name__, columns)
    return found


def _target_names(node: ast.expr, loops: dict[str, set[str]]) -> set[str]:
    if isinstance(node, ast.Name):
        return loops.get(node.id, {node.id})
    return set()


def erased_classes(sources: list[str]) -> set[str]:
    """Class names that are the target of delete(...) or update(...) in these files. A loop such as
    `for key, model in (("a", ModelA), ("b", ModelB)): delete(model)` counts every model listed."""
    erased: set[str] = set()
    for source in sources:
        tree = ast.parse(source)
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            loops: dict[str, set[str]] = {}
            for loop in ast.walk(fn):
                if (
                    isinstance(loop, ast.For)
                    and isinstance(loop.iter, ast.Tuple | ast.List)
                    and isinstance(loop.target, ast.Tuple)
                    and isinstance(loop.target.elts[-1], ast.Name)
                ):
                    names = {
                        e.id
                        for item in loop.iter.elts
                        if isinstance(item, ast.Tuple)
                        for e in item.elts
                        if isinstance(e, ast.Name)
                    }
                    loops[loop.target.elts[-1].id] = names
            for call in ast.walk(fn):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id in ("delete", "update")
                    and call.args
                ):
                    erased |= _target_names(call.args[0], loops)
    return erased


def uncovered(
    tables: dict[str, tuple[str, list[str]]],
    erased: set[str],
    allowed: dict[str, str],
    gaps: dict[str, str],
) -> list[str]:
    return sorted(
        name
        for name, (cls, _) in tables.items()
        if cls not in erased and name not in allowed and name not in gaps
    )


def current() -> tuple[dict[str, tuple[str, list[str]]], set[str]]:
    from app.shared.models import Base

    load_models()
    return customer_tables(Base), erased_classes([p.read_text(encoding="utf-8") for p in SOURCES])


def test_every_customer_table_is_erased_or_listed_with_a_reason():
    tables, erased = current()
    assert uncovered(tables, erased, ALLOWED, KNOWN_GAPS) == [], (
        "a table with customer_id or conversation_id is neither erased by brain_erase nor "
        "listed in ALLOWED (with a reason) or KNOWN_GAPS"
    )


def test_the_check_sees_what_brain_erase_really_erases():
    tables, erased = current()
    for name in (
        "pi_memories",
        "pi_problems",
        "pi_conversations",  # update(): the words are cleared
        "pi_messages",  # update()
        "pi_offer_log",  # delete(model) inside a loop
        "pi_open_items",  # same loop
        "pi_business_profiles",  # business_profile_store.erase_for_customer
        "pi_map_versions",
        "pi_solution_boxes",
        "pi_hypotheses",
        "pi_move_log",
        "pi_experiences",
        "pi_solution_memory",
        "pi_idea_feedback",
        "pi_problem_groups",
    ):
        assert name in tables, name
        assert tables[name][0] in erased, f"{name} is not seen as erased"
    # a table that is only read (select) in brain_erase is not erased
    for name in ("pi_brain_documents", "pi_brain_payments"):
        assert tables[name][0] not in erased


def test_a_new_table_without_erase_fails_the_check():
    class Other(DeclarativeBase):
        pass

    class Synthetic(Other):
        __tablename__ = "pi_synthetic_new_table"
        id: Mapped[str] = mapped_column(String(8), primary_key=True)
        customer_id: Mapped[str] = mapped_column(Uuid)

    Synthetic.__module__ = "app.modules.pi.synthetic_models"
    tables, erased = current()
    tables.update(customer_tables(Other))
    assert "pi_synthetic_new_table" in tables
    assert uncovered(tables, erased, ALLOWED, KNOWN_GAPS) == ["pi_synthetic_new_table"]
    # a conversation_id-only table is caught as well

    class OtherTwo(DeclarativeBase):
        pass

    class Synthetic2(OtherTwo):
        __tablename__ = "pi_synthetic_conv_table"
        id: Mapped[str] = mapped_column(String(8), primary_key=True)
        conversation_id: Mapped[str] = mapped_column(Uuid)

    Synthetic2.__module__ = "app.modules.pi_saas.synthetic_models"
    more = customer_tables(OtherTwo)
    assert uncovered(more, erased, ALLOWED, KNOWN_GAPS) == ["pi_synthetic_conv_table"]


def test_a_delete_in_brain_erase_counts_and_a_select_does_not():
    src = (
        "async def f(s, scope):\n"
        "    await s.execute(delete(Gone).where(Gone.customer_id == 1))\n"
        "    await s.execute(update(Cleared).values(body=''))\n"
        "    await s.scalars(select(OnlyRead.id))\n"
        '    for key, model in (("a", InLoopA), ("b", InLoopB)):\n'
        "        await s.execute(delete(model))\n"
    )
    assert erased_classes([src]) == {"Gone", "Cleared", "InLoopA", "InLoopB"}


def test_the_lists_hold_only_real_uncovered_tables_with_reasons():
    tables, erased = current()
    for label, listing in (("ALLOWED", ALLOWED), ("KNOWN_GAPS", KNOWN_GAPS)):
        for name, reason in listing.items():
            assert name in tables, f"{label}: {name} is not a customer table any more"
            assert tables[name][0] not in erased, (
                f"{label}: {name} is erased now; remove it from the list"
            )
            assert reason.strip() and "\n" not in reason
    assert not set(ALLOWED) & set(KNOWN_GAPS)


def _targets(source: str, verb: str) -> set[str]:
    """Class names that are the first argument of `verb(...)` in the source (a delete() or an
    update() call)."""
    found: set[str] = set()
    for call in ast.walk(ast.parse(source)):
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == verb
            and call.args
            and isinstance(call.args[0], ast.Name)
        ):
            found.add(call.args[0].id)
    return found


def test_g1_to_g10_are_fixed_by_the_documented_action():
    tables, _ = current()
    source = (PI / "brain_erase.py").read_text(encoding="utf-8")
    deleted, updated = _targets(source, "delete"), _targets(source, "update")
    for name in sorted(DELETED_ROWS):
        assert tables[name][0] in deleted, f"{name}: rows of the customer must be deleted"
    for name in sorted(WORDS_BLANKED):
        assert tables[name][0] in updated, f"{name}: the words must be blanked, the row kept"
        assert tables[name][0] not in deleted, f"{name}: the row must stay (counts, audit trail)"
    assert not (DELETED_ROWS | WORDS_BLANKED) & set(KNOWN_GAPS)
