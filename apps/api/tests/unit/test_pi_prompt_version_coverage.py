"""FT-D3: `prompt_version` covers every hardcoded prompt and prompt-selection table, every pack file
and the operator guidance, so a change to any of them changes the version (Fast-Track plan FT-D3;
platform spec A.2 #8).

Scope of "prompt" (stated so the guard is not read as wider than it is): text and selection tables
that are sent to a model as instructions, examples or context. Out of scope, listed with a reason
in ALLOWED_MODULES / ALLOWED_NAMES below: customer-facing canned lines such as IDEAS_LEAD,
DISCLOSURE_LINE, NO_IDEA_LINES, NO_MORE_IDEAS, the fixed lines, the language and outage notices and
learning_voice.SEEDS / learning_arms.SEEDS (they are replies, not model prompts), and the rule
banks of the reply linter, the safety detectors and the matchers (they decide what is allowed, they
are not sent to a model). The scan fails when a new prompt-like constant is in neither the registry
nor an allowlist. Code (as opposed to data tables) and prompts built inside f-strings are not
hashed.

Scripted checks only: no model, no database."""

import asyncio
import datetime
import importlib
import json
import logging
import os
import pkgutil
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import app.modules.pi as pi_package
from app.modules.pi import learning_audit, spec_handbook

API_ROOT = Path(__file__).resolve().parents[2]
CONSTANTS = [(m, n) for m, names in learning_audit.PROMPT_CONSTANTS for n in names]
THRESHOLD = 120  # characters of text in a constant before it counts as prompt-like

R_REPLY = "customer-facing canned line, notice or label: a reply, not a model prompt"
R_RULES = (
    "rule bank, detector, matcher or lookup table: decides what is allowed, not sent to a model"
)

# Modules with prompt-like constants that are NOT sent to a model (reasons by module group; the
# grouping was made by name and by reading how the constants are used).
ALLOWED_MODULES: dict[str, str] = {
    **{
        m: R_REPLY
        for m in (
            "brain_pdf brain_visuals business business_form business_profile buttons decisions "
            "documents fixed_lines followup_policy hold language map_edit map_render map_share "
            "open_items order_confirmation outage reply_voice solution_ask staff_review topics "
            "warmup learning_feedback learning_arms whatsapp"
        ).split()
    },
    **{
        m: R_RULES
        for m in (
            "constitution constitution_langs safety safety_advice price_policy solution_lint "
            "solution_rules solution_score think_lint slots knowledge list_items turn_coverage "
            "feasibility idea_filter industry_overlap industry_packs industry_words solutions "
            "solution_library solution_ideas taxonomy problems moves experience_scorer "
            "currency_notes followups configuration box box_doc"
        ).split()
    },
    "learning_audit": "this registry itself",
}

