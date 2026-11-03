"""The openingGate log (spec v1.5, 18.2): result, path and prompt version, never the text."""

import logging

from app.modules.pi import learning_audit, reply_gates


def test_the_log_carries_result_path_and_prompt_version() -> None:
    assert reply_gates.opening_log(True, "model", "abc123") == {
        "result": "pass",
        "path": "model",
        "prompt_version": "abc123",
    }
    assert reply_gates.opening_log(False, "template", "abc123")["result"] == "fail"


def test_the_fields_are_safe_to_pass_as_logging_extra(caplog) -> None:
    fields = reply_gates.opening_log(True, "model", learning_audit.prompt_version())
    with caplog.at_level(logging.INFO):
        logging.getLogger("test").info("openingGate pass", extra=fields)
    record = caplog.records[-1]
    assert record.result == "pass" and record.path == "model"
    assert record.prompt_version == learning_audit.prompt_version()


def test_the_prompt_version_is_a_short_stable_hash() -> None:
    version = learning_audit.prompt_version()
    assert len(version) == 12 and version == learning_audit.prompt_version()
