"""The example bank's gates and the question arms' rules (spec 8.4, 8.5, 8.8; evals L1, L2, L7)."""

import pytest

from app.modules.pi import learning, learning_arms, learning_bank, learning_context


@pytest.mark.parametrize(
    "text",
    [
        "Thanks. I've noted it: stock running out. Is it every shop, or only some?",
        "Where do you notice it most: sales, stock, staff or cash?",
        "Shukriya. Note kar liya: udhaar ke paise wapas nahi aate.",
    ],
)
def test_plain_replies_pass_the_redaction_gate(text):
    assert learning_bank.redaction_confidence(text) >= 0.98


@pytest.mark.parametrize(
    "text",
    [
        "Thanks Ali, is it the Johar Town branch?",  # a name and a place in the middle
        "Call me on 0300 1234567 about the stock",  # a number
        "See https://example.com for what I mean",  # a link
        "mail me at ali@example.com please",  # a contact detail
        "my card is 4111 1111 1111 1111",  # redacted by the PII pass
        "There are 3 shops and Ahmed runs one",  # a digit and a name
    ],
)
def test_text_that_may_hold_personal_data_is_kept_out(text):
    assert learning_bank.redaction_confidence(text) < 0.98


def test_the_rubric_proxy_passes_clean_replies_only():
    assert learning_bank.rubric_proxy("Is it every shop, or only some?") == 2.0
    assert learning_bank.rubric_proxy("Is it every shop? Or is it the cash too?") == 1.0


def test_similarity_and_cosine():
    assert (
        learning_bank.similarity("stock runs out in two shops", "stock runs out in three shops")
        > 0.5
    )
    assert learning_bank.similarity("stock runs out", "cashiers are late") == 0.0
    assert learning_bank.similarity("", "anything") == 0.0
    assert learning_bank.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert learning_bank.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert learning_bank.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_only_the_listening_loop_can_teach():
    assert learning_bank.LISTENING_STATES == ("S1_LISTENING", "S2_CLARIFYING", "S3_NOTED")


def test_backing_off_drops_the_turn_kind_then_the_state():
    levels = learning_bank._backoff("S2_CLARIFYING", "en", "question")
    assert levels == [
        {"state": "S2_CLARIFYING", "language": "en", "turn_kind": "question"},
        {"state": "S2_CLARIFYING", "language": "en"},
        {"language": "en"},
    ]


def test_the_next_question_slot_follows_the_question_policy():
    assert learning_arms.slot_for(["where", "how_often", "impact", "since"]) == "scope"
    assert learning_arms.slot_for(["how_often", "impact"]) == "frequency"
    assert learning_arms.slot_for(["impact", "since"]) == "impact"
    assert learning_arms.slot_for(["since"]) == "since"
    assert learning_arms.slot_for([]) is None
    assert learning_arms.slot_for(["unknown_field"]) is None


def test_every_seeded_wording_is_a_single_clean_question():  # L7 applied to the seeds themselves
    for slot, by_language in learning_arms.SEEDS.items():
        for language, texts in by_language.items():
            for text in texts:
                assert text.endswith("?"), (slot, text)
                assert learning.never_learn(text) == [], (slot, language, text)


def test_a_wording_with_two_questions_or_a_pitch_is_never_learnable():
    assert learning.never_learn("Is it every shop? And how often does it happen?")
    assert learning.never_learn("Is it every shop? Workzap can build an app for that.")


def test_an_answer_counts_for_a_wording_only_when_useful_and_clean():
    assert learning_arms.was_useful(["rich_reply"])
    assert learning_arms.was_useful(["confirmed_first_time", "thanked"])
    assert not learning_arms.was_useful(["short_neutral"])
    assert not learning_arms.was_useful(["rich_reply", "confusion"])
    assert not learning_arms.was_useful(["drop_off"])
    assert not learning_arms.was_useful([])


def test_learning_context_is_active_only_when_switched_on_explicitly():
    assert learning_context.active({"pi_mode": "brain", "brain": {"learning_frozen": False}})
    assert not learning_context.active({"pi_mode": "brain"})  # frozen by default
    assert not learning_context.active({"pi_mode": "brain", "brain": {"learning_frozen": True}})
    assert not learning_context.active({"pi_mode": "standard", "brain": {"learning_frozen": False}})
    assert not learning_context.active(None)


def test_embeddings_are_only_used_when_the_platform_has_them(settings):
    from app.modules.pi.learning_embed import make_embedder

    assert make_embedder(settings, None) is None  # no HTTP client
    off = settings.model_copy(update={"semantic_search_enabled": False})
    assert make_embedder(off, object()) is None  # not switched on
    no_model = settings.model_copy(update={"semantic_search_enabled": True, "openai_models": {}})
    assert make_embedder(no_model, object()) is None  # no embedding model configured
    on = settings.model_copy(
        update={"semantic_search_enabled": True, "openai_models": {"embedding": "some-model"}}
    )
    assert make_embedder(on, object()) is not None
