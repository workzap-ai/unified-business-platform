# ruff: noqa: E501
"""Controlled execution: fourth audit round. Name slot, key families, label/value pairs, reversed and
spaced disclosures, encoded values, over-blocking precision, value-only redaction."""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pi import execution_audit as au
from app.modules.pi.execution_scope import (
    ApprovalCue,
    classify_approval,
    create_scope,
    name_parts,
    scope_sha,
)
from app.modules.pi.execution_task import (
    ActionRequest,
    RollbackPlan,
    approve_task,
    check_can_execute,
    new_task,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
TEXT = "Update the delivery note template on the staging site."
TOOLS = ["read_record", "write_note"]
LIMITS = {"max_actions": 5}
PLAN = RollbackPlan(
    ("restore the saved template",), True, "Ali (staff)", "template shows the old text"
)


def mk(**over):
    args = dict(
        scope_text=TEXT,
        tools=TOOLS,
        limits=LIMITS,
        expires_at=NOW + timedelta(days=2),
        approver="Sara (owner)",
        approval_source="owner_chat",
        approval_text="I approve this",
        referenced_sha=scope_sha(TEXT, frozenset(TOOLS), LIMITS),
        task_owner="Ali (staff)",
        task_creator="Zed (staff)",
        now=NOW,
    )
    args.update(over)
    return create_scope(**args)


def gate(params):
    sc = mk().scope
    t = new_task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    ).task
    t = approve_task(t, sc, NOW).task
    return check_can_execute(t, sc, NOW, action=ActionRequest("write_note", params))


def blocked(params):
    d = gate(params)
    return (not d.allowed) and d.code == "bad_params"


def allowed(params):
    return gate(params).allowed


def clean(detail):
    return au.AuditLog().append(at=NOW, kind="action", actor="a", task_id="t", detail=detail).detail


# ---- HIGH 1: the name slot ----

INSTRUCTIONS_AS_NAMES = [
    "I approve - Disable Auth",
    "I approve - Overwrite Backups",
    "I approve - Reset Passwords",
    "I approve - Close Account",
    "I approve - Wire Money Abroad",
    "I approve - Update Prices",
    "I approve - Add Discount",
    "I approve - Buy Stock",
    "I approve - Hire Staff",
    "I approve - Sign Contract",
    "I approve - Order Inventory",
    "I approve - Upload Photos",
    "I approve - Grant Access",
    "manzoor hai - Paise Bhejo",
    "I approve, Delete Everything",
    "I approve - Rotate Keys",
    "I approve - Fire Ahmed",
    "go ahead - Merge Branch",
    "approved - Launch Rocket",
    "I approve - Disable",
    "I approve - Overwrite",
    "I approve - Wire",
    "I approve - Hire",
    "I approve - Upload",
    "I approve - Grant",
]


@pytest.mark.parametrize("t", INSTRUCTIONS_AS_NAMES)
def test_instructions_are_not_names(t):
    assert classify_approval(t) is not ApprovalCue.EXPLICIT_YES
    assert classify_approval(t, name_parts("Sara (owner)")) is not ApprovalCue.EXPLICIT_YES
    assert not mk(approval_text=t).ok


def test_name_slot_rules():
    assert (
        classify_approval("I approve - Ahmed") is ApprovalCue.EXPLICIT_YES
    )  # one unknown capitalised word
    assert (
        classify_approval("I approve - Ahmed Khan") is not ApprovalCue.EXPLICIT_YES
    )  # two unknown words
    known = name_parts("Ahmed Khan (owner)")
    assert known == {"ahmed", "khan"}
    assert classify_approval("I approve - Ahmed Khan", known) is ApprovalCue.EXPLICIT_YES
    assert classify_approval("I approve - Ahmed Delete", known) is not ApprovalCue.EXPLICIT_YES
    assert (
        classify_approval("I approve - Ahmed Zafar", known) is not ApprovalCue.EXPLICIT_YES
    )  # a known and an unknown word together
    assert mk(approver="Bilal Raza (owner)", approval_text="I approve, thank you Bilal").ok
    assert mk(approver="Bilal Raza (owner)", approval_text="I approve - Bilal Raza").ok
    assert not mk(approver="Bilal Raza (owner)", approval_text="I approve - Bilal Raza Update").ok


# ---- HIGH 2: key families and pairs ----

KEYS = [
    "security code",
    "one_time_code",
    "securitycode",
    "cc_num",
    "ccv",
    "cookie",
    "mothers maiden name",
    "social security number",
    "nic",
    "NIC",
    "Cvv2",
    "session",
    "sid",
    "Session-ID",
    "one time password",
    "onetimecode",
    "OTP",
    "otp_code",
    "card num",
    "CardNum",
    "Cookies",
    "pass word",
    "api key",
    "bearer",
    "authorization",
    "pwd",
    "passphrase",
    "client secret",
    "pin",
    "national id",
    "cnic",
    "ssn",
    "token",
    "access_token",
    "پاسورڈ",
    "पासवर्ड",
    "كلمة المرور",
]


@pytest.mark.parametrize("k", KEYS)
def test_key_families_blocked(k):
    assert blocked({k: "x"})


PAIRS = [
    {"label": "password", "value": "hunter2"},
    {"name": "pwd", "val": "hunter2"},
    {"field": "OTP", "answer": "482913"},
    {"key": "api key", "v": "abc"},
    {"type": "token", "data": "zzz"},
    {"label": "Security Code", "value": "123"},
]


