"""FT-D3: `prompt_version` hashes the SOURCE of every prompt-bearing module, every pack file, the
handbook and the operator guidance, so a change to any of them changes the version (Fast-Track plan
FT-D3; platform spec A.2 #8).

Design (changed after the audit): a list of constants can never be complete, so the whole source of
every module under app/modules/pi is hashed (evalkit excluded) unless the module is named on
`learning_audit.NON_PROMPT_MODULES` with a reason. A new module is hashed by default. Any edit to a
hashed module, a comment included, changes the version; the drift check then reports `stale_prompt`
once after the deploy, which is intended (docs/pi-saas/pi-prompt-version.md).

Not covered, stated plainly: behaviour driven by data outside the hashed files (database settings,
learned lessons and examples) and the operator guidance except through its own optional hash.

Scripted checks only: no model, no database."""

import asyncio
import datetime
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.pi import drift_check, learning_audit, spec_handbook

API_ROOT = Path(__file__).resolve().parents[2]
MODEL_CALL = re.compile(
    r"Message\.(system|user|assistant)\(|LLMManager|\.chat\(|\.complete\(|manager\.generate"
    r"|generate_structured|\.structured\("
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    learning_audit.clear_prompt_cache()
    yield
    learning_audit.clear_prompt_cache()


def _tree(root: Path, files: dict[str, str | bytes]) -> Path:
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return root


def _version(monkeypatch, pi_root: Path, packs: Path | None = None, **kwargs) -> str:
    """The version of a temporary pi folder (and packs folder), with its own allowlist if given."""
    monkeypatch.setattr(learning_audit, "PI_ROOT", pi_root)
    if packs is not None:
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", packs)
    if "allow" in kwargs:
        monkeypatch.setattr(learning_audit, "NON_PROMPT_MODULES", kwargs.pop("allow"))
    learning_audit.clear_prompt_cache()
    return learning_audit.prompt_version(kwargs.get("guidance"))


BASE = {
    "prompt.py": 'SYSTEM = "You are pi."\n',
    "other.py": "VALUE = 1\n",
    "models.py": "class Row: pass\n",
    "tools/handlers.py": 'DESC = "a tool"\n',
    "evalkit/cases.py": "CASES = []\n",
}
ALLOW = {"models.py": "table definitions, no prompt text"}


# ---- the guard over the real tree -------------------------------------------------------------


def test_the_version_is_a_short_deterministic_hash():
    version = learning_audit.prompt_version()
    assert re.fullmatch(r"[0-9a-f]{12}", version)
    assert version == learning_audit.prompt_version()


def test_every_module_is_hashed_or_named_on_the_allowlist_with_a_reason():
    """The guard: every .py file under app/modules/pi (evalkit aside) is either hashed or on the
    allowlist with a reason, never both, never neither."""
    every = set(learning_audit.all_module_files())
    hashed = {k for k in learning_audit.prompt_source_files() if not k.startswith("ext/")}
    allowed = set(learning_audit.NON_PROMPT_MODULES)
    assert every == hashed | allowed
    assert not hashed & allowed
    assert all(len(reason) >= 10 for reason in learning_audit.NON_PROMPT_MODULES.values())
    assert "service_conversation.py" in hashed and "tools/handlers.py" in hashed
    assert not [k for k in every if k.startswith("evalkit/")]
    assert "ext/app.ai.media" in learning_audit.prompt_source_files()


def test_a_stale_allowlist_entry_fails():
    missing = [
        k for k in learning_audit.NON_PROMPT_MODULES if k not in learning_audit.all_module_files()
    ]
    assert not missing, missing


def test_an_allowlisted_module_builds_no_model_message_and_calls_no_model():
    offenders = []
    files = learning_audit.all_module_files()
    for label in learning_audit.NON_PROMPT_MODULES:
        text = files[label].read_text(encoding="utf-8", errors="replace")
        if MODEL_CALL.search(text):
            offenders.append(label)
    assert not offenders, offenders


# ---- source files: every kind of edit to a hashed module ---------------------------------------


def test_a_new_module_is_hashed_by_default(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), BASE)
        before = _version(monkeypatch, root, allow=ALLOW)
        _tree(root, {"brand_new.py": "x = 1\n"})
        assert _version(monkeypatch, root, allow=ALLOW) != before


