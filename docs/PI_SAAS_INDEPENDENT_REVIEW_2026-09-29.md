# Pi SaaS independent review — 29 September 2026

## Verdict

The implementation is moving in the agreed architectural direction, but it is not ready for acceptance or unattended customer use. Three behavioral defects were reproduced, and the standalone UI/tool implementation is still in progress.

Another process continued changing source files during this review. To avoid mixed test results and editing conflicts, backend verification used an isolated source snapshot captured at **12:12:04 Asia/Karachi** and a dedicated local test database, `pi_independent_review_20260929_test`. Later source inspections are explicitly distinguished from that snapshot. No active application code was patched by this review.

This is an interim review, not a claim that the other implementation process has finished.

## Verified results

| Check | Result | Evidence |
| --- | --- | --- |
| Migrations through 0007 on a fresh review database | Passed | `migrate.log` |
| Existing backend unit suite on the snapshot | 273 passed, 3 failed | `unit-baseline.log` |
| Selected existing Pi integration suite | 42 passed | `pi-integration.log` |
| Independent behavioral/API probes | 5 passed, 7 failed | `independent-probes.log` |

The seven independent failures represent three defects, not seven separate defects. The initial working-tree run had two additional transient scheduler failures while source files were being added; those did not recur in the stable snapshot and are not presented as persistent findings.

The five independent API checks that passed were:
- Pi registration, account retrieval, and Home endpoint.
- Pi session cookie cannot access the Owner OS session endpoint.
- A second owner cannot select the first owner's business.
- A viewer can read account details but cannot pause Pi.
- Pi mutations reject requests without the required CSRF token.

These establish useful basic controls. They do not prove every tool, field, customer, role, summary, or worker is isolated.

Existing Pi integration checks covered the new inbox/history/publication regressions plus selected tools, service conversations, and runtime behavior. Real external AI and WhatsApp delivery were mocked.

## P1 — No-price service policy still allows written amounts

**Files:** `apps/api/app/modules/pi/price_policy.py`, `service_conversation.py`.

Reproductions:
- `validate_service_reply("The fee is thirteen.", 4000, "hidden")` returns the reply.
- `validate_service_reply("The website costs fourteen.", 4000, "hidden")` returns the reply.
- `validate_service_reply("The price is sixteen.", 4000, "hidden")` returns the reply.

The lexicon omits these number words. More importantly, the implementation still relies on an enumerated lexical filter for this decision.

Two database-backed pipeline probes injected the first two replies into the service-business model result and then ran delivery. Each reached the **mocked WhatsApp sender** once despite the service default prohibiting prices.

This demonstrates a guard failure if a model produces such text; it does not claim a live model actually quoted those prices.

**Required correction:** enforce approved pricing sources and no-price policy throughout retrieval, tool output, reply generation, attachment generation, and final send. Keep lexical detection as defense in depth rather than the sole guarantee. Preserve legitimate collection of customer budgets/dates. Add these pipeline regressions and broader multilingual/implicit-amount cases; route unresolved policy ambiguity to a person.

## P1 — Price evidence accepts a different amount as a substring

**File:** `apps/api/app/modules/pi/guard.py:146`.

Reproduction:
```python
validate_reply("The router is Rs 50", ['{"price": "150.00"}'], 4000)
```

The reply passes because `50` is a substring of `150.00`.

**Impact:** Pi can present an incorrect amount while the guard considers it supported by a tool result.

**Required correction:** parse and compare canonical Decimal monetary values from structured approved fields. Bind the value to the relevant item/currency/context; do not search arbitrary serialized evidence strings. Add amount-boundary, currency, grouping, quantity-versus-price, and multi-item regression cases.

## P2 — Invalid onboarding input returns HTTP 500

**File:** `apps/api/app/modules/pi_saas/app_routes.py`, `save_step`.

An authenticated Pi owner sends:
```http
PUT /api/v1/pi-app/account/onboarding/1
{"name": ""}
```

Observed: HTTP 500 `INTERNAL_ERROR`.
Expected: HTTP 422 with a safe field-level validation error.

The route manually calls `model.model_validate(await request.json())`, but the resulting Pydantic error is not converted into the request-validation exception handled by the application.

**Required correction:** use typed request validation or deliberately translate manual validation/JSON errors into the established safe 4xx envelope. Keep valid authorization failures distinct. Test empty names, malformed JSON, invalid timezones, invalid offering amounts, and unknown steps. UI must preserve the user's input and focus the relevant field.

