"""Which voice each built-in agent speaks with, so it sounds like the character the room shows:
the woman is a woman's voice, the man a man's, and no two agents share one. pi keeps its own voice.
A custom agent has no character picture, so it keeps pi's voice rather than guess a voice that
may not match who the room shows."""

DEFAULT_VOICE = "marin"  # pi

VOICES: dict[str, str] = {
    "pi": DEFAULT_VOICE,
    "sales_coach": "onyx",  # a man, deep and confident
    "negotiation_coach": "sage",  # a woman, calm and measured
    "presentation_coach": "coral",  # a woman, warm and clear
    "training_coach": "fable",  # a man, a patient teacher
    "hustle_coach": "nova",  # a woman, bright and energetic
    "customer_success": "ash",  # a man, friendly and steady
    "interviewer": "cedar",  # a man, thoughtful and low
}


def voice_for(agent_key: str | None) -> str:
    return VOICES.get(agent_key or "", DEFAULT_VOICE)


# How each agent sounds as a person: age, warmth and pace, added to the shared "real person on a
# call" style. Only the manner of speaking: the words and the rules never come from here.
CHARACTER: dict[str, str] = {
    "sales_coach": (
        "You are a confident man in his thirties: relaxed, warm and clear, with natural "
        "enthusiasm, like a trusted mentor. Never pushy or salesy."
    ),
    "negotiation_coach": (
        "You are a composed woman in her thirties: calm, measured and unhurried, with quiet "
        "authority and a hint of a smile."
    ),
    "presentation_coach": (
        "You are a warm, articulate woman in her late twenties: clear and encouraging, with "
        "gentle emphasis on the important words."
    ),
    "training_coach": (
        "You are a patient man in his forties, a kind teacher: a slightly slower pace, gentle "
        "and reassuring, with friendly curiosity."
    ),
    "hustle_coach": (
        "You are an upbeat woman in her twenties: bright, energetic and motivating, quick "
        "but never rushed and never shouting."
    ),
    "customer_success": (
        "You are a friendly man in his thirties, like a helpful colleague from support: "
        "relaxed, warm and reassuring."
    ),
    "interviewer": (
        "You are a thoughtful man in his thirties: calm, a little low and unhurried, curious "
        "and encouraging, with natural pauses to think."
    ),
}


def character_for(agent_key: str | None) -> str:
    """The manner of speaking of this agent ('' for pi and for custom agents)."""
    return CHARACTER.get(agent_key or "", "")
