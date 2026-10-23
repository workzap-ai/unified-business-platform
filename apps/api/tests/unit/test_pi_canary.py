"""Canary rollout decisions (pi Brain spec 9.10 rule 3, eval L9)."""

from datetime import timedelta
from types import SimpleNamespace as Row

from app.modules.pi import learning_canary as canary

SIT = {"state": "S2_CLARIFYING", "language": "en"}


def exp(conv, reward, used=None, signals=()):
    return Row(
        conversation_id=conv,
        reward=reward,
        signals=list(signals),
        example_ids=[used] if used else [],
        situation=SIT,
    )


def window(n_used, n_control, used_reward=2, control_reward=1, bad=0):
    used = [
        exp(f"u{i}", used_reward, "E1", ["confusion"] if i < bad else ()) for i in range(n_used)
    ]
    return used + [exp(f"c{i}", control_reward) for i in range(n_control)]


def judge(rows, days=5):
    return canary.judge("E1", SIT, rows, timedelta(days=days), min_days=3, min_uses=30)[0]


def test_the_same_conversation_is_always_in_or_out():
    assert canary.in_canary("abc", 10) == canary.in_canary("abc", 10)
    assert not canary.in_canary("abc", 0)
    assert canary.in_canary("abc", 100)


def test_about_the_chosen_share_is_in():
    share = sum(canary.in_canary(f"conv-{i}", 10) for i in range(2000)) / 2000
    assert 0.07 < share < 0.13


def test_enough_good_use_promotes():
    assert judge(window(30, 60)) == "promote"


def test_too_few_uses_keep_watching():
    assert judge(window(12, 60)) == "continue"


def test_too_young_keeps_watching():
    assert judge(window(30, 60), days=1) == "continue"


def test_worse_than_control_is_not_promoted():
    assert judge(window(30, 60, used_reward=0, control_reward=2)) == "continue"


def test_rising_confusion_rolls_back_even_on_a_small_sample():
    assert judge(window(8, 60, bad=4)) == "rollback"


def test_one_odd_chat_is_not_enough_to_roll_back():
    assert judge(window(3, 60, bad=2)) == "continue"
