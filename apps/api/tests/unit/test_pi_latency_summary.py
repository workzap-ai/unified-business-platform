"""A turn's timing is kept as plain numbers, so a slow reply can be traced from the database."""

from app.modules.pi import latency


def test_no_turn_no_summary() -> None:
    latency._turn.set(None)
    assert latency.summary() is None


def test_the_summary_holds_every_stage_and_the_counters() -> None:
    latency.begin()
    with latency.stage("debounce"):
        pass
    latency.count("model_calls")
    latency.count("prompt_chars", 1234)
    summary = latency.summary()
    assert summary is not None
    assert set(summary) == {"stages_ms", "wall_ms", "model_calls", "prompt_chars"}
    assert "debounce" in summary["stages_ms"] and summary["model_calls"] == 1
    assert summary["prompt_chars"] == 1234 and summary["wall_ms"] >= 0
    assert all(isinstance(v, int) for v in summary["stages_ms"].values())
    latency._turn.set(None)
