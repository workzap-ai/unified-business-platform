"""Whether an idea survives the reply linter in the shape pi says it: the opener, the idea as a
bullet and the offer, in brain mode. Industry content is data placed below the rules (CLAUDE.md),
so an idea that would be blocked the moment pi says it is not picked: the next idea is served
instead of a blocked reply being rewritten into a fallback. The rules are not touched."""

from functools import lru_cache

from app.modules.pi import constitution
from app.modules.pi.solution_ask import OFFER_AFTER

HISTORY = [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}]
IGNORED = frozenset({"R-DISC-01"})  # the first-message line: the scripted context has history


@lru_cache(maxsize=20000)
def passes(text: str) -> bool:
    reply = f"Here are two ideas you can try now:\n\n• {text}\n\n{OFFER_AFTER['en']}"
    context = {
        "pi_mode": "brain",
        "flow": {"state": "S5_READINESS"},
        "reply_language": "en",
        "history": HISTORY,
        "solution_asked": True,
    }
    return not any(v.hard and v.rule not in IGNORED for v in constitution.lint(reply, context))
