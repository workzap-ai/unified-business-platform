"""The weekly drift monitor (spec 8.9, eval L13)."""

from app.modules.pi import learning_drift as d


def stats(**over):
    base = dict(replies=100, words=18.0, many_questions=0.02, emoji=0.0, english_to_urdu=0.05)
    base.update(over)
    return d.Stats(**base)


def test_no_change_is_no_drift():
    assert d.drift(stats(), stats()) == []


def test_each_kind_of_drift_is_named():
    assert d.drift(stats(), stats(words=26.0)) == ["longer replies"]
    assert "more replies with several questions" in d.drift(stats(), stats(many_questions=0.20))
    assert "more emoji" in d.drift(stats(), stats(emoji=0.15))
    assert "more English for people who write Roman Urdu" in d.drift(
        stats(), stats(english_to_urdu=0.30)
    )


def test_too_few_replies_means_no_verdict():
    assert d.drift(stats(replies=10), stats(words=40.0)) == []
    assert d.drift(stats(), stats(replies=10, words=40.0)) == []


def test_stats_count_questions_emoji_and_language():
    rows = [
        ("Which shop? And how often?", "en"),
        ("Noted. Which items run out first?", "en"),
        ("Shukriya \U0001f44d", "roman_ur"),
        ("Thanks, noted. Which shop is it", "roman_ur"),
    ]
    s = d.stats(rows)
    assert s.replies == 4 and s.many_questions == 0.25 and s.emoji == 0.25
    assert s.english_to_urdu >= 0.0
