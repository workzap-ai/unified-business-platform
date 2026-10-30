# prompt_version: what it covers and what an edit costs (FT-D3)

`learning_audit.prompt_version()` is the 12-character hash stamped on every reply (`PiReplyAudit.prompt_version`)
and compared by the drift check. It answers one question: which prompt text was in force for this reply.

## What is hashed

| Input | How |
|---|---|
| the specification handbook (`spec/handbook.json`) and what the platform specification replaced (`spec/supersession.json`) | bytes, line endings normalised; read once per process and cleared with the rest of the cache |
| the **source of every prompt-bearing module** | every `.py` file under `app/modules/pi` (including `tools/`, and `learning_audit.py` itself), except `evalkit/` and the modules named on `NON_PROMPT_MODULES`; relative path and bytes, sorted by path |
| prompt modules outside that folder (`EXTERNAL_PROMPT_MODULES`) | `app.ai.media` (its `IMAGE_INSTRUCTION` reaches the model) and `app.modules.pi_saas.proposal_writer` (its system prompt shapes customer-facing pi output), found with `importlib.util.find_spec` without importing them |
| every pack file | every `*.json` under `packs/`, relative path and bytes, sorted |
| the operator guidance (optional) | `prompt_version(guidance)` mixes in a hash; the reply stamp keeps the workspace-independent version and records the guidance as `pack_versions.operator_guidance` (12 hex characters, never the words) |

Why source files and not a list of constants: prompts are also inline literals, f-strings and selection
logic (which handbook sections a state or topic selects), and a list can never be complete. A new module
is hashed **by default**; it can leave the hash only by being named on `NON_PROMPT_MODULES` with a reason.

## The allowlist is checked by AST, not by a text search

Every allowlisted module must pass an AST check in `test_pi_prompt_version_coverage.py`:

- no import from `app.ai` in any form: `import app.ai...`, `from app.ai... import`, `from app import ai`, a
  relative import of `ai`, `app.ai.<x>` attribute use, or a string naming `app.ai` (a dynamic import);
- no reference to `Message`, `LLMManager`, `build_llm_manager`, `Gateway` or `route_message` (aliased or not);
- no call to `.system`, `.complete`, `.chat`, `.structured`, `.stream`, `.generate`, `.generate_structured`,
  `.complete_with_images`, `.run`, `.invoke`, `.ask`, `.respond` or `.embed`;
- no string or f-string text over 80 characters anywhere (functions, classes and returns included; docstrings
  excluded; one named exception: `drift_check._LISTEN_ONLY`, a detector regex).

Running the guard on the real allowlist moved two more modules into the hash: `routes.py` (it calls
`request.stream()`, an HTTP body read, which the new `.stream` rule flags) and `brain_erase_routes.py` (a long
text). Earlier rounds moved `brain_doc_routes.py`, `config_routes.py`, `brain_visual_routes.py`, `read_routes.py`
and `learning_audit.py`. An empty or stale allowlist entry fails the test.

**The guard is direct-only.** It sees an import, a reference, a call or a long text written in that module's own
source. A model reached through an object passed in as an argument, through another module's helper, or through a
name built at run time is not seen. A second test fails when a prompt-like data file (`.txt`, `.md`, `.jinja`,
`.j2`, `.yaml`, `.yml`, `.tmpl`, `.prompt`) appears under `app/modules/pi`, because only `.py` sources, the pack
JSON and the handbook JSON are hashed (the one existing file is the font licence `fonts/OFL.txt`).

## What an edit costs (intended, tolerated, and not once-only)

Any edit to a hashed module's source, **a comment included**, changes `prompt_version`. The drift check then
reports **two** findings:

1. `prompt_version` (`drift_check.py`, the versions loop near line 405): the version differs from the
   previous run's baseline. It appears on the first run after the change.
2. `stale_prompt` (`drift_check.stamp_findings`, near line 440): none of the last replies carries the version on
   disk now. It fires on **every** drift run until a reply is stamped with the new version, so a quiet workspace
   keeps it until its next reply.

Nearly every release that touches a hashed module triggers both. This is understood and accepted for now; it is
not an error. Stored audit rows are never rewritten.

### Proposed mitigations (PROPOSALS only; `drift_check.py` is not changed in this commit)

1. In `stamp_summary`, count a stamp as stale only when its `pack_versions.build` equals the current
   `build_id()` (same build, different prompt), and treat a different build as "deploy in progress".
2. Hash comment-stripped source (using `tokenize`), so a comment-only edit does not change the version.

## An incomplete digest is marked, not constant

If a file cannot be read, or the source set is too small to be real (fewer than `MIN_HASHED_MODULES` = 100
modules, or `service_conversation.py` / `runtime.py` missing: an empty or frozen folder; or the packs folder is
empty, missing or holds no `industry/*.json` pack, `MIN_PACK_FILES` = 1), the version starts with
`!` (for example `!3fa91c0b27d`), a warning is logged once (a count or a label, never a path or content), and the
result is not cached, so the next call retries.

## Reproducibility

The hash uses no clock, host name, working directory, environment variable or absolute path: files are read by
relative path in sorted order and line endings are normalised. `test_pi_prompt_version_coverage.py` covers two
fresh processes with different `PYTHONHASHSEED` and working directory and a scrubbed environment.

## Modules deliberately NOT hashed (accepted)

These modules reach a model but do not shape WhatsApp pi replies; they are accepted as outside the version. They
can be added to `EXTERNAL_PROMPT_MODULES` if the owner judges them in scope.

| Module | Why it is accepted as not hashed |
|---|---|
| `pi_saas/assistant.py` | the in-app assistant (setup help for staff), not a customer reply |
| `pi_saas/teach.py`, `pi_saas/website_kb.py` | knowledge drafts and website crawling; they write drafts that a person publishes, not replies |
| `pi_saas/agenta.py` | the operator console agent |
| `pi_customer/service.py` | the pi Customer portal, not the WhatsApp reply path |
| `workspace_agent/*` | the Owner OS workspace agent (a different product surface) |

## Limits

- Behaviour driven by data outside the hashed files is not covered: database settings, learned lessons and
  examples, and the operator guidance except through its own optional hash.
- Only `app/modules/pi` and the listed external modules are hashed; other packages that reach the model are not.
- The per-pack digest stored in audit rows (`pack_versions`) stays a hash of raw bytes, because the drift check
  compares it in that form; only the combined version normalises line endings.
- The number of hashed files and the first-call time are printed by `test_report_the_hashed_file_count_and_the_first_call_time`
  (not asserted); the digest is cached per process afterwards.
- Known guard gaps (re-audit advisories, not fixed): a prompt split into many short literals passes the long-text rule;
  `import app as a; a.ai.x` and a bare-name call such as `run(m)` are not flagged; `MIN_PACK_FILES` is 1 against 211
  packs; the data-file test lists only the extensions named above; `stamp_safely` still logs a traceback.