@pytest.mark.parametrize("p", PAIRS)
def test_label_value_pairs_blocked(p):
    assert blocked(p)
    assert blocked({"items": [p]})


TEXTS = [
    "hunter2 is my password",
    "Hunter is your pin",
    "482913 is my otp",
    "o t p 4 8 2 9 1 3",
    "p-i-n 4821",
    "c v v 123",
    "P.I.N. 4821",
    "the code we texted you is four eight two nine one three",
    "the otp is four eight two nine",
    "sid=abc123",
    "mother's maiden name is Khan",
    "social security number is 123456789",
    "secret: hunter2",
    "secret = hunter2",
    "my secret is Hunter",
]


@pytest.mark.parametrize("v", TEXTS)
def test_disclosure_forms_blocked(v):
    assert blocked({"note": v}), v


def test_encoded_values_blocked():
    card = b"4111111111111111"
    enc = [
        base64.b64encode(card).decode(),
        base64.urlsafe_b64encode(card).decode(),
        card.hex(),
        base64.b64encode(b"password is hunter2").decode(),
        base64.b64encode(b"4111 1111 1111 1111").decode(),
        base64.b64encode(b"otp 482913").decode(),
    ]
    for e in enc:
        assert blocked({"ref": e}), e
        assert "[secret]" in clean(f"saved {e} ok"), e
        assert e not in clean(f"saved {e} ok")
    assert allowed({"ref": base64.b64encode(b"hello there friend, nice day").decode()})


def test_card_digits_with_letters_between_are_caught_per_value():
    # Only the per-value card check sees this shape: removing that check must fail this test.
    assert blocked({"note": "4111a1111a1111a1111"})
    assert blocked({"note": "4111x1111x1111x1111"})


# ---- over-blocking precision ----

ORDINARY = [
    {"order": 123456, "total": 12500, "phone": 3001234567, "zip": 54000},
    {"nums": list(range(1, 15))},
    {
        "items": [
            {"sku": 1001, "qty": 2, "price": 450},
            {"sku": 1002, "qty": 1, "price": 1200},
            {"sku": 1003, "qty": 5, "price": 99},
        ]
    },
    {"tokens_used": 5, "body": "hello"},
    {"token_count": 12, "body": "hello"},
    {"ref": str(uuid.uuid4())},
    {"ref": "7f9c2ba4-e88f-4a7c-9d0c-1a2b3c4d5e6f"},
    {"order": "123456", "total": "12500", "phone": "3001234567", "zip": "54000"},
    {"note": "Order 1234 for delivery on 12 March, call 0300 1234567"},
    {"qty": 3, "price": 1999, "sku": 20240101},
]


@pytest.mark.parametrize("p", ORDINARY)
def test_ordinary_order_data_is_allowed(p):
    assert gate(p).allowed, p


def test_tokens_key_with_text_value_or_secretish_context_is_still_blocked():
    assert blocked({"tokens": "sk-live-51H8abcdefghijklmnop"})
    assert blocked({"access_tokens_used": "abc"})
    assert blocked({"api_token": 5})


def test_split_card_still_blocked_but_small_ints_are_not():
    assert blocked({"a": "41111111", "b": "11111111"})
    assert blocked({"a": 4111, "b": 1111, "c": 1111, "d": 1111})
    assert blocked({"card_part_1": "5555", "x": "5555", "y": "5555", "z": "4444"})
    assert allowed({"a": 41, "b": 11, "c": 1, "d": 1111})


# ---- HIGH 3 and value-only redaction ----


def test_secret_colon_is_redacted_and_the_rest_kept():
    assert (
        clean("secret: hunter2. Verification passed. Rollback plan recorded.")
        == "secret: [secret]. Verification passed. Rollback plan recorded."
    )


@pytest.mark.parametrize(
    "detail,expect",
    [
        (
            "customer said password is hunter2 then asked for the delivery date on Friday",
            "customer said password is [secret] then asked for the delivery date on Friday",
        ),
        (
            "otp 482913 received, refusal code needs_approval for task t1",
            "otp [secret] received, refusal code needs_approval for task t1",
        ),
        (
            "api key sk-live-51H8abcdefghijklmnop was rotated on Monday",
            "api key [secret] was rotated on Monday",
        ),
        ("pin 4821 then moved on", "pin [secret] then moved on"),
        ("o t p 4 8 2 9 1 3 sent to staff", "otp [secret] sent to staff"),
    ],
)
def test_redaction_keeps_context_and_removes_only_the_value(detail, expect):
    out = clean(detail)
    assert out == expect, out


def test_redaction_of_values_with_dashes_and_trailing_dot():
    out = clean("cnic 35202-1234567-1. next step approved")
    assert "35202" not in out and "1234567" not in out and "next step approved" in out
    out = clean("password is hunter2. Done")
    assert "hunter2" not in out and out.endswith("Done")


def test_audit_still_redacts_everything_the_param_gate_blocks():
    for v in (
        "hunter2 is my password",
        "the code we texted you is four eight two nine one three",
        "c v v 123",
    ):
        out = clean(v)
        assert "hunter2" not in out and "four eight two" not in out and "123" not in out, out


def test_per_value_digit_gap_check_is_not_redundant():
    # letters between the digits, mostly text: only the per-value 13-digit gap check sees a card here
    v = "pay 4 a 1 b 1 c 1 d 1 e 1 f 1 g 1 h 1 i 1 j 1 k 1 l 1 m 1 n 1 o 1 p thanks"
    assert blocked({"note": v})
    assert not au.looks_secret(v)
