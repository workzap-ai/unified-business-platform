"""The old-opening scan (spec v1.5 18.2) counts hits with the same pattern the live gate uses."""

from app.modules.pi import reply_gates
from app.modules.pi.evalkit import greeting_scan


def test_it_counts_the_old_opening_in_three_languages() -> None:
    texts = [
        ("a", "Hi, I'm pi, an AI from Workzap. What is your business called?"),
        ("b", "Tell me what's going wrong in your business and I'll start on it."),
        ("c", "Aap ke karobar mein kya masla hai?"),
        ("d", "آپ کے کاروبار میں کیا مسئلہ ہے؟"),
        ("e", ""),
    ]
    report = greeting_scan.scan(texts)
    assert report["scanned"] == 5 and report["hits"] == 3
    assert [w for w, _ in report["samples"]] == ["b", "c", "d"]


def test_a_clean_set_reports_zero() -> None:
    report = greeting_scan.scan([("x", "Hi, I'm pi, an AI from Workzap."), ("y", "Thanks.")])
    assert report == {"scanned": 2, "hits": 0, "samples": []}


def test_it_agrees_with_the_live_gate() -> None:
    for text in ("what's going wrong in your business", "Hello there", "main is par kaam shuru"):
        gate = reply_gates.forbidden_opening(text) is not None
        assert (greeting_scan.scan([("t", text)])["hits"] == 1) is gate


def test_the_sample_is_cut_short() -> None:
    long = "x" * 500 + " going wrong in your business " + "y" * 500
    sample = greeting_scan.scan([("l", long)])["samples"][0][1]
    assert len(sample) <= greeting_scan.SAMPLE and "going wrong" in sample