def test_new_text_in_a_hashed_module_changes_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), BASE)
        before = _version(monkeypatch, root, allow=ALLOW)
        new_constant = 'NEW_RULE = "' + ("never promise a date to the owner; " * 5) + '"\n'
        assert len(new_constant) > 150
        with open(root / "other.py", "a", encoding="utf-8") as handle:
            handle.write(new_constant)
        assert _version(monkeypatch, root, allow=ALLOW) != before


@pytest.mark.parametrize(
    ("label", "edit"),
    [
        ("prompt.py", 'SYSTEM = "You are pi, say hello."\n'),  # a constant
        ("prompt.py", 'SYSTEM = "You are pi."\n# a comment\n'),  # a comment counts, by design
        ("prompt.py", 'SYSTEM = "You are pi."\nx = f"Say {1}"\n'),  # an inline f-string
        ("tools/handlers.py", 'DESC = "a different tool"\n'),  # the tools folder is hashed
    ],
)
def test_any_edit_to_a_hashed_module_changes_the_version(monkeypatch, label, edit):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), BASE)
        before = _version(monkeypatch, root, allow=ALLOW)
        (root / label).write_text(edit, encoding="utf-8")
        assert _version(monkeypatch, root, allow=ALLOW) != before


def test_edits_to_a_named_non_prompt_module_or_to_evalkit_do_not_change_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), BASE)
        before = _version(monkeypatch, root, allow=ALLOW)
        (root / "models.py").write_text("class Row:\n    # changed\n    pass\n", encoding="utf-8")
        (root / "evalkit/cases.py").write_text("CASES = [1, 2, 3]\n", encoding="utf-8")
        (root / "notes.txt").write_text("not python", encoding="utf-8")
        os.utime(root / "prompt.py", (1_000_000_000, 1_000_000_000))  # another timestamp
        assert _version(monkeypatch, root, allow=ALLOW) == before


def test_a_module_leaves_the_hash_only_by_being_named_on_the_allowlist(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), BASE)
        before = _version(monkeypatch, root, allow={})
        (root / "models.py").write_text("class Row:\n    pass  # edited\n", encoding="utf-8")
        assert _version(monkeypatch, root, allow={}) != before  # not named: hashed
        assert _version(monkeypatch, root, allow=ALLOW) != before  # now left out: another digest


def test_renaming_or_removing_a_hashed_module_changes_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), BASE)
        before = _version(monkeypatch, root, allow=ALLOW)
        (root / "other.py").rename(root / "renamed.py")
        renamed = _version(monkeypatch, root, allow=ALLOW)
        assert renamed != before
        (root / "renamed.py").unlink()
        assert _version(monkeypatch, root, allow=ALLOW) not in (before, renamed)


def test_line_endings_creation_order_and_location_cannot_change_the_version(monkeypatch):
    crlf = {k: (v.replace("\n", "\r\n") if isinstance(v, str) else v) for k, v in BASE.items()}
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        with tempfile.TemporaryDirectory() as c:
            one = _version(monkeypatch, _tree(Path(a), BASE), allow=ALLOW)
            two = _version(monkeypatch, _tree(Path(b), crlf), allow=ALLOW)
            reordered = dict(reversed(list(BASE.items())))
            three = _version(monkeypatch, _tree(Path(c), reordered), allow=ALLOW)
    assert one == two == three