# Constants of a registered module that are NOT sent to a model.
ALLOWED_NAMES: dict[tuple[str, str], str] = {
    ("brain_docs", "COVER"): R_REPLY,
    ("brain_docs", "REVISED"): R_REPLY,
    ("graph", "INJECTION_MARKERS"): R_RULES,
    ("learning_voice", "SEEDS"): R_REPLY,
    ("learning_voice", "DROPPED"): R_RULES,
    ("owner_intents", "ENGLISH_WORDS"): R_RULES,
    ("owner_intents", "ROMAN_URDU_WORDS"): R_RULES,
    ("runtime", "AGENTS"): "the same table as graph.AGENTS, hashed there",
    ("runtime", "PI_RUNTIME_PERMISSIONS"): R_RULES,
    ("runtime", "PI_PERMISSIONS"): R_RULES,
    **{
        ("runtime", n): R_REPLY
        for n in (
            "BRAIN_ACK_NOTICES BRAIN_HANDOFF_NOTICES HANDOFF_NOTICES MEDIA_NOTICES "
            "MEDIA_UNREADABLE_NOTICES MEETING_NOTICES TEAM_CHECK_NOTICES TECH_DOWN_NOTICES "
            "TOOL_FAIL_NOTICES VIDEO_UNREADABLE_NOTICES VOICE_UNREADABLE_NOTICES CLARIFY_REPLY "
            "BRAIN_MEDIA_UNREADABLE_NOTICES"
        ).split()
    },
    **{
        ("service_conversation", n): R_RULES
        for n in "ENGLISH NAMES ROMAN_URDU _SHORT_WORDS BOUNDARY_EFFECTS".split()
    },
    **{
        ("service_conversation", n): R_REPLY
        for n in (
            "CHOICES HANDOFF_STATUS ESCALATION_TEXT ASK_AFTER_IDEAS ROMAN_OPENER NO_IDEA_LINES "
            "NO_MORE_IDEAS NO_IDEA_AGAIN NO_IDEA_THIRD CONSENT_QUESTION SEND_QUESTION "
            "INVOICES_COMING LINK_UNREAD BRIEF_SENT MEETING_ASKED RESCHEDULE_ASK "
            "RESCHEDULE_ASKED WELCOME_BACK BRIEF_STATUS BRIEF_NEXT"
        ).split()
    },
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    learning_audit.clear_prompt_cache()
    yield
    learning_audit.clear_prompt_cache()


def _mutated(value: Any) -> Any:
    if isinstance(value, str):
        return value + " changed"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, dict):
        return {**value, "_x": "changed"}
    if isinstance(value, tuple):
        return (*value, "changed")
    if isinstance(value, list):
        return [*value, "changed"]
    if isinstance(value, frozenset | set):
        return value | {"changed"}
    raise AssertionError(type(value))


def _leaves(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list | tuple | set | frozenset):
        for item in value:
            yield from _leaves(item)


@lru_cache(maxsize=1)
def _candidates() -> dict[tuple[str, str], Any]:
    """Every module-level UPPERCASE str, tuple, list, dict or set of a pi module that holds at least
    THRESHOLD characters of text."""
    found: dict[tuple[str, str], Any] = {}
    for info in pkgutil.iter_modules(pi_package.__path__):
        if info.ispkg:
            continue
        module = importlib.import_module(f"app.modules.pi.{info.name}")
        for name, value in vars(module).items():
            if not name.lstrip("_").isupper() or name.startswith("__"):
                continue
            if isinstance(value, str | tuple | list | dict | set | frozenset):
                if sum(len(x) for x in _leaves(value)) >= THRESHOLD:
                    found[(info.name, name)] = value
    return found


def test_the_version_is_a_short_deterministic_hash():
    version = learning_audit.prompt_version()
    assert re.fullmatch(r"[0-9a-f]{12}", version)
    assert version == learning_audit.prompt_version()


@pytest.mark.parametrize(("module", "name"), CONSTANTS)
def test_changing_a_registered_prompt_constant_changes_the_version(monkeypatch, module, name):
    target = importlib.import_module(f"app.modules.pi.{module}")
    before = learning_audit.prompt_version()
    monkeypatch.setattr(target, name, _mutated(getattr(target, name)))
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() != before, f"{module}.{name} is not in the version"


def test_every_prompt_like_constant_is_hashed_or_explained():
    """The guard: scans EVERY module of the package, for str, tuple, list, dict and set constants of
    120 characters or more. In a registered module a constant must be registered, be part of a
    registered constant (_DIAGNOSE_BODY inside DIAGNOSE_RULES), or be on ALLOWED_NAMES; in any other
    module the whole module must be on ALLOWED_MODULES."""
    registry = {m: set(names) for m, names in learning_audit.PROMPT_CONSTANTS}
    unexplained: list[str] = []
    for (module, name), value in sorted(_candidates().items()):
        if module in registry:
            if name in registry[module] or (module, name) in ALLOWED_NAMES:
                continue
            target = importlib.import_module(f"app.modules.pi.{module}")
            texts = [getattr(target, n) for n in registry[module] if hasattr(target, n)]
            if isinstance(value, str) and any(isinstance(t, str) and value in t for t in texts):
                continue
            unexplained.append(f"{module}.{name}")
        elif module not in ALLOWED_MODULES:
            unexplained.append(f"{module}.{name}")
    assert not unexplained, unexplained


