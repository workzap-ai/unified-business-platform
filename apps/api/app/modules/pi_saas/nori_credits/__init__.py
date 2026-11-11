"""pi's side of the nori credits bridge (docs/pi-saas/nori-bridge.md).

Nothing here runs unless the server has NORI_BASE_URL and WORKZAP_BRIDGE_SECRET and a workspace
has `response_rules.nori_bridge.enabled` set to exactly true. With either missing, every entry
point returns before it does any work (no database read, no HTTP call), so pi behaves as it did
before this package existed.

Modules: config (the two gates and the tunables), signing, resilience (circuit breaker, counters,
redaction, small caches), client (signed calls to nori), store (idempotency, replay, audit, rate
limit rows), hook (the inbound pre-hook), send_door (nori to pi), routes (the HTTP door),
capture (requirements and problems for the Workzap team).
"""
