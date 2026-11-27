"""Each built-in agent speaks with its own voice, matching the character shown in the room."""

from app.modules.pi_meetings.agent_voices import DEFAULT_VOICE, VOICES, voice_for

# the characters: women and men, as drawn
WOMEN = {"negotiation_coach", "presentation_coach", "hustle_coach"}
MEN = {"sales_coach", "training_coach", "customer_success", "interviewer"}
FEMALE_VOICES = {"sage", "coral", "nova", "shimmer", "marin", "alloy"}
MALE_VOICES = {"onyx", "ash", "fable", "cedar", "echo", "verse"}


def test_no_two_agents_share_a_voice():
    assert len(set(VOICES.values())) == len(VOICES)


def test_a_voice_matches_the_character():
    for key in WOMEN:
        assert VOICES[key] in FEMALE_VOICES, key
    for key in MEN:
        assert VOICES[key] in MALE_VOICES, key


def test_pi_and_unknown_agents_keep_pis_voice():
    assert voice_for("pi") == DEFAULT_VOICE
    assert voice_for("my_custom_agent") == DEFAULT_VOICE
    assert voice_for(None) == DEFAULT_VOICE


def test_every_built_in_agent_has_a_voice():
    from app.modules.pi_meetings import agents

    for preset in agents.PRESETS:
        assert preset.key in VOICES, preset.key


def test_each_built_in_agent_has_its_own_manner_and_pi_has_none():
    from app.modules.pi_meetings.agent_voices import CHARACTER, character_for

    assert set(CHARACTER) == set(VOICES) - {"pi"}
    assert len(set(CHARACTER.values())) == len(CHARACTER)
    assert character_for("pi") == "" and character_for("custom_one") == ""
    for text in CHARACTER.values():  # a manner of speaking only: no rules or words in it
        assert "price" not in text.lower() and "say " not in text.lower()