## P2 — Production configuration compatibility and tests need updating

**File:** `apps/api/app/core/config.py:158,229`.

The new Pi origins default to HTTP localhost, while production validation unconditionally requires HTTPS. Two existing production-settings tests now fail with `Production Pi app origins require HTTPS`.

**Required correction:** explicitly define the deployment contract for Owner OS-only versus Pi-enabled deployments. Supply/document required Pi production origins and URL, update valid production test fixtures, and/or gate optional Pi configuration appropriately. Do not weaken HTTPS checks for an enabled production Pi app.

Failing tests:
- `test_database_neon.py::test_production_rejects_remote_database_without_ssl`
- `test_integrations_http.py::test_production_requires_encryption_key_when_integrations_enabled`

## P2 — Generated frontend permissions are stale

The updated backend access registry adds permissions including `pi.inbox.all`, while the frontend generated access snapshot is unchanged.

Failing test:
`test_navigation.py::test_frontend_snapshots_are_in_sync_with_the_registry`.

**Required correction:** regenerate through the repository's navigation/access export command, review the resulting diff, and rerun the synchronization check and affected permission UI tests.

The isolated review initially omitted this frontend fixture; that harness omission was corrected before the reported baseline result. The final reported failure is the actual content mismatch, not a missing-file error.

## Requirement gaps: work still being implemented

These are observed incomplete areas, not claims about the eventual finished implementation:

- `apps/pi` appeared during the review. At the UI checkpoint, landing, sign-in, and sign-up pages existed; full onboarding, authenticated inbox, tools, billing, responsive journeys, and browser acceptance had not been verified.
- The live tool catalog still contained 18 registered tools at the tool checkpoint. Onboarding declared the following names that were absent from that registry:
  - Bookings: `check_availability`, `create_booking`, `cancel_booking`, `get_bookings`.
  - Tasks: `create_task`, `get_project_status`.
  - Tickets: `create_ticket`.
  - Payments: `create_payment_link`, `get_payment_status`.
- Configuration choices or model tables alone do not establish an executable tool integration.
- Full own/assigned/other-creator record permissions, custom roles, restricted fields, provider reconnect, subscription lifecycle, all tool approvals, complete media behavior, reminders, and operator summaries still need dedicated acceptance coverage.
- No live Kapso/Meta onboarding, number purchase, actual outbound customer message, payment charge, or model/media-quality check was performed.
- Redis/ARQ deployment behavior and browser UX are not certified by these inline-worker/API tests.

The price-policy, amount-guard, production-config, and tool-catalog files matched the captured snapshot when rechecked at approximately 12:22. The implementation is continuing; recheck current source before applying fixes.

## Artifacts and reproduction

Artifacts are in:
`.cache/pi-independent-review-20260929/`

- `snapshot-manifest.json`: captured time and source hashes.
- `snapshot/`: independent backend source and test fixtures.
- `unit-baseline.log`, `pi-integration.log`, `independent-probes.log`.
- `snapshot/apps/api/tests/unit/test_independent_price_review.py`.
- `snapshot/apps/api/tests/integration/test_independent_pi_saas_review.py`.
- `review.py`: safe local review harness.

From the repository root:
```powershell
.venv\Scripts\python.exe .cache/pi-independent-review-20260929/review.py probes
.venv\Scripts\python.exe .cache/pi-independent-review-20260929/review.py baseline-recheck
```

These commands exercise the saved snapshot, not future edits to the live tree. Port the relevant regression tests into the active test suite and rerun there after fixes. The harness uses only local test-cluster configuration and does not load the live application .env.

## Handoff to the implementing agent

1. Reproduce the three behavioral defects against current source.
2. Add the independent regressions to the active suite and fix the underlying behavior.
3. Resolve production configuration and generated-permission consistency.
4. Finish and register all promised tools, with honest disconnected/credential-blocked states.
5. Complete the standalone customer UI and demonstrate mobile/desktop browser journeys.
6. Verify advanced role/record/customer boundaries and real configured integrations.
7. Update the requirement matrix and report implemented, tested, blocked, and remaining scope accurately.

The existing shared-backend reuse, audience-separated sessions, basic access controls, and honest provider-state approach are appropriate foundations. They are not sufficient on their own to approve the complete product.