def test_a_copy_of_the_real_tree_has_the_same_version_and_real_edits_move_it(monkeypatch):
    """The real source is what the version reads: a copy gives the SAME version from another place;
    editing a hashed module of the copy moves it; editing a named non-prompt module does not. Repo
    files are never edited."""
    real = learning_audit.prompt_version()
    ignore = shutil.ignore_patterns("__pycache__", "packs", "fonts", "spec")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "pi"
        shutil.copytree(learning_audit.PI_ROOT, copy, ignore=ignore)
        same = _version(monkeypatch, copy)
        assert same == real
        with open(copy / "models.py", "a", encoding="utf-8") as handle:
            handle.write("\n# an edit to a named non-prompt module\n")
        assert _version(monkeypatch, copy) == real
        with open(copy / "service_conversation.py", "a", encoding="utf-8") as handle:
            handle.write("\n# an edit to a hashed module\n")
        assert _version(monkeypatch, copy) != real


# ---- unreadable files: logged once, never cached as permanent ----------------------------------


def test_an_unreadable_module_is_logged_once_and_retried_on_the_next_call(monkeypatch, caplog):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), {"prompt.py": 'SYSTEM = "x"\n'})
        (root / "broken.py").mkdir()  # a folder named like a module: reading it raises OSError
        monkeypatch.setattr(learning_audit, "PI_ROOT", root)
        monkeypatch.setattr(learning_audit, "NON_PROMPT_MODULES", {})
        learning_audit.clear_prompt_cache()
        with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
            broken = learning_audit.prompt_version()
            again = learning_audit.prompt_version()
        assert broken == again and re.fullmatch(r"[0-9a-f]{12}", broken)
        assert caplog.text.count("pi_prompt_version_unreadable broken.py") == 1  # once
        (root / "broken.py").rmdir()
        (root / "broken.py").write_text("FIXED = 1\n", encoding="utf-8")
        fixed = learning_audit.prompt_version()  # the failure was not cached
        assert fixed != broken


def test_an_unreadable_pack_file_or_handbook_is_logged_and_never_breaks_the_version(
    monkeypatch, caplog
):
    with tempfile.TemporaryDirectory() as tmp:
        packs = Path(tmp) / "packs"
        packs.mkdir()
        (packs / "x.json").mkdir()  # unreadable as a file
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", packs)
        monkeypatch.setattr(spec_handbook, "SUPERSESSION", Path(tmp) / "missing.json")
        learning_audit.clear_prompt_cache()
        with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
            version = learning_audit.prompt_version()
        assert re.fullmatch(r"[0-9a-f]{12}", version)
        assert "pi_prompt_version_unreadable x.json" in caplog.text
        assert "pi_prompt_version_unreadable spec/missing.json" in caplog.text


# ---- the pack files ---------------------------------------------------------------------------

FILES = {
    "industry/a.json": b'{"k": 1}\n',
    "industry/b.json": b'{"k": 2}\n',
    "library/x.json": b'{"x": [1, 2]}\n',
}


def test_a_pack_file_edit_add_removal_or_rename_changes_the_version(monkeypatch):
    with tempfile.TemporaryDirectory() as pi, tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(pi), BASE)
        packs = _tree(Path(tmp), {"industry/a.json": b'{"k": 1}'})
        base = _version(monkeypatch, root, packs, allow=ALLOW)
        assert _version(monkeypatch, root, packs, allow=ALLOW) == base
        (packs / "industry/a.json").write_bytes(b'{"k": 2}')
        edited = _version(monkeypatch, root, packs, allow=ALLOW)
        assert edited != base
        (packs / "industry/b.json").write_bytes(b"{}")
        added = _version(monkeypatch, root, packs, allow=ALLOW)
        assert added not in (base, edited)
        (packs / "industry/b.json").unlink()
        assert _version(monkeypatch, root, packs, allow=ALLOW) == edited
        (packs / "industry/a.json").rename(packs / "industry/c.json")
        assert _version(monkeypatch, root, packs, allow=ALLOW) != edited


