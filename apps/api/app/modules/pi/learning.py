# ruff: noqa: E501  (long regexes read better on one line)
"""The self-learning brain's safe core (pi Brain spec Part 8, 9.10, 11.9).

Pure functions, no database and no model. They decide four things:

* what happened after pi spoke (`signals_after`) and the reward for it (`reward`, spec 8.3). Offers
  accepted, quotes approved and payments are never rewards: if pi were paid for sales it would
  learn to sell and quietly break R-SELL. pi is rewarded for understanding the person with little
  friction.
* what may never be learned (`never_learn`, spec 8.9) and how risky a proposed lesson is
  (`risk`, spec 8.7; anything unsure is HIGH).
* which of several candidate questions to try (`choose_arm`, `update_arm`: Thompson sampling).
* when to stop everything (`frozen`) and when pi's style has drifted (`drifted`).

Nothing here changes pi's behaviour by itself. Learned text is data placed below the constitution;
the constitution (constitution.py) never learns.
"""

import random
import re
from dataclasses import dataclass
from typing import Any

from app.modules.pi import constitution, safety, style

# --- what happened after pi spoke (spec 8.3) ----------------------------------------------------

REWARDS: dict[str, int] = {
    "rich_reply": 2,
    "confirmed_first_time": 2,
    "self_continued": 1,
    "thanked": 1,
    "returned_and_continued": 1,
    "short_neutral": 0,
    "correction": -2,
    "confusion": -2,
    "repeat_question": -3,
    "drop_off": -1,
    "frustration": -2,
    "asked_human_because_of_pi": -2,
    "opt_out": -5,
    "complaint": -5,
}
# Deliberately absent, whatever a caller passes: the business outcome is reported, never rewarded.
NEVER_REWARDED = frozenset(
    {"offer_accepted", "approved", "paid", "payment", "quote_approved", "yes"}
)