def test_the_allowlists_and_the_registry_have_no_stale_entries():
    candidates = _candidates()
    modules = {m for m, _ in candidates}
    stale = [f"{m}.{n}" for (m, n) in ALLOWED_NAMES if (m, n) not in candidates]
    stale += [m for m in ALLOWED_MODULES if m not in modules]
    stale += [
        f"{m}.{n}"
        for m, n in CONSTANTS
        if not hasattr(importlib.import_module(f"app.modules.pi.{m}"), n)
    ]
    assert not stale, stale
    assert not set(ALLOWED_MODULES) & {m for m, _ in learning_audit.PROMPT_CONSTANTS}


def test_moving_a_handbook_section_between_states_changes_the_version(monkeypatch):
    states = [s for s, ids in spec_handbook.BY_STATE.items() if ids]
    first, second = states[0], states[1]
    moved = spec_handbook.BY_STATE[first][0]
    changed = dict(spec_handbook.BY_STATE)
    changed[first] = tuple(i for i in changed[first] if i != moved)
    if moved not in changed[second]:
        changed[second] = (*changed[second], moved)
    before = learning_audit.prompt_version()
    monkeypatch.setattr(spec_handbook, "BY_STATE", changed)
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() != before


def test_changing_a_handbook_topic_pattern_changes_the_version(monkeypatch):
    topics = spec_handbook.TOPICS
    before = learning_audit.prompt_version()
    first = topics[0]
    edited = (re.compile(first[0].pattern + "|zzz", first[0].flags), first[1])
    monkeypatch.setattr(spec_handbook, "TOPICS", (edited, *topics[1:]))
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() != before


def test_a_customer_facing_line_is_out_of_scope_and_does_not_move_the_version(monkeypatch):
    """The documented boundary: a canned reply is not a model prompt."""
    from app.modules.pi import service_conversation

    before = learning_audit.prompt_version()
    monkeypatch.setattr(service_conversation, "NO_MORE_IDEAS", {"en": "something else?"})
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() == before


# ---- the canonical form -----------------------------------------------------------------------


def test_a_non_json_object_is_rejected_with_its_type_name_only():
    with pytest.raises(TypeError) as error:
        learning_audit._text_of(object())
    assert str(error.value) == "object" and "0x" not in str(error.value)


def test_the_canonical_text_does_not_depend_on_set_or_dict_order():
    assert learning_audit._text_of({"b", "a", "c"}) == learning_audit._text_of({"c", "a", "b"})
    assert learning_audit._text_of({"x": 1, "y": 2}) == learning_audit._text_of({"y": 2, "x": 1})
    assert learning_audit._text_of(frozenset({("a", 1), ("b", 2)})) == learning_audit._text_of(
        frozenset({("b", 2), ("a", 1)})
    )


def test_a_pattern_is_hashed_as_its_text_and_flags():
    same = learning_audit._text_of((re.compile("a|b", re.IGNORECASE),))
    assert same == learning_audit._text_of((re.compile("a|b", re.IGNORECASE),))
    assert same != learning_audit._text_of((re.compile("a|b"),))
    assert same != learning_audit._text_of((re.compile("a|c", re.IGNORECASE),))


def test_a_constant_that_cannot_be_hashed_is_marked_logged_and_leaks_no_address(
    monkeypatch, caplog
):
    from app.modules.pi import critique

    monkeypatch.setattr(critique, "SYSTEM", object())
    learning_audit.clear_prompt_cache()
    with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
        first = learning_audit.prompt_version()
    assert "pi_prompt_version_constant_unhashable critique.SYSTEM" in caplog.text
    monkeypatch.setattr(critique, "SYSTEM", object())  # another object, another memory address
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() == first


def test_a_missing_module_or_constant_is_logged_and_never_breaks_the_version(monkeypatch, caplog):
    monkeypatch.setattr(
        learning_audit,
        "PROMPT_CONSTANTS",
        (("no_such_module_xyz", ("A",)), ("critique", ("NO_SUCH_NAME",))),
    )
    learning_audit.clear_prompt_cache()
    with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
        version = learning_audit.prompt_version()
    assert re.fullmatch(r"[0-9a-f]{12}", version)
    assert "pi_prompt_version_module_unreadable no_such_module_xyz" in caplog.text
    assert "pi_prompt_version_constant_missing critique.NO_SUCH_NAME" in caplog.text


