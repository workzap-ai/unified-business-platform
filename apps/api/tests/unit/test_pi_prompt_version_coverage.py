"""FT-D3: `prompt_version` covers the hardcoded prompts, the pack files and the operator guidance,
so a change to any of them changes the version (Fast-Track plan, FT-D3; platform spec A.2 #8).

Scripted checks only: no model, no database."""

import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.pi import learning_audit

API_ROOT = Path(__file__).resolve().parents[2]
CONSTANTS = [(m, n) for m, names in learning_audit.PROMPT_CONSTANTS for n in names]
EXEMPT = {"_SHORT_WORDS"}  # a word list, not prompt text


@pytest.fixture(autouse=True)
def _fresh_cache():
    learning_audit.clear_prompt_cache()
    yield
    learning_audit.clear_prompt_cache()


def test_the_version_is_a_short_deterministic_hash():
    version = learning_audit.prompt_version()
    assert re.fullmatch(r"[0-9a-f]{12}", version)
    assert version == learning_audit.prompt_version()


@pytest.mark.parametrize(("module", "name"), CONSTANTS)
def test_changing_a_hardcoded_prompt_changes_the_version(monkeypatch, module, name):
    target = importlib.import_module(f"app.modules.pi.{module}")
    before = learning_audit.prompt_version()
    original = getattr(target, name)
    changed = {**original, "_x": "changed"} if isinstance(original, dict) else original + " changed"
    monkeypatch.setattr(target, name, changed)
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() != before, f"{module}.{name} is not in the version"


def test_every_large_prompt_constant_of_a_covered_module_is_registered():
    """A new long prompt string added to one of these modules must be registered, or it would
    change pi's behaviour without changing the version."""
    registered = set(CONSTANTS)
    missing: list[str] = []
    for module in dict(learning_audit.PROMPT_CONSTANTS):
        target = importlib.import_module(f"app.modules.pi.{module}")
        covered_text = [
            getattr(target, n) for m, n in CONSTANTS if m == module and hasattr(target, n)
        ]
        for name, value in vars(target).items():
            if name.isupper() and isinstance(value, str) and len(value) > 400:
                # a body that is part of a registered constant (DIAGNOSE_RULES is _DIAGNOSE_BODY
                # plus more) is covered through it
                inside = any(isinstance(t, str) and value in t for t in covered_text)
                if (module, name) not in registered and name not in EXEMPT and not inside:
                    missing.append(f"{module}.{name}")
    assert not missing, missing


def test_the_prompt_modules_beyond_the_registry_have_no_unregistered_large_prompts():
    """The modules the registry does not list but that hold a model system prompt."""
    for module in ("brain_prompt", "solution_ideas", "hypothesis_reply", "idea_filter", "box_doc"):
        target = importlib.import_module(f"app.modules.pi.{module}")
        for name, value in vars(target).items():
            if name.isupper() and isinstance(value, str) and len(value) > 400:
                assert (module, name) in set(CONSTANTS), f"{module}.{name}"


def test_a_pack_file_change_adds_or_removes_changes_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "industry").mkdir()
        (root / "industry" / "a.json").write_text('{"k": 1}', encoding="utf-8")
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", root)
        learning_audit.clear_prompt_cache()
        base = learning_audit.prompt_version()
        learning_audit.clear_prompt_cache()
        assert learning_audit.prompt_version() == base  # unchanged files, same version
        (root / "industry" / "a.json").write_text('{"k": 2}', encoding="utf-8")
        learning_audit.clear_prompt_cache()
        edited = learning_audit.prompt_version()
        assert edited != base
        (root / "industry" / "b.json").write_text("{}", encoding="utf-8")
        learning_audit.clear_prompt_cache()
        added = learning_audit.prompt_version()
        assert added not in (base, edited)
        (root / "industry" / "b.json").unlink()
        learning_audit.clear_prompt_cache()
        assert learning_audit.prompt_version() == edited


def test_a_renamed_pack_file_changes_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", root)
        learning_audit.clear_prompt_cache()
        before = learning_audit.prompt_version()
        (root / "a.json").rename(root / "b.json")
        learning_audit.clear_prompt_cache()
        assert learning_audit.prompt_version() != before


def test_the_real_pack_tree_is_in_the_version():
    root = learning_audit.PACKS_ROOT
    assert root.is_dir() and any(root.rglob("*.json"))


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
    assert digest != learning_audit.operator_guidance_digest(text + " Also be brief.")  # a change
    assert learning_audit.operator_guidance_digest(f"  {text}\n") == digest  # whitespace does not


def test_the_audit_stamp_records_the_guidance_hash_and_never_its_text():
    conversation = SimpleNamespace(service_brief={})
    secret = "Always mention the Karachi branch phone 02111222333."
    with_guidance = learning_audit.pack_versions(
        conversation, {"industry": "dental_clinics"}, operator_guidance=secret
    )
    assert re.fullmatch(r"[0-9a-f]{12}", with_guidance["operator_guidance"])
    assert secret not in json.dumps(with_guidance) and "02111222333" not in json.dumps(
        with_guidance
    )
    # The old shape is untouched when there is no guidance (stored rows stay readable).
    plain = learning_audit.pack_versions(conversation, {"industry": "dental_clinics"})
    assert "operator_guidance" not in plain
    assert list(plain) == ["dental_clinics"]
    assert (
        learning_audit.pack_versions(
            conversation, {"industry": "dental_clinics"}, operator_guidance=""
        )
        == plain
    )


