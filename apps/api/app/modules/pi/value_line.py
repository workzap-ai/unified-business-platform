"""The value line: how much pi gives away for free (Addendum 2 to the pi Brain v3, Part 1).

pi gives the what and the why for free; Workzap sells the how. The numbers and the rules below are
fixed in code. Automatic learning may choose WHICH two ideas pi gives, never how many, and never to
give away the how (Part 1.7 and 3.8): nothing here reads a setting, and `brain_config` has no knob
for any of it. Only a person changing this file changes it.
"""

IDEAS_PER_MESSAGE = 2  # R-VAL-01: two ideas per message, two per problem, never a third
IDEAS_PER_PROBLEM = 2
IDEAS_BEFORE_OFFER = 4  # R-VAL-02: four free ideas per conversation before the offer
IDEAS_AFTER_DECLINE = 2  # at most two more, and only for a new problem
IDEA_MAX_WORDS = 25  # R-VAL-03: one line each, "about" 25 words
IDEA_WORD_SLACK = 5  # "about": a line of up to 30 words is still a line

# What the never-learn list protects (Part 3.8): the value line and how pi describes a build.
NEVER_LEARN_RULES = (
    "R-VAL-01", "R-VAL-02", "R-VAL-03", "R-VAL-04", "R-VAL-05", "R-VAL-06", "R-VAL-07",
    "R-BUILD-01", "R-BUILD-02", "R-BUILD-03", "R-BUILD-04", "R-BUILD-05", "R-BUILD-06",
)  # fmt: skip

# Setting names a learning run must never write (it would be raising or loosening the line).
PROTECTED_SETTINGS = frozenset(
    {
        "ideas_per_message",
        "ideas_per_problem",
        "ideas_before_offer",
        "ideas_after_decline",
        "idea_max_words",
        "value_line",
    }
)


def may_learn(setting: str) -> bool:
    """False for every setting that is part of the value line."""
    return setting not in PROTECTED_SETTINGS and not setting.startswith(("ideas_", "value_line"))
