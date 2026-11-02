"""Digital solution exploration uses the existing reply, memory and safety pipeline.

Intent recognition is shared with solution_ask and its multilingual model fallback. This
module adds workflow/implementation language, not industry-to-product mappings.
"""

import re
from typing import Any

WORKFLOW = re.compile(
    r"\bhow (?:would|will|can|could|do) you (?:practically )?(?:solve|fix|handle|address)\b"
    r"|\b(?:practical|digital|modern) (?:solution|workflow|system|approach)s?\b"
    r"|\b(?:what|which) (?:actual )?(?:system|software|app) "
    r"(?:would|will|can|could) you (?:build|develop)\b"
    r"|\bi (?:want|need) (?:a |some )?(?:software|system|app) (?:for|to)\b"
    r"|\bhow (?:would|will|do|can) (?:my|our|the) (?:staff|workers|employees|team) use\b"
    r"|\b(?:can|could|would) you (?:automate|develop|build)\b"
    r"|\b(?:actual system|system would look like|use it daily)\b"
    r"|\b(?:ap|aap)\s+(?:kia|kya)\s+(?:kar|kr|karay|karein|karen|bana|bna)\w*\b"
    r"|\b(?:cheez|system|software) (?:bana|bna) (?:sakte|sakty|skty)\b",
    re.I,
)
DATA_ENTRY = re.compile(
    r"\b(?:data entry|data migration|initial (?:data|stock)|opening stock)\b"
    r"|ڈیٹا (?:انٹری|منتقلی)|إدخال البيانات|ادخال البيانات",
    re.I,
)
REFUSAL = re.compile(
    r"\b(?:we|our company) (?:sell|provide|offer) (?:practical|digital) solutions?\b"
    r"|\b(?:do not|don't|no|not looking for|don't want) (?:want |need |a |any )*"
    r"(?:practical|digital) (?:solution|system|workflow)",
    re.I,
)
MANUAL_ONLY = re.compile(
    r"\b(?:no software|without software|manual (?:ideas|solution|options) only)\b", re.I
)


def explicit(said: str) -> bool:
    return bool(WORKFLOW.search(said or "")) and not REFUSAL.search(said or "")


def implementation_asked(said: str) -> bool:
    return bool(DATA_ENTRY.search(said or "")) and bool(
        re.search(
            r"[?؟]|\b(?:will|who|would|how|aap|ap|khud|kaise|kon|kaun)\b|کون|کیا|هل|من سي",
            said,
            re.I,
        )
    )


def requested(said: str) -> bool:
    from app.modules.pi import owner_asks, solution_ask

    if REFUSAL.search(said or "") or MANUAL_ONLY.search(said or ""):
        return False
    return bool(
        explicit(said)
        or implementation_asked(said)
        or solution_ask.asked_for_ideas(said)
        or owner_asks.asks_for_plan(said)
    )


def eligible(context: dict[str, Any]) -> bool:
    from app.modules.pi import decisions, solution_ask

    said = str(context.get("latest_customer_message") or "")
    if context.get("pi_mode") != "brain" or context.get("operator_review_required"):
        return False
    if (context.get("flow") or {}).get("state") not in solution_ask.ASKABLE:
        return False
    # A quote request still goes through the real offer/approval gate. Expense descriptions
    # and implementation questions are not purchase approval.
    if decisions.asks_for_document(said) or decisions.cost_asked(said):
        return False
    if REFUSAL.search(said) or MANUAL_ONLY.search(said):
        return False
    known = bool(
        context.get("noted_problems")
        or context.get("business_profile")
        or context.get("profile_grounding")
        or len(said.split()) >= 18
    )
    brief = context.get("brief") or {}
    answering_workflow = (
        brief.get("conversation_stage") == "solution_exploration"
        and bool(brief.get("solution_question_pending"))
        and not context.get("topic_event")
        and 0 < len(said.split()) <= 12
        and not re.search(r"[?؟？]", said)
        and not map_incomplete(said)
    )
    return known and (requested(said) or bool(context.get("plan_asked")) or answering_workflow)


PROMPT = """
The customer is exploring a business solution, not authorising a purchase or implementation.
Use the latest customer message, complete noted_problems, problem_relationships, requirements,
known business profile, approved_knowledge, industry context and history. Customer corrections
win over older notes. Distinguish confirmed facts, hypotheses, unknowns and proposed features.
Never revive a rejected relationship or claim unknown constraints have been checked.

Answer their actual question first in reply_language (and reply_language_other/script when set).
For a solution request, reason from their business and desired outcome to the smallest suitable
DIGITAL system. Explain what the owner, staff and other relevant users would do each day,
how information moves, and how each proposed capability addresses a stated problem. Consider
relevant records, roles, modules, mobile/web interfaces, reporting, alerts and integrations.
Only include what fits; neither AI nor a large ERP is mandatory. Use domain knowledge for
unfamiliar industries too, with assumptions labelled. Do not default to manual boards, meetings,
registers or spreadsheets in place of requested software. Existing libraries are examples,
not a limit on what can be proposed. Explain ordinary terms instead of dumping feature names.
Unknown headcounts or budgets need not block a provisional design; label sizing as still open.
Respect any known budget, staff, privacy, timing and other constraints.

For an implementation question, answer that question directly rather than repeating the full
solution. Initial data entry/migration and ongoing entry are separate tasks. Workzap's actual
responsibility, availability, scope and cost require team confirmation unless approved context
already supplies them. Never promise that Workzap will enter all data. Mention an import option
only when approved technical context supports it; otherwise say it needs checking.
Organising operational, expense or inspection records is possible to discuss, but never invent
legal/tax rules, guarantee compliance, or offer treatment/medical advice. State the limited
professional verification needed without abandoning the operational solution.

Use roughly 100-200 words for a workflow, fewer for a focused implementation answer. Ask at most
one useful UNANSWERED workflow question, last, only if it materially improves the design. If
no_questions is true, ask none. Do not restart discovery, ask for already-known facts, force a
choice of problems, or replace the answer with a document offer. Never repeat previous replies.
The proposal is conditional: nothing has been built, started, sent or approved by this conversation.
Do not invent pricing, deadlines, guaranteed results, company capabilities or supported imports.
Do not change consent, create an action, book a meeting or approve a quote. Keep action none,
ready_for_team false and proposal_answer none. Record new CUSTOMER problems/corrections using
problem_ops and existing refs; proposed features are not customer problems.
"""


def answer_problem(reply: str, context: dict[str, Any]) -> str | None:
    if not context.get("solution_exploration"):
        return None
    # Script-independent: do not require a minimum number of whitespace-separated words.
    text = reply.strip()
    if len(text) < 80 and not implementation_asked(
        str(context.get("latest_customer_message") or "")
    ):
        return "answer the solution request with a grounded digital workflow, not only a question"
    if len(text.split()) > 240:
        return "keep the practical explanation concise (under 240 words)"
    questions = sum(text.count(mark) for mark in ("?", "؟", "？"))
    if questions > (0 if context.get("no_questions") else 1):
        return "ask at most one useful unanswered question, none when no_questions is true"
    if questions and not text.endswith(("?", "؟", "？")):
        return "put the single workflow question last"
    return None


def map_incomplete(said: str) -> bool:
    return " ".join((said or "").casefold().strip(" .!?؟").split()) in {
        "kuch reh gaya",
        "something is missing",
        "something missing",
        "something was missed",
        "کچھ رہ گیا",
        "شيء ناقص",
        "هناك شيء ناقص",
    }