def test_the_version_does_not_depend_on_any_message_or_customer_input():
    """The only caller-supplied input is the operator guidance; two calls with the same guidance
    agree, and nothing else (a message, a phone number, a conversation) can reach the hash."""
    import inspect

    params = list(inspect.signature(learning_audit.prompt_version).parameters)
    assert params == ["operator_guidance"]


def _version_in_a_fresh_process(seed: str, cwd: str) -> list[str]:
    code = (
        "import sys; sys.path.insert(0, r'" + str(API_ROOT) + "');"
        "from app.modules.pi import learning_audit as a;"
        "print(a.prompt_version()); print(a.prompt_version('Be warm.'))"
    )
    result = subprocess.run(  # noqa: S603 - fixed arguments
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONHASHSEED": seed},
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]
    return result.stdout.split()


def test_the_same_inputs_give_the_same_version_in_two_fresh_processes():
    """Two separate Python processes, different hash seeds and different working directories."""
    with tempfile.TemporaryDirectory() as other_cwd:
        first = _version_in_a_fresh_process("1", str(API_ROOT))
        second = _version_in_a_fresh_process("12345", other_cwd)
    assert first == second
    assert first[0] == learning_audit.prompt_version()
    assert first[1] == learning_audit.prompt_version("Be warm.")


def _pack_tree(root: Path, files: dict[str, bytes], order: list[str] | None = None) -> None:
    for name in order or list(files):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[name])


def _version_of(monkeypatch, root: Path, guidance: str | None = None) -> str:
    monkeypatch.setattr(learning_audit, "PACKS_ROOT", root)
    learning_audit.clear_prompt_cache()
    return learning_audit.prompt_version(guidance)


FILES = {
    "industry/a.json": b'{"k": 1}\n',
    "industry/b.json": b'{"k": 2}\n',
    "library/x.json": b'{"x": [1, 2]}\n',
}


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


def test_no_clock_host_name_working_directory_or_environment_enters_the_hash(monkeypatch):
    import socket
    import time

    learning_audit.clear_prompt_cache()
    expected = learning_audit.prompt_version("Be warm.")
    learning_audit.clear_prompt_cache()
    reads: list[str] = []

    def spy(owner, name):
        real = getattr(owner, name)

        def wrapper(*args, **kwargs):
            reads.append(name)
            return real(*args, **kwargs)

        return wrapper

    # Spies that record a read (and still answer), active only while the version is computed, so a
    # failure shows as an ordinary assertion and not inside pytest's own use of the clock or cwd.
    with monkeypatch.context() as scoped:
        for owner, name in ((time, "time"), (socket, "gethostname"), (os, "getcwd")):
            scoped.setattr(owner, name, spy(owner, name))
        scoped.setattr(os, "environ", {})
        got = learning_audit.prompt_version("Be warm.")
    assert reads == [], f"the version read: {reads}"
    assert got == expected


def test_touching_a_pack_file_or_adding_a_non_json_file_does_not_change_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _pack_tree(root, FILES)
        base = _version_of(monkeypatch, root)
        os.utime(root / "industry/a.json", (1_000_000_000, 1_000_000_000))  # another timestamp
        (root / "industry/notes.txt").write_text("not a pack", encoding="utf-8")
        assert _version_of(monkeypatch, root) == base


def test_exactly_one_input_changes_the_version_and_the_other_two_do_not(monkeypatch):
    """(a) hardcoded prompt, (b) pack file, (c) operator guidance: each alone moves the version,
    and the version returns to the base when it is put back."""
    from app.modules.pi import critique

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _pack_tree(root, FILES)
        base = _version_of(monkeypatch, root)

        # (a) only a hardcoded prompt changes
        monkeypatch.setattr(critique, "SYSTEM", critique.SYSTEM + " changed")
        a = _version_of(monkeypatch, root)
        monkeypatch.undo()
        assert a != base
        assert _version_of(monkeypatch, root) == base

        # (b) only a pack file changes
        (root / "industry/a.json").write_bytes(b'{"k": 99}\n')
        b = _version_of(monkeypatch, root)
        (root / "industry/a.json").write_bytes(FILES["industry/a.json"])
        assert b != base
        assert _version_of(monkeypatch, root) == base

        # (c) only the operator guidance changes
        c = _version_of(monkeypatch, root, "Be warm and short.")
        assert c != base
        assert _version_of(monkeypatch, root, None) == base

        assert len({base, a, b, c}) == 4


def test_unrelated_inputs_are_controls_that_do_not_move_the_version(monkeypatch):
    """A constant that is not a prompt, a new attribute on a covered module and a word list change
    nothing."""
    from app.modules.pi import critique, service_conversation

    learning_audit.clear_prompt_cache()
    base = learning_audit.prompt_version()
    monkeypatch.setattr(critique, "NOT_A_PROMPT", "anything", raising=False)
    monkeypatch.setattr(service_conversation, "_SHORT_WORDS", "changed", raising=False)
    learning_audit.clear_prompt_cache()
    assert learning_audit.prompt_version() == base


def test_a_missing_module_or_constant_never_breaks_the_version(monkeypatch):
    monkeypatch.setattr(
        learning_audit,
        "PROMPT_CONSTANTS",
        (("no_such_module_xyz", ("A",)), ("critique", ("NO_SUCH_NAME",))),
    )
    learning_audit.clear_prompt_cache()
    assert re.fullmatch(r"[0-9a-f]{12}", learning_audit.prompt_version())
