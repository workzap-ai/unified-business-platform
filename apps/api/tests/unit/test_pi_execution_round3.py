# ruff: noqa: E501
"""Controlled execution: third audit round. Secret screening (split, spelled, key names, token values,
precision), seal checks that pin the HMAC comparison, recall with names and thanks, bare 'approve'."""

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pi import execution_audit as au
from app.modules.pi import execution_scope as xs
from app.modules.pi import execution_task as xt
from app.modules.pi.execution_scope import ApprovalCue, classify_approval, create_scope, scope_sha
from app.modules.pi.execution_task import (
    ActionRequest,
    RollbackPlan,
    approve_task,
    check_can_execute,
    new_task,
    start_task,
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


def sc_task():
    sc = mk().scope
    t = new_task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    ).task
    return sc, approve_task(t, sc, NOW).task


def blocked(params):
    sc, t = sc_task()
    d = check_can_execute(t, sc, NOW, action=ActionRequest("write_note", params))
    return (not d.allowed) and d.code == "bad_params"


# ---- HIGH 1: secret screening ----

SPLIT = [
    {"a": "41111111", "b": "11111111"},
    {"a": 41111111, "b": 11111111},
    {"parts": ["4111", "1111", "1111", "1111"]},
    {"x": {"a": "4111 1111", "b": "1111 1111"}},
    {"a": "4111-1111", "k": "x", "b": "1111-1111"[:9]},
]


@pytest.mark.parametrize("p", SPLIT)
def test_card_split_across_values_is_blocked(p):
    assert blocked(p)


SPELLED = [
    "four one one one one one one one one one one one one one one one",
    "Four One One One One One One One One One One One One",
    "char ek ek ek ek ek ek ek ek ek ek ek ek ek ek ek",
    "چار ایک ایک ایک ایک ایک ایک ایک ایک ایک ایک ایک ایک ایک",
    "चार एक एक एक एक एक एक एक एक एक एक एक एक एक",
    "اربعة واحد واحد واحد واحد واحد واحد واحد واحد واحد واحد واحد واحد واحد",
    "4 1 1 1 one one one one one one one one one one",
]


@pytest.mark.parametrize("v", SPELLED)
def test_spelled_out_card_digits_are_blocked(v):
    assert blocked({"note": v})
    assert (
        "[secret]"
        in au.AuditLog()
        .append(at=NOW, kind="action", actor="a", task_id="t", detail=f"card {v}")
        .detail
    )


@pytest.mark.parametrize(
    "v", ["one two three", "we have two one-hour slots and three nine-to-five days", "ek do teen"]
)
def test_few_digit_words_are_fine(v):
    sc, t = sc_task()
    assert check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {"note": v})).allowed


KEYS = [
    "pass word",
    "Pass-Word",
    "PASSWORD",
    "api key",
    "api_key",
    "apiKey",
    "apikey",
    "bearer",
    "Authorization",
    "secret",
    "client_secret",
    "private key",
    "access token",
    "refresh_token",
    "Card Number",
    "card-no",
    "CVV",
    "OTP",
    "pin",
    "PIN code",
    "iban",
    "CNIC",
    "ssn",
    "پاسورڈ",
    "पासवर्ड",
    "كلمة المرور",
]


@pytest.mark.parametrize("k", KEYS)
def test_secret_key_names_are_blocked(k):
    assert blocked({k: "x"})
    assert blocked({"outer": {k: "x"}})


@pytest.mark.parametrize(
    "k", ["note", "title", "customer", "shipping_address", "spinning", "opinion", "happiness"]
)
def test_ordinary_key_names_pass(k):
    sc, t = sc_task()
    assert check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {k: "hello"})).allowed


TOKENS = [
    "sk-live-51H8abcdefghijklmnop",
    "sk_test_abcdefghijkl123",
    "pk_live_abcdefgh1234",
    "pk_test_abcdefgh1234",
    "ghp_" + "a1B2" * 6,
    "xoxb-123456789-abcdefghij",
    "xoxp-123456789-abcdefghij",
    "AKIAIOSFODNN7EXAMPLE",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123def",
    "Authorization: Bearer abcdefgh12345678",
    "bearer abcdefghijkl",
    "https://x.example/cb?token=abc123xyz",
    "https://x.example/?api_key=zzzzzz",
    "https://x.example/?a=1&password=hunter22",
    "A1b2C3d4E5f6G7h8I9j0K1l2M3n4",
    "deadbeef0123456789abcdef0123456789",
]