# ---- the pack files ---------------------------------------------------------------------------

FILES = {
    "industry/a.json": b'{"k": 1}\n',
    "industry/b.json": b'{"k": 2}\n',
    "library/x.json": b'{"x": [1, 2]}\n',
}


def _pack_tree(root: Path, files: dict[str, bytes], order: list[str] | None = None) -> None:
    for name in order or list(files):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[name])


def _version_of(monkeypatch, root: Path, guidance: str | None = None) -> str:
    monkeypatch.setattr(learning_audit, "PACKS_ROOT", root)
    learning_audit.clear_prompt_cache()
    return learning_audit.prompt_version(guidance)


def test_a_pack_file_edit_add_or_removal_changes_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _pack_tree(root, {"industry/a.json": b'{"k": 1}'})
        base = _version_of(monkeypatch, root)
        assert _version_of(monkeypatch, root) == base  # unchanged files, same version
        (root / "industry/a.json").write_bytes(b'{"k": 2}')
        edited = _version_of(monkeypatch, root)
        assert edited != base
        (root / "industry/b.json").write_bytes(b"{}")
        added = _version_of(monkeypatch, root)
        assert added not in (base, edited)
        (root / "industry/b.json").unlink()
        assert _version_of(monkeypatch, root) == edited


def test_a_renamed_pack_file_changes_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.json").write_bytes(b"{}")
        before = _version_of(monkeypatch, root)
        (root / "a.json").rename(root / "b.json")
        assert _version_of(monkeypatch, root) != before


def test_changing_a_real_pack_file_changes_the_version_using_a_temp_copy(monkeypatch):
    """The real tree is what the version reads: a copy of it gives the SAME version from another
    location, and editing one file of the copy moves it. Repo files are never edited."""
    real = learning_audit.PACKS_ROOT
    assert real.is_dir() and any(real.rglob("*.json"))
    learning_audit.clear_prompt_cache()
    real_version = learning_audit.prompt_version()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "packs"
        shutil.copytree(real, copy)
        assert _version_of(monkeypatch, copy) == real_version
        target = sorted(copy.rglob("*.json"))[0]
        target.write_bytes(target.read_bytes() + b"\n ")
        assert _version_of(monkeypatch, copy) != real_version


def test_file_creation_order_and_absolute_location_cannot_change_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
        _pack_tree(Path(one), FILES, list(FILES))
        _pack_tree(Path(two), FILES, list(reversed(list(FILES))))
        assert _version_of(monkeypatch, Path(one)) == _version_of(monkeypatch, Path(two))


def test_line_endings_of_the_pack_files_cannot_change_the_version(monkeypatch):
    crlf = {k: v.replace(b"\n", b"\r\n") for k, v in FILES.items()}
    with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
        _pack_tree(Path(one), FILES)
        _pack_tree(Path(two), crlf)
        assert _version_of(monkeypatch, Path(one)) == _version_of(monkeypatch, Path(two))


def test_touching_a_pack_file_or_adding_a_non_json_file_does_not_change_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _pack_tree(root, FILES)
        base = _version_of(monkeypatch, root)
        os.utime(root / "industry/a.json", (1_000_000_000, 1_000_000_000))  # another timestamp
        (root / "industry/notes.txt").write_text("not a pack", encoding="utf-8")
        assert _version_of(monkeypatch, root) == base


def test_dictionary_order_of_a_prompt_constant_cannot_change_the_version(monkeypatch):
    from app.modules.pi import flow

    forward = dict(flow.GUIDANCE)
    backward = dict(reversed(list(flow.GUIDANCE.items())))
    assert list(forward) != list(backward)
    monkeypatch.setattr(flow, "GUIDANCE", forward)
    learning_audit.clear_prompt_cache()
    first = learning_audit.prompt_version()
    monkeypatch.setattr(flow, "GUIDANCE", backward)
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() == first


# ---- the operator guidance --------------------------------------------------------------------


