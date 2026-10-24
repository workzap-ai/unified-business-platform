# Latency notes (delete before final commit)
- Step1 review: diff vs 4263dd4 = latency.py, stage timers, shared customer/noted reads, merged agent+version query, prompt built once. Reviewing/testing now.
- step4: settings_row per-turn cache (configuration.settings_cache_for_turn) + seed_agents select-first: committed, tests in test_pi_latency_profile.py. 629->588 stmts/5 turns. Next: prompt caching check, post-reply work, static caches, full verification