@pytest.mark.parametrize("v", TOKENS)
def test_token_looking_values_blocked_and_redacted(v):
    assert blocked({"note": v})
    d = (
        au.AuditLog()
        .append(at=NOW, kind="action", actor="a", task_id="t", detail=f"used {v} today")
        .detail
    )
    assert "[secret]" in d
    for frag in (
        "51H8",
        "abcdefghijkl",
        "AKIAIOSF",
        "eyJhbGci",
        "abc123xyz",
        "hunter22",
        "A1b2C3d4",
        "deadbeef",
        "zzzzzz",
    ):
        assert frag not in d, (frag, d)


def test_audit_token_example_from_the_audit():
    d = (
        au.AuditLog()
        .append(
            at=NOW,
            kind="action",
            actor="a",
            task_id="t",
            detail="token sk-live-51H8abcdefghijklmnop",
        )
        .detail
    )
    assert "sk-live" not in d and "51H8" not in d


DISCLOSURES = [
    "my password is hunter2",
    "Password: hunter",
    "password = Hunter",
    "otp 123456",
    "cvv is 123",
    "pin 1234",
    "pin number 4321",
    "iban is PK36SCBL0000001123456702",
    "cnic 35202-1234567-1",
    "ssn 123-45-6789",
    "123456 is my otp",
    "mera password hai hunter",
    "میرا پاسورڈ ہے hunter",
    "मेरा पासवर्ड है hunter",
    "كلمة المرور هي hunter",
    "one time code 55",
    "verification code: 482913",
    "security code is 123",
    "ओटीपी 12",
    "اوٹی پی 1",
    "card number is 4111",
]


@pytest.mark.parametrize("v", DISCLOSURES)
def test_disclosures_still_blocked_and_redacted(v):
    assert blocked({"note": v})
    d = au.AuditLog().append(at=NOW, kind="action", actor="a", task_id="t", detail=v).detail
    assert "hunter" not in d and "482913" not in d and "4321" not in d and "1234" not in d, d


PRECISION = [
    "Please send the pin location of our shop",
    "Our IBAN is shown on the quote PDF",
    "Send the OTP-free link to the customer",
    "Please do not share your password with anyone",
    "Your password reset link will arrive by email",
    "Pin the poster on the board",
    "The card number field is on page two",
    "Ask the customer to keep the OTP private",
    "password is required",
]


@pytest.mark.parametrize("v", PRECISION)
def test_bare_mentions_are_not_blocked_and_are_kept_in_audit(v):
    sc, t = sc_task()
    assert check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {"note": v})).allowed, v
    assert au.AuditLog().append(at=NOW, kind="action", actor="a", task_id="t", detail=v).detail == v


# ---- HIGH 2: seal comparison is pinned ----


def _flip(h: str, i: int) -> str:
    return h[:i] + ("0" if h[i] != "0" else "1") + h[i + 1 :]


def test_scope_with_wrong_seal_is_not_intact_and_cannot_approve():
    sc = mk().scope
    t = new_task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    ).task
    assert sc.is_intact() and approve_task(t, sc, NOW).ok
    for bad in (
        "",
        "0" * 64,
        "x",
        sc.seal.upper(),
        _flip(sc.seal, 0),
        _flip(sc.seal, 63),
        _flip(sc.seal, 31),
        sc.seal + "0",
        sc.seal[:-1],
    ):
        forged = dataclasses.replace(sc, seal=bad)
        assert forged.is_intact() is False, bad
        assert not approve_task(t, forged, NOW).ok, bad


