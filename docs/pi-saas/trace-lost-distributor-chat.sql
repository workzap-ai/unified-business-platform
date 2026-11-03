-- READ-ONLY trace of the chat of 2026-10-27 17:03-17:14 PKT (12:03-12:14 UTC) with +923112546598
-- ("SAW"), to find why pi asked the same question twice (turns 15 and 17: "Is mein sab se zyada
-- nuqsan kis baat ka ho raha hai?"). Paste into the Neon SQL editor yourself and send the results
-- (or a screenshot) back. Only SELECT statements: nothing here changes data. Claude Code does not
-- read the real database.

-- 1. The conversation and what pi remembered (expert_diag, closed slots, last question, language).
SELECT c.id AS conversation_id, c.flow_state, c.language, c.mode,
       c.service_brief->'expert_diag'      AS expert_diag,
       c.service_brief->'closed_slots'     AS closed_slots,
       c.service_brief->'last_question'    AS last_question,
       c.service_brief->'owner_language'   AS owner_language,
       c.service_brief->'ideas_given'      AS ideas_given
FROM pi_conversations c
WHERE c.contact_wa_id LIKE '%3112546598'
ORDER BY c.last_message_at DESC
LIMIT 1;

-- 2. The messages of that chat, in order, with the run that produced each pi reply.
SELECT m.created_at, m.direction, m.sender_type, m.body, r.id AS run_id
FROM pi_messages m
JOIN pi_conversations c ON c.id = m.conversation_id
LEFT JOIN pi_agent_runs r ON r.response_message_id = m.id
WHERE c.contact_wa_id LIKE '%3112546598'
  AND m.created_at BETWEEN '2026-10-27 12:00:00+00' AND '2026-10-27 12:20:00+00'
ORDER BY m.created_at;

-- 3. What the reply linter found on each pi reply (the rules that fired, the rewrite, any fallback).
SELECT m.created_at, left(m.body, 80) AS reply, a.linter
FROM pi_reply_audits a
JOIN pi_messages m ON m.id = a.message_id
JOIN pi_conversations c ON c.id = m.conversation_id
WHERE c.contact_wa_id LIKE '%3112546598'
  AND m.created_at BETWEEN '2026-10-27 12:00:00+00' AND '2026-10-27 12:20:00+00'
ORDER BY m.created_at;

-- 4. How each run went: which model answered, whether the fallback model was used, errors.
SELECT r.created_at, r.status, r.provider, r.model, r.fallback_used, r.outcome, r.error_code,
       r.latency_ms
FROM pi_agent_runs r
JOIN pi_conversations c ON c.id = r.conversation_id
WHERE c.contact_wa_id LIKE '%3112546598'
  AND r.created_at BETWEEN '2026-10-27 12:00:00+00' AND '2026-10-27 12:20:00+00'
ORDER BY r.created_at;
