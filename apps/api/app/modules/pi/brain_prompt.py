"""The brain-mode system prompt: the shared rules without the account-manager sales flow.

`service_conversation.SYSTEM` is one prompt for every workspace. Most of it is an account manager's
playbook (qualify the lead, confirm a brief, ask their name and business, send the brief to the
team, proposals, deals, payment). In brain mode that playbook contradicts the specification (listen
first, one question, no brief, no payment in the chat, nobody reads the chat), and the brain blocks
had to "override" it line by line, which is what platform spec Part A.5 forbids ("do not patch
around a conflict with more text").

So the brain prompt is the same text with those parts cut out. `SYSTEM` itself is not touched, so
every other workspace gets exactly the prompt it always had. Each cut names its start and end in
the original text; one that no longer matches fails at import, so an edit of `SYSTEM` can never
silently bring a removed rule back or drop a kept one.
"""

# (start, end, replacement): the text from `start` up to (not including) `end` is replaced. An end
# of None means "to the end of the text" when the replacement is empty, and otherwise that `start`
# itself is replaced by `replacement`.
CUTS: tuple[tuple[str, str | None, str], ...] = (
    # Confirming a brief in a bullet list: brain mode notes problems and never confirms a brief.
    (
        "- When they give a brief or instructions (e.g. a design change, an order detail), "
        "confirm\n",
        "- When a message is addressed to a named person",
        "",
    ),
    # The plan step still told the model to ask for their name and business and to avoid repeating
    # "Shall I send this to the team?": no brief in brain mode, and R-PRIV-04.
    (
        'no repeated sentences, no\nrepeated "Shall I send this to the team?" while they haven\'t '
        "answered it)",
        None,
        "no repeated sentences)",
    ),
    (
        "for the project and about their business (name, what it does), and\nwhether now is the "
        "right moment to ask (one question at most);",
        None,
        "in what they told you, and whether now is the right moment to ask (one question at most);",
    ),
    # "The company's real team reads this chat": R-DISC-04. The first message is fixed text.
    (
        '- In your first message of a conversation (no "ai" turn in history yet) say plainly in\n',
        "Reply strictly in the\n  customer's own language (reply_language says which)",
        "- ",
    ),
    # Ask a new customer for their name and business: R-PRIV-04, R-ASK-01. The profile is still
    # filled from what they say.
    (
        "A new customer: in your first or second reply,\n",
        "Fill\ncustomer_profile from the customer's own words only",
        "",
    ),
    (
        "Learn these naturally while helping, never as a\n",
        "Never say the company has or offers",
        "",
    ),
    # The account manager's lead qualification, brief confirmation and ideas (2 to 4 and "which one
    # do you like"), which Book 2 and 3 replace with exactly two ideas and the offer.
    (
        "Work like the company's best account manager.",
        "Meetings: when the customer asks for a meeting",
        "",
    ),
    (
        "4. Share facts from approved_knowledge that answer the customer's obvious next worry",
        "wants_person: true ONLY",
        "",
    ),
    # Check-ins ask for their name and business: Book 4 5.4 (a follow-up asks for no known fact).
    (
        "check_in_now: the customer went quiet in the middle of this conversation",
        "A project document they just sent",
        "",
    ),
    ("A project document they just sent", "shared_documents: documents the customer sent", ""),
    # Two questions in a reply: R-VOICE-02.
    (
        'otherwise "calm". Ask at most two short, related questions per reply.',
        None,
        'otherwise "calm".',
    ),
    # Drive every collecting project to a confirmed brief and "Shall I send this to the team?".
    (
        'Projects still "collecting" in brief.projects: never leave them there.',
        "If followups are enabled and consent is unknown",
        "",
    ),
    # Proposals, invoices and paying in the chat: R-PAY-01. Brain mode has its own document, quote
    # and payment gates.
    ("Proposals:\n- When the customer asks where things stand", None, ""),
)


def cut(text: str, cuts: tuple[tuple[str, str | None, str], ...] = CUTS) -> str:
    """`text` with every cut applied, in order. A cut whose start or end is not found raises."""
    for start, end, replacement in cuts:
        at = text.find(start)
        if at < 0:
            raise ValueError(f"brain prompt cut not found: {start[:60]!r}")
        if end is None:
            # to the end of the text, or (with a replacement) only the start text itself
            stop = at + len(start) if replacement else len(text)
        else:
            stop = text.find(end, at + len(start))
            if stop < 0:
                raise ValueError(f"brain prompt cut end not found: {end[:60]!r}")
        text = text[:at] + replacement + text[stop:]
    return text