def test_task_with_wrong_seal_is_refused_everywhere():
    sc, t = sc_task()
    assert xt.task_is_genuine(t) and check_can_execute(t, sc, NOW).allowed
    for bad in ("", "0" * 64, _flip(t.seal, 0), _flip(t.seal, 63), t.seal + "0", t.seal[:-1]):
        forged = dataclasses.replace(t, seal=bad)
        assert xt.task_is_genuine(forged) is False, bad
        assert not check_can_execute(forged, sc, NOW).allowed, bad
    forged_new = new_task(
        id="t2",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    ).task
    forged_new = dataclasses.replace(forged_new, seal="0" * 64)
    assert not approve_task(forged_new, sc, NOW).ok
    assert not start_task(dataclasses.replace(t, seal="0" * 64), sc, NOW).ok


def test_seal_comparison_uses_compare_digest(monkeypatch):
    calls = []
    real = xs.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(xs.hmac, "compare_digest", spy)
    sc = mk().scope
    assert sc.is_intact() and calls
    calls.clear()
    t = new_task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    ).task
    assert xt.task_is_genuine(t) and calls


# ---- M05: question marks ----


@pytest.mark.parametrize(
    "t",
    ["I approve?", "go ahead?", "approved؟", "I approve ?", "manzoor hai?", "اوافق؟", "क्या मंजूर है?"],
)
def test_question_marks_never_approve_and_are_labelled(t):
    assert classify_approval(t) is ApprovalCue.CONDITIONAL


# ---- recall: names and thanks ----

TRUE = [
    "I approve - Ahmed",
    "I approve it, thanks Sara",
    "shukriya, manzoor hai",
    "main ye approve karta hoon shukriya",
    "Yes, I approve this work",
    "I hereby approve",
    "I authorise you to go ahead",
    "I approve this exactly as written",
    "I approve the plan as shown",
    "mujhe manzoor hai",
    "main ijazat deta hoon",
    "bilkul, main approve karta hoon",
    "میں اجازت دیتا ہوں",
    "मैं अनुमति देता हूं",
    "मैं मंज़ूर करता हूँ",
    "मैं मंज़ूरी देती हूँ",
    "أوافق على هذا",
    "أعطيك الموافقة",
    "أصرح لك بالبدء",
    "Approved - Sara",
    "Go ahead, thanks Ahmed",
    "Thanks, I approve",
    "I approve from Sara",
    "I approve this as described",
    "I approve it exactly as stated",
    "approve hai, shukriya",
    "go ahead - Omar",
    "Thank you, I approve this scope",
]


@pytest.mark.parametrize("t", TRUE)
def test_name_and_thanks_approvals_pass(t):
    assert classify_approval(t) is ApprovalCue.EXPLICIT_YES, t
    assert mk(approval_text=t).ok


NOT = [
    "I approve - Delete Everything",
    "I approve, Send Everyone",
    "I approve - Pay Ahmed",
    "I approve, Refund Customers",
    "Sara approved",
    "Sara says I approve",
    "I approve - Ahmed go ahead and delete",
    "I approve Sara",
    "approve",
    "Approve",
    "approve this scope",
    "Approve the plan",
    "I approve - Ahmed Sara Omar Ali",
    "I approve as long as it is free",
    "I approve as shown, but later",
    "go ahead exactly as written if it is free",
    "I approve exactly as written 4111111111111111",
    "I approve - Ahmed, also email everyone",
    "thanks Sara, go ahead tomorrow",
    "I approve it, thanks Sara?",
    "I approve - Ahmed (CEO)",
]


@pytest.mark.parametrize("t", NOT)
def test_names_do_not_smuggle_content(t):
    assert classify_approval(t) is not ApprovalCue.EXPLICIT_YES, t


def test_bare_approve_is_vague():
    for t in ("approve", "Approve", "approve.", "APPROVE!"):
        assert classify_approval(t) is ApprovalCue.VAGUE
    assert classify_approval("approved") is ApprovalCue.EXPLICIT_YES
    assert classify_approval("approve hai") is ApprovalCue.EXPLICIT_YES


def test_forged_scope_seal_is_named_in_issues_and_refused_by_the_gate():
    sc, t = sc_task()
    forged = dataclasses.replace(sc, seal="f" * 64)
    assert forged.issues() and "issued by create_scope" in forged.issues()[0]
    d = check_can_execute(t, forged, NOW)
    assert not d.allowed
    assert not start_task(t, forged, NOW).ok
