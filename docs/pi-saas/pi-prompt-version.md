# prompt_version: what it covers and what an edit costs (FT-D3)

`learning_audit.prompt_version()` is the 12-character hash stamped on every reply (`PiReplyAudit.prompt_version`)
and compared by the drift check. It answers one question: which prompt text was in force for this reply.

## What is hashed

| Input | How |
|---|---|
| the specification handbook (`spec/handbook.json`) and what the platform specification replaced (`spec/supersession.json`) | bytes, line endings normalised |
| the **source of every prompt-bearing module** | every `.py` file under `app/modules/pi` (including `tools/`), except `evalkit/` and the modules named on `NON_PROMPT_MODULES`; relative path and bytes, sorted by path; plus prompt modules outside that folder (`EXTERNAL_PROMPT_MODULES`, now `app.ai.media`, whose `IMAGE_INSTRUCTION` reaches the model), found with `importlib.util.find_spec` without importing them |
| every pack file | every `*.json` under `packs/`, relative path and bytes, sorted |
| the operator guidance (optional) | `prompt_version(guidance)` mixes in a hash; the reply stamp keeps the workspace-independent version and records the guidance as `pack_versions.operator_guidance` (12 hex characters, never the words) |

Why source files and not a list of constants: prompts are also inline literals, f-strings and selection
logic (which handbook sections a state or topic selects), and a list can never be complete. A new module
is hashed **by default**; it can leave the hash only by being named on `NON_PROMPT_MODULES` with a reason
(pure table definitions, HTTP handlers, schemas, package markers, this machinery, the drift report, the
timing log). The unit test fails on a stale entry and on an allowlisted module that builds a model message
or calls the model.

## What an edit costs (intended, tolerated)

Any edit to a hashed module's source, **a comment included**, changes `prompt_version`. At the next deploy
the first replies carry the new version; replies stamped with the old one read as stale, and the drift check
reports `stale_prompt` once (`drift_check.stamp_summary`, `drift_check.stamp_findings`) until the new version
is the one being stamped. That finding is expected after any deploy that touches a hashed module and is not
an error. Stored audit rows are never rewritten.

## Reproducibility

The hash uses no clock, host name, working directory, environment variable or absolute path: files are
read by relative path in sorted order, line endings are normalised, and the digest is cached for the life of
the process only when every file could be read. A file that cannot be read is logged once (label only, never
the path or content) and marked in the digest; that result is not cached, so the next call retries.
`test_pi_prompt_version_coverage.py` covers two fresh processes with different `PYTHONHASHSEED` and working
directory and a scrubbed environment.

## Limits

- Behaviour driven by data outside the hashed files is not covered: database settings, learned lessons and
  examples, and the operator guidance except through its own optional hash.
- Only `app/modules/pi` and the listed external modules are hashed; other packages that reach the model are not.
- The per-pack digest stored in audit rows (`pack_versions`) stays a hash of raw bytes, because the drift check
  compares it in that form; only the combined version normalises line endings.
