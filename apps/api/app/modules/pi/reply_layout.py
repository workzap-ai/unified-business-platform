"""How a pi reply is laid out on a phone (expert advisor workspaces).

Words are never changed here, only spacing: short paragraphs, a bullet list set apart from the text
around it, and the one question that ends the reply on its own line so it is the first thing the eye
finds. Plain WhatsApp text: no Markdown headings or tables, "•" bullets, at most one blank line.
"""

import re

BULLET = "•"
_DASH_BULLET = re.compile(r"(?m)^[ \t]*[-*–—][ \t]+(?=\S)")
_NUMBERED = re.compile(r"(?m)^[ \t]*\d{1,2}[.)][ \t]+(?=\S)")
_QUESTION_END = re.compile(r"[?؟]\s*$")
# the last sentence is a question that starts after a sentence end
_LAST_QUESTION = re.compile(r"(?<=[.!۔।])[ \t]+(?=[^.!?۔।\n]{12,}[?؟]\s*$)")
_HEADING = re.compile(r"(?m)^#{1,6}[ \t]+")


def _is_item(line: str) -> bool:
    return line.lstrip().startswith(BULLET) or bool(_NUMBERED.match(line))


def tidy(reply: str) -> str:
    """The same words, laid out for a phone. Safe to run twice."""
    text = (reply or "").replace("\r\n", "\n").strip()
    if not text:
        return text
    text = _HEADING.sub("", text)
    text = _DASH_BULLET.sub(BULLET + " ", text)
    lines = [line.rstrip() for line in text.split("\n")]
    out: list[str] = []
    for index, line in enumerate(lines):
        item = _is_item(line)
        before = _is_item(lines[index - 1]) if index else False
        if item and not before and out and out[-1] != "":
            out.append("")  # a blank line before the list
        elif not item and before and line != "":
            out.append("")  # and after it
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    has_list = any(_is_item(line) for line in text.split("\n"))
    if not has_list and "\n" not in text and _QUESTION_END.search(text):
        # a plain paragraph that ends in the one question: the question stands alone
        parts = _LAST_QUESTION.split(text)
        if len(parts) == 2 and len(parts[0].split()) >= 6:
            text = parts[0].rstrip() + "\n\n" + parts[1].lstrip()
    return text.strip()
