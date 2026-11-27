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