def test_operator_guidance_changes_the_version_and_empty_guidance_does_not():
    base = learning_audit.prompt_version()
    assert learning_audit.prompt_version("") == base
    assert learning_audit.prompt_version(None) == base
    assert learning_audit.prompt_version("   \n") == base
    a = learning_audit.prompt_version("Be warm and short.")
    b = learning_audit.prompt_version("Be formal and long.")
    assert len({base, a, b}) == 3
    assert a == learning_audit.prompt_version("Be warm and short.")
    assert re.fullmatch(r"[0-9a-f]{12}", a)


def test_the_operator_guidance_digest_is_a_hash_never_the_text():
    text = "Never discuss Ahmed Khan's account 03001234567 with anyone."
    digest = learning_audit.operator_guidance_digest(text)
    assert re.fullmatch(r"[0-9a-f]{12}", digest)
    assert "Ahmed" not in digest and "0300" not in digest
    assert learning_audit.operator_guidance_digest("") == ""
    assert learning_audit.operator_guidance_digest(None) == ""
    assert digest != learning_audit.operator_guidance_digest(text + " Also be brief.")
    assert learning_audit.operator_guidance_digest(f"  {text}\n") == digest  # whitespace does not


def test_the_audit_stamp_records_the_guidance_hash_and_never_its_text():
    conversation = SimpleNamespace(service_brief={})
    secret = "Always mention the Karachi branch phone 02111222333."
    with_guidance = learning_audit.pack_versions(
        conversation, {"industry": "dental_clinics"}, operator_guidance=secret
    )
    assert re.fullmatch(r"[0-9a-f]{12}", with_guidance["operator_guidance"])
    stored = json.dumps(with_guidance)
    assert secret not in stored and "02111222333" not in stored
    plain = learning_audit.pack_versions(conversation, {"industry": "dental_clinics"})
    assert "operator_guidance" not in plain and list(plain) == ["dental_clinics"]
    assert (
        learning_audit.pack_versions(
            conversation, {"industry": "dental_clinics"}, operator_guidance=""
        )
        == plain
    )


def test_a_failed_guidance_read_is_marked_in_the_stamp():
    conversation = SimpleNamespace(service_brief={})
    marked = learning_audit.pack_versions(
        conversation, {"industry": "dental_clinics"}, None, guidance_unread=True
    )
    assert marked["guidance_unread"] == "1" and "operator_guidance" not in marked
    assert "guidance_unread" not in learning_audit.pack_versions(
        conversation, {"industry": "dental_clinics"}
    )


def test_the_guidance_read_returns_none_when_it_fails(caplog):
    def boom():
        raise RuntimeError("database down")

    scope = SimpleNamespace(tenant_id="t", environment_id="e")
    session = SimpleNamespace(begin_nested=boom)
    with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
        result = asyncio.run(learning_audit.operator_guidance_of(session, scope))
    assert result is None  # unreadable is None; none written is ""
    assert "pi_reply_audit_guidance_unread" in caplog.text


def test_the_version_takes_no_message_or_customer_input():
    assert learning_audit.prompt_version("Be warm.")
    with pytest.raises(TypeError):
        learning_audit.prompt_version(message="hello")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        learning_audit.prompt_version("Be warm.", "a second argument")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        learning_audit.pack_versions(  # type: ignore[call-arg]
            SimpleNamespace(service_brief={}), {}, message="hello"
        )


# ---- one input at a time, controls ------------------------------------------------------------


def test_exactly_one_input_changes_the_version_and_the_other_two_do_not(monkeypatch):
    """(a) hardcoded prompt, (b) pack file, (c) operator guidance: each alone moves the version,
    and the version returns to the base when it is put back."""
    from app.modules.pi import critique

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _pack_tree(root, FILES)
        base = _version_of(monkeypatch, root)

        monkeypatch.setattr(critique, "SYSTEM", critique.SYSTEM + " changed")
        a = _version_of(monkeypatch, root)
        monkeypatch.undo()
        assert a != base
        assert _version_of(monkeypatch, root) == base

        (root / "industry/a.json").write_bytes(b'{"k": 99}\n')
        b = _version_of(monkeypatch, root)
        (root / "industry/a.json").write_bytes(FILES["industry/a.json"])
        assert b != base
        assert _version_of(monkeypatch, root) == base

        c = _version_of(monkeypatch, root, "Be warm and short.")
        assert c != base
        assert _version_of(monkeypatch, root, None) == base

        assert len({base, a, b, c}) == 4


