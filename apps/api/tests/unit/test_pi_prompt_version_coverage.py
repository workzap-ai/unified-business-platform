"""FT-D3: `prompt_version` hashes the SOURCE of every prompt-bearing module, every pack file, the
handbook and the operator guidance, so a change to any of them changes the version (Fast-Track plan
FT-D3; platform spec A.2 #8).

Design: a list of constants can never be complete, so the whole source of every module under
app/modules/pi is hashed (evalkit excluded) unless the module is named on
`learning_audit.NON_PROMPT_MODULES` with a reason. A new module is hashed by default. An allowlisted
module is checked by AST (direct use only): it may not import from app.ai in any form, reference a
model client or gateway, call a model method or hold a string or f-string over 80 characters
anywhere. Any edit to a hashed module,
a comment included, changes the version (docs/pi-saas/pi-prompt-version.md). An empty or frozen
source folder gives a version starting with "!", never a silent constant.

Not covered, stated plainly: behaviour driven by data outside the hashed files (database settings,
learned lessons and examples) and the operator guidance except through its own optional hash.

Scripted checks only: no model, no database."""

import ast
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

from app.modules.pi import drift_check, learning_audit

API_ROOT = Path(__file__).resolve().parents[2]

# The AST guard for an allowlisted module (a module that leaves the hash must not reach a model).
# It is DIRECT-ONLY: it sees an import, a reference, a call or a long text written in that module's
# own source. A model reached through an object passed in as an argument, through another module's
# helper, or through a name built at run time is not seen.
FORBIDDEN_NAMES = {"Message", "LLMManager", "build_llm_manager", "Gateway", "route_message"}
FORBIDDEN_CALLS = {
    "system",
    "complete",
    "chat",
    "structured",
    "generate_structured",
    "complete_with_images",
}
# More model-method names. Checked against the real allowlist: `stream` tripped routes.py
# (`request.stream()`, an HTTP body read); that module is hashed instead of allowlisted.
EXTRA_CALL_CANDIDATES = ("stream", "generate", "run", "invoke", "ask", "respond", "embed")
FORBIDDEN_CALLS = FORBIDDEN_CALLS | set(EXTRA_CALL_CANDIDATES)
LONG_TEXT = 80  # characters of one string (or f-string text) anywhere before it counts as a prompt
# A legitimate long text in an allowlisted module: (module, module-level name) -> reason.
ALLOWED_LONG_TEXT = {
    (
        "drift_check.py",
        "_LISTEN_ONLY",
    ): "a regex that finds listen-only phrases in the prompt files",
}


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ids.add(id(first.value))
    return ids


