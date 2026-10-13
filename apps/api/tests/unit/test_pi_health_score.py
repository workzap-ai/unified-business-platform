from app.modules.pi_saas.health import Check, score, verdict
from app.modules.pi_saas.health_selftest import BY_KEY, judge


def _c(status: str) -> Check:
    return Check("k", "WhatsApp", status, "title")  # type: ignore[arg-type]


def test_score_counts_open_problems_and_warnings_only():
    assert score([]) == 100
    assert score([_c("ok"), _c("fixed")]) == 100
    assert score([_c("warning")]) == 93
    assert score([_c("problem"), _c("warning")]) == 73
    assert score([_c("problem")] * 6) == 0
    assert score([{"status": "problem"}, {"status": "ok"}]) == 80


def test_verdict_names_problems_first():
    assert verdict(100, 0).startswith("pi is healthy")
    assert verdict(80, 1) == "pi needs you for 1 thing."
    assert verdict(40, 3) == "pi needs you for 3 things."
    assert "several" in verdict(60, 0)


def test_judge_is_deterministic():
    greeting, price = BY_KEY["greeting"], BY_KEY["price"]
    ok = {"status": "ok", "reply": "Hello, how can we help you today?"}
    assert judge(greeting, ok) == (True, "passed")
    assert judge(greeting, {"status": "ok", "reply": "Hello there!"})[0] is False
    assert judge(greeting, {"status": "ai_unavailable"})[0] is None
    assert judge(greeting, {"status": "blocked", "blocked_reason": "X"})[0] is False
    priced = {"status": "ok", "reply": "A logo costs 25000 rupees.", "price_rule": "quote"}
    assert judge(price, priced)[0] is False
    roman = {"status": "ok", "reply": "Hum aap ki madad kar sakte hain, aap ko kya chahiye?"}
    assert judge(BY_KEY["services_roman_urdu"], roman)[0] is False
    listed = {
        "status": "ok",
        "reply": "We offer:\n• Logo design\n• Websites\nWhich one interests you?",
        "knowledge_used": ["Services"],
    }
    assert judge(BY_KEY["services"], listed) == (True, "passed")
    team = BY_KEY["brief_not_confirmed"]
    assert judge(team, {"status": "ok", "reply": "Yes, we do.", "ready_for_team": True})[0] is False
    assert (
        judge(BY_KEY["brief_confirmed"], {"status": "ok", "reply": "Sent to the team."})[0] is False
    )
    booked = {"status": "ok", "reply": "Your meeting is confirmed for tomorrow."}
    assert judge(BY_KEY["meeting"], booked)[0] is False