def test_changing_a_real_pack_file_changes_the_version_using_a_temp_copy(monkeypatch):
    real = learning_audit.PACKS_ROOT
    assert real.is_dir() and any(real.rglob("*.json"))
    learning_audit.clear_prompt_cache()
    real_version = learning_audit.prompt_version()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "packs"
        shutil.copytree(real, copy)
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", copy)
        learning_audit.clear_prompt_cache()
        assert learning_audit.prompt_version() == real_version
        target = sorted(copy.rglob("*.json"))[0]
        target.write_bytes(target.read_bytes() + b"\n ")
        learning_audit.clear_prompt_cache()
        assert learning_audit.prompt_version() != real_version


def test_pack_line_endings_order_location_and_non_json_files_cannot_change_the_version(
    monkeypatch,
):
    crlf = {k: v.replace(b"\n", b"\r\n") for k, v in FILES.items()}
    with tempfile.TemporaryDirectory() as pi, tempfile.TemporaryDirectory() as a:
        with tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as c:
            root = _tree(Path(pi), BASE)
            one = _version(monkeypatch, root, _tree(Path(a), FILES), allow=ALLOW)
            two = _version(monkeypatch, root, _tree(Path(b), crlf), allow=ALLOW)
            rev = dict(reversed(list(FILES.items())))
            three = _version(monkeypatch, root, _tree(Path(c), rev), allow=ALLOW)
            assert one == two == three
            (Path(a) / "industry/notes.txt").write_text("not a pack", encoding="utf-8")
            os.utime(Path(a) / "industry/a.json", (1_000_000_000, 1_000_000_000))
            assert _version(monkeypatch, root, Path(a), allow=ALLOW) == one


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


# ---- one input at a time, and what the drift check does with a changed version -----------------


def test_exactly_one_input_changes_the_version_and_the_other_two_do_not(monkeypatch):
    """(a) a hardcoded prompt (module source), (b) a pack file, (c) the operator guidance: each
    alone moves the version, and the version returns to the base when it is put back."""
    with tempfile.TemporaryDirectory() as pi, tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(pi), BASE)
        packs = _tree(Path(tmp), FILES)
        base = _version(monkeypatch, root, packs, allow=ALLOW)

        (root / "prompt.py").write_text('SYSTEM = "You are pi, changed."\n', encoding="utf-8")
        a = _version(monkeypatch, root, packs, allow=ALLOW)
        (root / "prompt.py").write_text(BASE["prompt.py"], encoding="utf-8")
        assert a != base
        assert _version(monkeypatch, root, packs, allow=ALLOW) == base

        (packs / "industry/a.json").write_bytes(b'{"k": 99}\n')
        b = _version(monkeypatch, root, packs, allow=ALLOW)
        (packs / "industry/a.json").write_bytes(FILES["industry/a.json"])
        assert b != base
        assert _version(monkeypatch, root, packs, allow=ALLOW) == base

        c = _version(monkeypatch, root, packs, allow=ALLOW, guidance="Be warm and short.")
        assert c != base
        assert len({base, a, b, c}) == 4


def test_a_changed_version_is_a_one_time_stale_prompt_finding_not_an_error():
    """The documented consequence of hashing source: after a deploy that edited any hashed module,
    replies stamped with the old version read as stale until a new reply is stamped."""
    summary = drift_check.stamp_summary(
        [{"prompt_version": "oldversion01", "pack_versions": {"build": "x"}}],
        {"prompt": learning_audit.prompt_version()},
    )
    codes = [f.code for f in drift_check.stamp_findings(summary)]
    assert codes == ["stale_prompt"]
    fresh = drift_check.stamp_summary(
        [{"prompt_version": learning_audit.prompt_version(), "pack_versions": {"build": "x"}}],
        {"prompt": learning_audit.prompt_version()},
    )
    assert drift_check.stamp_findings(fresh) == []


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