def test_unrelated_inputs_are_controls_that_do_not_move_the_version(monkeypatch):
    from app.modules.pi import critique, service_conversation

    base = learning_audit.prompt_version()
    monkeypatch.setattr(critique, "NOT_A_PROMPT", "anything", raising=False)
    monkeypatch.setattr(service_conversation, "_SHORT_WORDS", "changed", raising=False)
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() == base


# ---- nothing from the machine or the clock enters the hash ------------------------------------


def test_no_clock_host_name_working_directory_or_environment_enters_the_hash(monkeypatch):
    learning_audit.clear_prompt_cache()
    expected = learning_audit.prompt_version("Be warm.")
    learning_audit.clear_prompt_cache()
    reads: list[str] = []

    def spy(owner, name, label):
        real = getattr(owner, name)

        def wrapper(*args, **kwargs):
            reads.append(label)
            return real(*args, **kwargs)

        return wrapper

    class SpyDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            reads.append("datetime.now")
            return super().now(tz)

        @classmethod
        def utcnow(cls):
            reads.append("datetime.utcnow")
            return super().utcnow()

    real_cwd = Path.cwd

    def spy_cwd(cls):
        reads.append("Path.cwd")
        return real_cwd()

    # Spies record a read and still answer, active only while the version is computed, so a failure
    # is an ordinary assertion and not a crash inside pytest's own use of the clock or the cwd.
    with monkeypatch.context() as scoped:
        for owner, name in (
            (time, "time"),
            (time, "monotonic"),
            (time, "perf_counter"),
            (socket, "gethostname"),
            (os, "getcwd"),
        ):
            scoped.setattr(owner, name, spy(owner, name, f"{owner.__name__}.{name}"))
        scoped.setattr(datetime, "datetime", SpyDatetime)
        scoped.setattr(Path, "cwd", classmethod(spy_cwd))
        scoped.setattr(os, "environ", {})
        got = learning_audit.prompt_version("Be warm.")
    assert reads == [], f"the version read: {reads}"
    assert got == expected


# ---- two fresh processes ----------------------------------------------------------------------

SENSITIVE_ENV = re.compile(
    r"DATABASE|_DSN|DB_|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|NEON|OPENAI|ANTHROPIC"
    r"|^PG|REDIS|SMTP",
    re.IGNORECASE,
)
CODE = (
    "import sys; sys.path.insert(0, sys.argv[1]);"
    "from app.modules.pi import learning_audit as a;"
    "print(a.prompt_version()); print(a.prompt_version('Be warm.'))"
)


def _clean_env(seed: str) -> dict[str, str]:
    """The inherited environment without database, key, token or password variables."""
    env = {k: v for k, v in os.environ.items() if not SENSITIVE_ENV.search(k)}
    env["PYTHONHASHSEED"] = seed
    return env


def _version_in_a_fresh_process(seed: str, cwd: str) -> list[str]:
    result = subprocess.run(  # noqa: S603 - fixed arguments, the path is an argument not code
        [sys.executable, "-c", CODE, str(API_ROOT)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=_clean_env(seed),
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-600:]
    return result.stdout.split()


def test_the_subprocess_environment_is_scrubbed_of_secrets():
    env = _clean_env("1")
    assert "DATABASE_URL" not in env
    assert not [k for k in env if SENSITIVE_ENV.search(k)]


def test_the_same_inputs_give_the_same_version_in_two_fresh_processes():
    """Two separate Python processes, different hash seeds and different working directories, with
    the database and key variables removed from the environment."""
    with tempfile.TemporaryDirectory() as other_cwd:
        first = _version_in_a_fresh_process("1", str(API_ROOT))
        second = _version_in_a_fresh_process("12345", other_cwd)
    assert first == second
    assert first[0] == learning_audit.prompt_version()
    assert first[1] == learning_audit.prompt_version("Be warm.")