def model_access_findings(source: str, label: str = "", calls: set[str] | None = None) -> list[str]:
    """Why this source may not be allowlisted (direct use only): an import from app.ai in any form
    (absolute, `from app import ai`, relative, `app.ai.x` attribute use, a string naming app.ai), a
    model client, gateway or router name (aliased or not), a model-method call, or any string or
    f-string text over LONG_TEXT characters anywhere (docstrings and the named exception aside)."""
    forbidden_calls = FORBIDDEN_CALLS if calls is None else calls
    tree = ast.parse(source)
    found: set[str] = set()
    skip = _docstring_ids(tree)
    for node in tree.body:  # the named long-text exceptions are module-level assignments
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if (label, getattr(target, "id", "?")) in ALLOWED_LONG_TEXT:
                skip.update(id(sub) for sub in ast.walk(node.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0:
                if module.split(".")[:2] == ["app", "ai"]:
                    found.add(f"import from {module}")
                if module == "app" and any(a.name == "ai" for a in node.names):
                    found.add("from app import ai")
            else:
                if module.split(".")[0] == "ai" or (
                    module == "" and any(a.name == "ai" for a in node.names)
                ):
                    found.add("relative import of ai")
            found.update(f"imports {a.name}" for a in node.names if a.name in FORBIDDEN_NAMES)
        elif isinstance(node, ast.Import):
            found.update(
                f"import {a.name}" for a in node.names if a.name.split(".")[:2] == ["app", "ai"]
            )
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.add(f"name {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_NAMES:
                found.add(f"attribute {node.attr}")
            if node.attr == "ai" and isinstance(node.value, ast.Name) and node.value.id == "app":
                found.add("app.ai attribute use")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_calls
        ):
            found.add(f"call .{node.func.attr}()")
        if id(node) in skip:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith("app.ai"):
                found.add("a string naming app.ai (dynamic import)")
            if len(node.value) > LONG_TEXT:
                found.add(f"long text (line {node.lineno})")
        elif isinstance(node, ast.JoinedStr):
            literal = sum(
                len(v.value)
                for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
            if literal > LONG_TEXT:
                found.add(f"long f-string (line {node.lineno})")
    return sorted(found)


def allowlist_offenders(files: dict[str, Path], allowed) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for label in allowed:
        found = model_access_findings(files[label].read_text(encoding="utf-8"), label)
        if found:
            out[label] = found
    return out


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
    """The version of a temporary pi folder (and packs folder), with its own allowlist if given.
    A temporary folder is small, so the minimum module count is lowered unless `strict`."""
    monkeypatch.setattr(learning_audit, "PI_ROOT", pi_root)
    if packs is not None:
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", packs)
    if "allow" in kwargs:
        monkeypatch.setattr(learning_audit, "NON_PROMPT_MODULES", kwargs.pop("allow"))
    if not kwargs.pop("strict", False):
        monkeypatch.setattr(learning_audit, "MIN_HASHED_MODULES", 1)
        monkeypatch.setattr(learning_audit, "REQUIRED_MODULES", ())
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
ALIASED_MODEL_IMPORT = (
    "from app.ai.messages import Message as M\n\n\ndef f():\n    return M.system('x')\n"
)


# ---- the guard over the real tree -------------------------------------------------------------


def test_the_version_is_a_short_deterministic_hash():
    version = learning_audit.prompt_version()
    assert re.fullmatch(r"[0-9a-f]{12}", version)
    assert version == learning_audit.prompt_version()


def test_the_allowlist_entries_exist_have_a_reason_and_the_core_modules_stay_hashed():
    every = set(learning_audit.all_module_files())
    hashed = {k for k in learning_audit.prompt_source_files() if not k.startswith("ext/")}
    allowed = set(learning_audit.NON_PROMPT_MODULES)
    assert not allowed - every, sorted(allowed - every)  # a stale entry fails
    assert not hashed & allowed
    assert all(len(reason) >= 10 for reason in learning_audit.NON_PROMPT_MODULES.values())
    assert set(learning_audit.REQUIRED_MODULES) <= hashed
    assert len(hashed) >= learning_audit.MIN_HASHED_MODULES
    assert "service_conversation.py" in hashed and "tools/handlers.py" in hashed
    assert "learning_audit.py" in hashed and "config_routes.py" in hashed
    assert "routes.py" in hashed and "brain_erase_routes.py" in hashed  # tripped the AST guard
    assert not [k for k in every if k.startswith("evalkit/")]


def test_the_external_prompt_modules_are_hashed():
    sources = learning_audit.prompt_source_files()
    assert "ext/app.ai.media" in sources
    assert "ext/app.modules.pi_saas.proposal_writer" in sources
    assert all(path.is_file() for label, path in sources.items() if label.startswith("ext/"))


def test_a_real_allowlisted_module_reaches_no_model_by_ast():
    """The real allowlist passes the AST guard: no import from app.ai, no model client, gateway or
    router, no model-method call, no long module-level text."""
    offenders = allowlist_offenders(
        learning_audit.all_module_files(), learning_audit.NON_PROMPT_MODULES
    )
    assert not offenders, offenders


@pytest.mark.parametrize(
    "source",
    [
        "from app.ai.messages import Message as M\nM.system('x')\n",  # aliased message class
        "from app.ai.messages import Message as M\nx = 1\n",  # import alone, from app.ai
        "from somewhere import build_llm_manager as b\nb()\n",  # lower-case manager factory
        "import x\nx.Gateway(1)\n",  # gateway through an attribute
        "route_message(1)\n",  # router call
        "async def f(m):\n    await m.complete_with_images(1)\n",
        "def f(m):\n    m.generate_structured(1)\n",
        "def f(m):\n    m.chat(1)\n",
        "import app.ai.media\n",
        "TEXT = '" + "x" * 100 + "'\n",  # a long module-level constant
        "TEXTS = {'a': '" + "y" * 100 + "'}\n",  # long text inside a table
    ],
)
def test_the_ast_guard_flags_every_way_a_module_can_reach_a_model(source):
    assert model_access_findings(source)


@pytest.mark.parametrize(
    "source",
    [
        "class Row:\n    id = 1\n",
        "NAME = 'short'\n",
        "from fastapi import APIRouter\nrouter = APIRouter()\n",
        "def f(x):\n    return x.name\n",
    ],
)
def test_the_ast_guard_passes_a_plain_module(source):
    assert model_access_findings(source) == []


def test_an_aliased_model_import_in_an_allowlisted_temp_module_fails_the_guard():
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(
            Path(tmp),
            {
                "models.py": "class Row: pass\n",
                "routes.py": ALIASED_MODEL_IMPORT,
            },
        )
        files = learning_audit.all_module_files(root)
        assert allowlist_offenders(files, ["models.py"]) == {}
        offenders = allowlist_offenders(files, ["models.py", "routes.py"])
        assert list(offenders) == ["routes.py"]


# ---- an empty or frozen source folder is marked, not a silent constant --------------------------


def test_an_empty_source_folder_gives_a_marked_version_logged_once_and_never_cached(
    monkeypatch, caplog
):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        packs = _tree(Path(tmp) / "packs", {"industry/a.json": b"{}"})
        monkeypatch.setattr(learning_audit, "PI_ROOT", root)
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", packs)
        learning_audit.clear_prompt_cache()
        with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
            first = learning_audit.prompt_version()
            second = learning_audit.prompt_version()
        assert first == second and first.startswith("!") and len(first) == 12
        assert caplog.text.count("pi_prompt_version_sources_incomplete") == 1  # once
        _tree(root, {f"m{i}.py": f"X = {i}\n" for i in range(120)})
        _tree(root, {"service_conversation.py": "A = 1\n", "runtime.py": "B = 2\n"})
        real_size = learning_audit.prompt_version()  # not cached: the failure was retried
        assert not real_size.startswith("!") and real_size != first


def test_a_source_folder_without_the_core_modules_is_marked_incomplete(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), {f"m{i}.py": f"X = {i}\n" for i in range(120)})
        marked = _version(monkeypatch, root, strict=True)
        assert marked.startswith("!")
        _tree(root, {"service_conversation.py": "A = 1\n", "runtime.py": "B = 2\n"})
        assert not _version(monkeypatch, root, strict=True).startswith("!")


def test_a_marked_version_stays_marked_with_guidance():
    with tempfile.TemporaryDirectory() as tmp:
        learning_audit.PI_ROOT, saved = Path(tmp), learning_audit.PI_ROOT
        try:
            learning_audit.clear_prompt_cache()
            assert learning_audit.prompt_version("Be warm.").startswith("!")
        finally:
            learning_audit.PI_ROOT = saved
            learning_audit.clear_prompt_cache()


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
        hashed = _version(monkeypatch, root, allow={})
        assert hashed != before  # not named: its edit moves the version
        left_out = _version(monkeypatch, root, allow=ALLOW)
        assert left_out != hashed  # named: it is no longer part of the digest at all
        (root / "models.py").write_text("class Row:\n    pass  # edited again\n", encoding="utf-8")
        assert _version(monkeypatch, root, allow=ALLOW) == left_out  # and edits no longer count


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
        assert _version(monkeypatch, copy, strict=True) == real
        with open(copy / "models.py", "a", encoding="utf-8") as handle:
            handle.write("\n# an edit to a named non-prompt module\n")
        assert _version(monkeypatch, copy, strict=True) == real
        with open(copy / "service_conversation.py", "a", encoding="utf-8") as handle:
            handle.write("\n# an edit to a hashed module\n")
        assert _version(monkeypatch, copy, strict=True) != real


# ---- unreadable files: logged once, marked, never cached ---------------------------------------


def test_an_unreadable_module_is_logged_once_marked_and_retried_on_the_next_call(
    monkeypatch, caplog
):
    with tempfile.TemporaryDirectory() as tmp:
        root = _tree(Path(tmp), {"prompt.py": 'SYSTEM = "x"\n'})
        (root / "broken.py").mkdir()  # a folder named like a module: reading it raises OSError
        monkeypatch.setattr(learning_audit, "PI_ROOT", root)
        monkeypatch.setattr(learning_audit, "NON_PROMPT_MODULES", {})
        monkeypatch.setattr(learning_audit, "MIN_HASHED_MODULES", 1)
        monkeypatch.setattr(learning_audit, "REQUIRED_MODULES", ())
        learning_audit.clear_prompt_cache()
        with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
            broken = learning_audit.prompt_version()
            again = learning_audit.prompt_version()
        assert broken == again and broken.startswith("!") and len(broken) == 12
        assert caplog.text.count("pi_prompt_version_unreadable broken.py") == 1  # once
        (root / "broken.py").rmdir()
        (root / "broken.py").write_text("FIXED = 1\n", encoding="utf-8")
        fixed = learning_audit.prompt_version()  # the failure was not cached
        assert fixed != broken and not fixed.startswith("!")


def test_an_unreadable_pack_file_or_handbook_is_logged_and_marked(monkeypatch, caplog):
    from app.modules.pi import spec_handbook

    with tempfile.TemporaryDirectory() as tmp:
        packs = Path(tmp) / "packs"
        packs.mkdir()
        (packs / "x.json").mkdir()  # unreadable as a file
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", packs)
        monkeypatch.setattr(spec_handbook, "SUPERSESSION", Path(tmp) / "missing.json")
        learning_audit.clear_prompt_cache()
        with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
            version = learning_audit.prompt_version()
        assert version.startswith("!") and len(version) == 12
        assert "pi_prompt_version_unreadable x.json" in caplog.text
        assert "pi_prompt_version_unreadable spec/missing.json" in caplog.text


def test_the_two_handbook_files_are_read_once_per_process_and_cleared_with_the_rest(monkeypatch):
    reads: list[str] = []
    real = learning_audit._read

    def counting(path, label):
        if label.startswith("spec/"):
            reads.append(label)
        return real(path, label)

    monkeypatch.setattr(learning_audit, "_read", counting)
    learning_audit.clear_prompt_cache()
    learning_audit.prompt_version()
    learning_audit.prompt_version("Be warm.")
    learning_audit.prompt_version()
    assert len(reads) == 2  # handbook and supersession, once
    learning_audit.clear_prompt_cache()
    learning_audit.prompt_version()
    assert len(reads) == 4


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
    assert "pi_reply_audit_guidance_unread RuntimeError" in caplog.text  # the error type only
    assert "database down" not in caplog.text and "Traceback" not in caplog.text


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


def test_a_changed_version_keeps_stale_prompt_firing_until_a_reply_is_stamped():
    """The documented consequence of hashing source: after a deploy that edited any hashed module
    EVERY drift run reports `stale_prompt` until a reply is stamped with the new version (a quiet
    workspace keeps it until its next reply); it is not a once-only finding."""
    live = learning_audit.prompt_version()
    stale = drift_check.stamp_summary(
        [{"prompt_version": "oldversion01", "pack_versions": {"build": "x"}}], {"prompt": live}
    )
    for _run in range(3):  # three drift runs, no new reply in between
        assert [f.code for f in drift_check.stamp_findings(stale)] == ["stale_prompt"]
    fresh = drift_check.stamp_summary(
        [{"prompt_version": live, "pack_versions": {"build": "x"}}], {"prompt": live}
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


def test_report_the_hashed_file_count_and_the_first_call_time(capsys):
    """Printed, not asserted: how many files are hashed and how long the first call takes."""
    sources = learning_audit.prompt_source_files()
    packs = list(learning_audit.PACKS_ROOT.rglob("*.json"))
    learning_audit.clear_prompt_cache()
    start = time.perf_counter()
    learning_audit.prompt_version()
    first = time.perf_counter() - start
    start = time.perf_counter()
    learning_audit.prompt_version()
    cached = time.perf_counter() - start
    with capsys.disabled():
        print(
            f"\nFT-D3 hashed source files: {len(sources)}; pack files: {len(packs)}; "
            f"first call {first * 1000:.1f} ms; cached call {cached * 1000:.3f} ms"
        )
    assert len(sources) > 0


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


# ---- the AST guard: more ways round it, and plain modules that must pass ------------------------


@pytest.mark.parametrize(
    "source",
    [
        "from app import ai\n",
        "import app\nclient = app.ai.manager\n",
        "from .ai import manager\n",
        "from ..ai.manager import build\n",
        "from . import ai\n",
        "import importlib\nmodule = importlib.import_module('app.ai.manager')\n",
        "def f():\n    return '" + "z" * 100 + "'\n",  # a long text inside a function
        "def f(x):\n    return f'" + "a" * 100 + "{x}'\n",  # a long f-string
        "class C:\n    note = '" + "b" * 100 + "'\n",  # a long text in a class body
        "def f(m):\n    return m.stream(1)\n",
        "def f(m):\n    return m.generate(1)\n",
        "def f(m):\n    return m.run(1)\n",
        "def f(m):\n    return m.invoke(1)\n",
        "def f(m):\n    return m.ask(1)\n",
        "def f(m):\n    return m.respond(1)\n",
        "def f(m):\n    return m.embed(1)\n",
    ],
)
def test_the_ast_guard_flags_the_further_bypasses(source):
    assert model_access_findings(source)


@pytest.mark.parametrize(
    "source",
    [
        "def f():\n    '''" + "d" * 120 + "'''\n    return 1\n",  # a long docstring
        "'''" + "m" * 120 + "'''\nX = 1\n",  # a long module docstring
        "class C:\n    '''" + "c" * 120 + "'''\n    x = 1\n",
        "def f(x):\n    return f'short {x} text'\n",
        "import os\n\n\ndef f(path):\n    return os.path.join(path, 'a')\n",
    ],
)
def test_the_ast_guard_passes_docstrings_and_short_text(source):
    assert model_access_findings(source) == []


def test_the_named_long_text_exception_applies_only_to_that_module_and_name():
    source = "_LISTEN_ONLY = '" + "r" * 120 + "'\n"
    assert model_access_findings(source, "drift_check.py") == []
    assert model_access_findings(source, "other.py")
    assert model_access_findings(source.replace("_LISTEN_ONLY", "_OTHER"), "drift_check.py")
    leaking = source + "def f():\n    return '" + "s" * 100 + "'\n"
    assert model_access_findings(leaking, "drift_check.py")  # the exception is not a blanket


def test_the_extra_model_method_names_are_in_force_and_the_real_allowlist_is_clean():
    assert set(EXTRA_CALL_CANDIDATES) <= FORBIDDEN_CALLS
    offenders = allowlist_offenders(
        learning_audit.all_module_files(), learning_audit.NON_PROMPT_MODULES
    )
    assert not offenders, offenders


# ---- an empty or missing packs folder is marked like a short source set ------------------------


def test_an_empty_or_missing_packs_folder_is_marked_logged_once_and_never_cached(
    monkeypatch, caplog
):
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "empty"
        empty.mkdir()
        missing = Path(tmp) / "missing"
        for label, packs in (("empty", empty), ("missing", missing)):
            caplog.clear()
            monkeypatch.setattr(learning_audit, "PACKS_ROOT", packs)
            learning_audit.clear_prompt_cache()
            with caplog.at_level(logging.WARNING, logger=learning_audit.logger.name):
                first = learning_audit.prompt_version()
                second = learning_audit.prompt_version()
            assert first == second and first.startswith("!") and len(first) == 12, label
            assert caplog.text.count("pi_prompt_version_packs_incomplete") == 1, label
        _tree(empty, {"industry/a.json": b"{}"})
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", empty)
        assert not learning_audit.prompt_version().startswith("!")  # retried, not cached


def test_a_packs_folder_without_an_industry_pack_is_marked(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        packs = _tree(Path(tmp), {"library/x.json": b"{}"})
        monkeypatch.setattr(learning_audit, "PACKS_ROOT", packs)
        learning_audit.clear_prompt_cache()
        assert learning_audit.prompt_version().startswith("!")
        _tree(packs, {"industry/a.json": b"{}"})
        assert not learning_audit.prompt_version().startswith("!")


# ---- no new prompt-like data file can sit outside the hash --------------------------------------

DATA_EXTENSIONS = {".txt", ".md", ".jinja", ".j2", ".yaml", ".yml", ".tmpl", ".prompt"}
ALLOWED_DATA_FILES = {"fonts/OFL.txt": "the licence text of the bundled font, not a prompt"}


def test_no_unhashed_prompt_like_data_file_appears_under_the_pi_folder():
    """Only .py sources, packs/*.json and the handbook JSON are hashed; a text, markdown, template
    or yaml file under the pi folder would reach the model (or not) without moving the version."""
    root = learning_audit.PI_ROOT
    found = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in DATA_EXTENSIONS
        and "__pycache__" not in p.parts
        and "evalkit" not in p.relative_to(root).parts[:1]
    )
    unexplained = [f for f in found if f not in ALLOWED_DATA_FILES]
    assert not unexplained, unexplained
    assert not [f for f in ALLOWED_DATA_FILES if f not in found]  # no stale entry