THANKS = re.compile(
    r"\b(?:thanks|thank you|thx|shukriya|shukria|jazak|mashkoor)\b|👍|🙏|❤|شكرا|شکریہ",
    re.IGNORECASE,
)
CORRECTION = re.compile(
    r"^\W*(?:no[, ]|nahi|nahin|galat|wrong|that'?s not|its not|it'?s not|not what i)"
    r"|\b(?:not what i meant|galat likha|actually it'?s|actually its|you got it wrong|that is wrong)\b",
    re.IGNORECASE,
)
FRUSTRATION = re.compile(
    r"\b(?:useless|stupid|waste of time|you (?:don'?t|dont) listen|already told you|i said this|"
    r"bekar|faltu|pehle bata chuka|kitni baar)\b|😡|🤬",
    re.IGNORECASE,
)
COMPLAINT = re.compile(
    r"\b(?:i (?:want to )?complain|complaint (?:about|against) (?:pi|this bot)|report (?:you|this bot))\b",
    re.IGNORECASE,
)
ASKS_HUMAN = re.compile(
    r"\b(?:talk to (?:a )?(?:human|person|real person|someone)|speak to (?:a )?(?:human|person)|"
    r"insaan se baat|human chahiye)\b",
    re.IGNORECASE,
)
OPT_OUT = re.compile(
    r"^\W*(?:stop|unsubscribe|opt[\s-]?out|band\s*karo|band\s*kar\s*do|don'?t message me|"
    r"stop messaging me)\W*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Next:
    """What the person did after pi's message (all the pipeline needs to score it)."""

    reply: str | None  # their next message, None when nothing came
    hours_waited: float = 0.0
    pi_asked_a_question: bool = False
    noted_confirmed: bool = False  # a noted line they saw and did not object to
    new_problem: bool = False  # a problem they raised without being asked
    gap_days: float = 0.0  # since their previous message, when this one is a return
    already_known: bool = False  # pi asked something memory already answered


def _words(text: str) -> int:
    return len(text.split())


def signals_after(after: Next) -> list[str]:
    """The outcome signals for one pi message, from what followed it."""
    found: list[str] = []
    said = " ".join((after.reply or "").split())
    if after.already_known:
        found.append("repeat_question")
    if not said:
        if after.pi_asked_a_question and after.hours_waited >= 24:
            found.append("drop_off")
        return found
    if OPT_OUT.search(said):
        return [*found, "opt_out"]
    if COMPLAINT.search(said):
        found.append("complaint")
    if ASKS_HUMAN.search(said) and FRUSTRATION.search(said):
        found.append("asked_human_because_of_pi")  # a plain request for a person is not a fault
    if style.confused(said):
        found.append("confusion")
    if CORRECTION.search(said):
        found.append("correction")
    if FRUSTRATION.search(said):
        found.append("frustration")
    if found:
        return found
    if THANKS.search(said):
        found.append("thanked")
    if after.new_problem:
        found.append("self_continued")
    if after.noted_confirmed:
        found.append("confirmed_first_time")
    if after.gap_days >= 1:
        found.append("returned_and_continued")
    if after.pi_asked_a_question and _words(said) >= 8 and not found:
        found.append("rich_reply")
    return found or ["short_neutral"]


def reward(signals: list[str]) -> int:
    """The reward for one pi message. Sales outcomes never count (spec 8.3, eval L5)."""
    return sum(REWARDS.get(s, 0) for s in signals if s not in NEVER_REWARDED)


# --- what may never be learned, and how risky a lesson is (spec 8.7, 8.9) ------------------------

MONEY_OR_RULE_TOPICS = re.compile(
    r"\b(?:pay(?:ment|ing|s)?|price[sd]?|pricing|cost[s]?|quote[sd]?|invoice|bank|iban|account number|"
    r"refund|discount|offer|approv\w*|follow[- ]?up|remind\w*|privacy|personal data|passwords?|otp|pin|"
    r"cnic|passport|legal|lawyer|law|tax|medical|doctor|medicine|diagnos\w*|loan|invest\w*|"
    r"emergency|fire|police|ambulance|disclos\w*|ai\b|human|stop|opt[- ]?out|unsubscribe|"
    r"guarantee|promise|solution|document|proposal|workzap will|we will build)\b",
    re.IGNORECASE,
)
PERSON_OR_COMPETITOR = re.compile(
    r"\b(?:mr|mrs|ms|dr|haji|sheikh|sir)\.? [A-Z][a-z]+|\b(?:competitor|zoho|odoo|quickbooks|"
    r"vyapar|busy|marg|sap)\b",
    re.IGNORECASE,
)
SOCIAL_PROOF = re.compile(
    r"\b(?:other (?:businesses|shops|owners|clients)|most (?:owners|businesses|shops)|"
    r"hundreds of|thousands of|everyone is|trusted by|many (?:businesses|clients))\b",
    re.IGNORECASE,
)
INJECTION = re.compile(
    r"\b(?:ignore (?:all |the |your )?(?:previous|above|prior|rules|instructions)|disregard (?:the )?(?:rules|instructions)|"
    r"you are now|system prompt|new instructions?:|override)\b",
    re.IGNORECASE,
)
# A neutral listening-state context so the reply linter can judge a piece of learned text.
LISTENING = {
    "pi_mode": "brain",
    "strict_voice": True,
    "flow": {"state": "S2_CLARIFYING"},
    "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
}


def never_learn(text: str) -> list[str]:
    """Why a piece of text (an example, a question, a lesson) must never be learned. Empty when it
    breaks none of the never-learn rules. The reply linter does most of the work, so the checks
    that decide pi's replies and the checks that decide what pi may learn cannot disagree."""
    said = " ".join((text or "").split())
    why: list[str] = []
    if not said:
        return ["empty"]
    if said.count("?") > 1:
        why.append("more than one question (R-ASK-01)")
    for violation in constitution.hard(constitution.lint(said, dict(LISTENING))):
        why.append(f"{violation.rule}: {violation.message}")
    if safety.advice_asked(said) is not None or safety.boundary_asked(said) is not None:
        why.append("legal, medical, financial or boundary content")
    if PERSON_OR_COMPETITOR.search(said):
        why.append("names a person or a competitor")
    if SOCIAL_PROOF.search(said):
        why.append("social proof (R-SELL-03)")
    if INJECTION.search(said):
        why.append("tries to give pi instructions")
    if safety.redact_pii(said).kinds:
        why.append("contains personal data (R-PRIV-07)")
    return why


def risk(text: str) -> str:
    """LOW or HIGH for a proposed lesson (spec 8.7). Conservative: anything unsure is HIGH."""
    said = " ".join((text or "").split())
    if not said or len(said) > 400:
        return "HIGH"
    if never_learn(said) or MONEY_OR_RULE_TOPICS.search(said):
        return "HIGH"
    return "LOW"


# --- which question to try (spec 8.4.5, 8.5 job 3) ---------------------------------------------


@dataclass
class Arm:
    text: str
    alpha: float = 1.0  # successes + 1
    beta: float = 1.0  # failures + 1
    uses: int = 0
    traffic_cap: float = 1.0  # a new arm is capped (10%) until it has 50 uses


def choose_arm(arms: list[Arm], rng: random.Random | None = None) -> Arm:
    """Thompson sampling: draw once from each arm's Beta posterior and take the best draw."""
    if not arms:
        raise ValueError("no arms to choose from")
    rng = rng or random.Random()
    mature = [a for a in arms if a.traffic_cap >= 1.0]
    draw = {id(a): rng.betavariate(a.alpha, a.beta) for a in arms}
    best = max(arms, key=lambda a: draw[id(a)])
    if best.traffic_cap < 1.0 and mature and rng.random() > best.traffic_cap:
        return max(mature, key=lambda a: draw[id(a)])
    return best


def update_arm(arm: Arm, useful_without_confusion: bool) -> None:
    arm.uses += 1
    if useful_without_confusion:
        arm.alpha += 1
    else:
        arm.beta += 1
    if arm.traffic_cap < 1.0 and arm.uses >= 50:
        arm.traffic_cap = 1.0


def arm_should_retire(arm: Arm, best: Arm) -> bool:
    """A clearly worse posterior after 200 uses (spec 8.5 job 3)."""
    if arm.uses < 200:
        return False
    mean = arm.alpha / (arm.alpha + arm.beta)
    top = best.alpha / (best.alpha + best.beta)
    return top - mean >= 0.1


# --- the kill switch and the drift monitor (spec 8.9) --------------------------------------------


def frozen(response_rules: dict[str, Any] | None) -> bool:
    """`response_rules.brain.learning_frozen` stops every automatic change (eval L10). Learning is
    frozen unless a workspace sets it to exactly False: it is opt-in, and a typo must fail safe."""
    flag = ((response_rules or {}).get("brain") or {}).get("learning_frozen")
    return flag is not False


def drifted(reply_words: list[int], reference_words: list[int], limit: float = 0.30) -> bool:
    """Replies are longer than the frozen reference by more than `limit` (eval L13)."""
    if not reply_words or not reference_words:
        return False
    now = sum(reply_words) / len(reply_words)
    then = sum(reference_words) / len(reference_words)
    return then > 0 and (now - then) / then > limit
