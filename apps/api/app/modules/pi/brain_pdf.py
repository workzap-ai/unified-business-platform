# ruff: noqa: E501  (document texts and rule messages read better on one line each)
"""The solution document and the quote as PDFs (pi Brain spec 5.2, 5.3).

Both are plain and short. The quote carries the bank details (only here, never in chat: R-PAY-03,
R-QUOTE-06). The PDF writer draws Latin-1 text, so a document in Urdu script or Arabic is drawn from
its English copy and the person's own words stay in the chat.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.shared.pdf import MARGIN, WIDTH, Document, wrap

INK = (0.1, 0.1, 0.12)
MUTED = (0.42, 0.44, 0.48)
BRAND = (0.05, 0.37, 0.31)
LIGHT = (0.85, 0.94, 0.9)
BOTTOM = 745.0
RIGHT = WIDTH - MARGIN

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "solution": "Solution document",
        "quote": "Quote",
        "prepared": "Prepared from what you told pi. Reference",
        "problems": "1. Your problems, in your words",
        "build": "2. What Workzap would build",
        "covers": "3. What it covers",
        "wont": "4. What it won't do",
        "needs": "5. What we'd need from you",
        "next": "6. Next step",
        "next_text": "Read this with your quote. You can approve, ask for changes, or say no.",
        "included": "What's included",
        "cost": "Cost",
        "time": "Time",
        "payment": "How payment works",
        "not_included": "What's not included",
        "decide": "How to decide",
        "decide_text": "Approve, ask for changes, or say no.",
        "offer": "A quote is an offer. It isn't a charge.",
        "valid": "Valid until",
        "total": "Total",
        "bank": "Bank details",
        "verify": "Bank details are only in this PDF. Before paying, verify them on",
        "never": "We never ask for payment details in chat.",
        "for": "For solution document",
        "box_title": "Solution Box",
        "box_problems": "1. Your problem map, in your words",
        "box_happening": "2. What is happening",
        "box_links": "How they may connect",
        "box_hypothesis": "Our guess",
        "box_ideas": "3. Two ideas for each problem",
        "box_build": "4. What Workzap would build, in phases",
        "box_order": "5. Order of work",
        "box_needs": "6. What we'd need from you",
        "box_assume": "7. Assumptions and open questions",
        "box_quote": "8. Quote",
        "box_quote_text": "Your quote comes with this box, phase by phase. Bank details are only in the quote PDF.",
        "box_naya": "New since the last box",
    },
    "roman_ur": {
        "solution": "Solution document",
        "quote": "Quote",
        "prepared": "Ye us se bana hai jo aap ne pi ko bataya. Hawala",
        "problems": "1. Aap ke masail, aap ke alfaz mein",
        "build": "2. Workzap kya banayega",
        "covers": "3. Ye kis cheez ko cover karta hai",
        "wont": "4. Ye kya nahi karega",
        "needs": "5. Hamein aap se kya chahiye",
        "next": "6. Agla qadam",
        "next_text": "Isay apne quote ke saath parhein. Aap manzoor kar sakte hain, tabdeeli maang sakte hain, ya mana kar sakte hain.",
        "included": "Kya shamil hai",
        "cost": "Kharcha",
        "time": "Waqt",
        "payment": "Payment kaise hogi",
        "not_included": "Kya shamil nahi",
        "decide": "Faisla kaise karein",
        "decide_text": "Manzoor karein, tabdeeli maangein, ya mana karein.",
        "offer": "Quote ek offer hai. Ye charge nahi hai.",
        "valid": "Is tareekh tak durust",
        "total": "Kul",
        "bank": "Bank ki details",
        "verify": "Bank ki details sirf isi PDF mein hain. Payment se pehle in ko is number par verify karein",
        "never": "Hum chat mein kabhi payment ki details nahi maangte.",
        "for": "Solution document",
        "box_title": "Solution Box",
        "box_problems": "1. Aap ka naqsha, aap ke alfaz mein",
        "box_happening": "2. Kya ho raha hai",
        "box_links": "Ye kaise jude ho sakte hain",
        "box_hypothesis": "Hamara andaza",
        "box_ideas": "3. Har masle ke liye do ideas",
        "box_build": "4. Workzap kya banayega, marhalon mein",
        "box_order": "5. Kaam ki tarteeb",
        "box_needs": "6. Hamein aap se kya chahiye",
        "box_assume": "7. Farz kiye gaye nukte aur khule sawal",
        "box_quote": "8. Quote",
        "box_quote_text": "Aap ka quote is box ke saath hai, marhale ba marhale. Bank ki details sirf quote PDF mein hain.",
        "box_naya": "Pichle box ke baad naya",
    },
}
PDF_LANGUAGES = frozenset(LABELS)


def drawn_language(language: str) -> str:
    """The language a PDF is drawn in: ones the font can write, otherwise English."""
    return language if language in PDF_LANGUAGES else "en"


def _day(value: date | None) -> str:
    return f"{value:%d %b %Y}" if value else "-"


def money(total: Decimal | None, currency: str) -> str:
    return f"{currency} {total:,.2f}" if total is not None else "-"


class _Page:
    """A running cursor down the page that opens a new page when a block will not fit."""

    def __init__(self, doc: Document, y: float) -> None:
        self.doc, self.y = doc, y

    def room(self, need: float) -> None:
        if self.y + need > BOTTOM:
            self.doc.new_page()
            self.y = MARGIN + 12

    def heading(self, text: str) -> None:
        self.room(40)
        self.doc.text(MARGIN, self.y, text, 11, True, BRAND)
        self.y += 20

    def paragraph(self, text: str, size: float = 10, bold: bool = False, indent: float = 0) -> None:
        for line in wrap(text, size, RIGHT - MARGIN - indent):
            self.room(15)
            self.doc.text(MARGIN + indent, self.y, line, size, bold)
            self.y += 14

    def bullet(self, text: str) -> None:
        lines = wrap(text, 10, RIGHT - MARGIN - 14)
        self.room(14 * len(lines) + 4)
        self.doc.text(MARGIN, self.y, "-", 10, True, BRAND)
        for line in lines:
            self.doc.text(MARGIN + 14, self.y, line, 10)
            self.y += 14
        self.y += 3

    def gap(self, points: float = 10) -> None:
        self.y += points


def _header(doc: Document, business: str, title: str, number: str, issued: date) -> float:
    # Workzap's letterhead only (R-DOC-08); the customer's business is named under it.
    doc.box(0, 0, WIDTH, 84, BRAND)
    doc.text(MARGIN, 40, "Workzap", 19, True, (1, 1, 1))
    doc.text(MARGIN, 62, "pi by Workzap", 11, False, LIGHT)
    doc.text(RIGHT, 40, number, 14, True, (1, 1, 1), "right")
    doc.text(RIGHT, 62, _day(issued), 11, False, LIGHT, "right")
    doc.text(MARGIN, 112, f"{title} - {business}", 13, True, INK)
    return 140.0


def render_box(
    content: dict[str, Any], *, business: str, ref: str, issued: date, language: str
) -> bytes:
    """The Solution Box as the spec's eight sections (5.2). The quote itself is its own PDF."""
    label = LABELS[drawn_language(language)]
    doc = Document(title=f"{label['box_title']} {ref}")
    page = _Page(doc, _header(doc, business, label["box_title"], ref, issued))
    page.paragraph(f"{label['prepared']}: {ref}", 9)
    if content.get("naya"):
        page.paragraph(f"{label['box_naya']}: " + "; ".join(str(x) for x in content["naya"]), 9)
    page.gap(12)
    page.heading(label["box_problems"])
    for problem in content.get("problems", []):
        page.paragraph(str(problem.get("title", "")), 11, True)
        for quote in problem.get("quotes", [])[:2]:
            page.paragraph(f'"{quote}"', 10, indent=10)
        page.gap(4)
    page.heading(label["box_happening"])
    for cluster in content.get("clusters", []):
        page.paragraph(str(cluster.get("name", "")), 11, True)
        for item in cluster.get("happening", []):
            page.paragraph(str(item.get("title", "")), 10, indent=10)
            if item.get("line"):
                page.paragraph(str(item["line"]), 9, indent=20)
        for guess in cluster.get("hypotheses", []):
            page.bullet(f"{label['box_hypothesis']}: {guess}")
        page.gap(4)
    if content.get("links"):
        page.paragraph(label["box_links"], 10, True)
        for line in content["links"]:
            page.bullet(str(line))
    page.gap(6)
    page.heading(label["box_ideas"])
    for entry in content.get("ideas", []):
        page.paragraph(str(entry.get("title", "")), 10, True)
        for idea in entry.get("ideas", []):
            page.bullet(str(idea))
    page.gap(6)
    page.heading(label["box_build"])
    for phase in content.get("phases", []):
        page.paragraph(str(phase.get("name", "")), 11, True)
        for component in content.get("components", []):
            if int(component.get("phase") or 1) == phase.get("phase"):
                page.bullet(str(component.get("text", "")))
    for item in content.get("wont_do", []):
        page.bullet(f"{label['wont'][3:]}: {item.get('text', '')}")
    page.gap(6)
    page.heading(label["box_order"])
    for number, step in enumerate(content.get("order", []), start=1):
        page.bullet(f"{number}. {step.get('title', '')}: {step.get('why', '')}")
    page.gap(6)
    page.heading(label["box_needs"])
    for item in content.get("needs", []):
        page.bullet(str(item))
    page.gap(6)
    page.heading(label["box_assume"])
    for item in content.get("assumptions", []):
        page.bullet(str(item))
    page.gap(6)
    _blueprint(page, content.get("blueprint"))
    page.heading(label["box_quote"])
    page.paragraph(label["box_quote_text"])
    return doc.render()


def _blueprint(page: "_Page", blueprint: Any) -> None:
    """The blueprint for the reviewer, as PS-4 rendered it in the owner's language (plain text, one
    line per fact, the owner's own words kept); a refused or incomplete one shows what is missing."""
    if not isinstance(blueprint, dict) or not str(blueprint.get("text") or "").strip():
        return
    lines = str(blueprint["text"]).splitlines()
    page.heading(lines[0] if lines else "Blueprint")
    for line in lines[1:]:
        if not line.strip():
            page.gap(3)
        else:
            page.paragraph(line, 9)
    page.gap(6)


def render_solution(
    content: dict[str, Any], *, business: str, ref: str, issued: date, language: str
) -> bytes:
    if content.get("box"):
        return render_box(content, business=business, ref=ref, issued=issued, language=language)
    label = LABELS[drawn_language(language)]
    doc = Document(title=f"{label['solution']} {ref}")
    page = _Page(doc, _header(doc, business, label["solution"], ref, issued))
    page.paragraph(f"{label['prepared']}: {ref}", 9)
    page.gap(12)
    page.heading(label["problems"])
    for problem in content.get("problems", []):
        page.paragraph(str(problem.get("title", "")), 11, True)
        for quote in problem.get("quotes", [])[:2]:
            page.paragraph(f'"{quote}"', 10, indent=10)
        if problem.get("line"):
            page.paragraph(str(problem["line"]), 9, indent=10)
        page.gap(6)
    page.heading(label["build"])
    for component in content.get("components", []):
        page.bullet(str(component.get("text", "")))
        if component.get("problems"):
            page.paragraph("(" + ", ".join(component["problems"]) + ")", 9, indent=14)
    page.gap(6)
    page.heading(label["covers"])
    for item in content.get("covers", []):
        page.bullet(str(item))
    page.gap(6)
    page.heading(label["wont"])
    for item in content.get("wont_do", []):
        page.bullet(str(item.get("text", "")))
    page.gap(6)
    page.heading(label["needs"])
    for item in content.get("needs", []):
        page.bullet(str(item))
    page.gap(6)
    page.heading(label["next"])
    page.paragraph(label["next_text"])
    return doc.render()


def render_quote(
    content: dict[str, Any],
    *,
    business: str,
    ref: str,
    solution_ref: str,
    issued: date,
    valid_until: date | None,
    total: Decimal | None,
    currency: str,
    language: str,
    banks: list[dict[str, Any]],
    phone: str | None,
) -> bytes:
    label = LABELS[drawn_language(language)]
    doc = Document(title=f"{label['quote']} {ref}")
    page = _Page(doc, _header(doc, business, label["quote"], ref, issued))
    page.paragraph(f"{label['for']} {solution_ref}   |   {label['valid']} {_day(valid_until)}", 9)
    page.gap(12)
    page.heading(label["included"])
    for item in content.get("included", []):
        page.bullet(str(item))
    page.gap(6)
    page.heading(label["cost"])
    doc.text(MARGIN, page.y, label["total"], 10, False, MUTED)
    doc.text(RIGHT, page.y, money(total, currency), 14, True, INK, "right")
    page.y += 24
    cost = content.get("cost", {})
    for phase in content.get("phases", []):  # Solution Box: the quote by phase (spec 5.2, 8)
        doc.text(MARGIN, page.y, str(phase.get("name", "")), 10, False, MUTED)
        priced = Decimal(str(phase["price"])) if phase.get("price") else None
        doc.text(RIGHT, page.y, money(priced, currency), 10, True, INK, "right")
        page.y += 16
    if cost.get("tax_text"):
        page.paragraph(str(cost["tax_text"]), 9)
    for step in cost.get("instalments", []):
        page.bullet(str(step))
    page.gap(6)
    page.heading(label["time"])
    time = content.get("time", {})
    page.paragraph(str(time.get("estimate", "")))
    for milestone in time.get("milestones", []):
        page.bullet(str(milestone))
    page.gap(6)
    page.heading(label["payment"])
    page.paragraph(str(content.get("payment", "")))
    page.gap(4)
    if banks:
        page.room(30 + 70 * min(len(banks), 2))
        doc.text(MARGIN, page.y, label["bank"], 9, True, MUTED)
        page.y += 18
        for account in banks[:2]:
            rows = [
                ("Bank", account.get("bank", "")),
                ("Account title", account.get("account_title", "")),
                ("Account no.", account.get("account_number", "")),
                ("IBAN", account.get("iban", "")),
                ("Branch", account.get("branch", "")),
            ]
            rows = [(n, str(v)) for n, v in rows if v]
            page.room(14 * len(rows) + 10)
            for name, value in rows:
                doc.text(MARGIN, page.y, name, 9, False, MUTED)
                doc.text(MARGIN + 90, page.y, value, 10, name == "IBAN")
                page.y += 14
            page.y += 10
    page.heading(label["not_included"])
    for item in content.get("not_included", []):
        page.bullet(str(item))
    page.gap(6)
    page.heading(label["decide"])
    page.paragraph(label["decide_text"])
    page.paragraph(label["offer"], 10, True)
    footer = f"{label['verify']} {phone}. " if phone else ""
    footer += label["never"]
    doc.line(MARGIN, 752, RIGHT, 752)
    for i, line in enumerate(wrap(footer, 9, RIGHT - MARGIN)[:2]):
        doc.text(MARGIN, 766 + i * 12, line, 9, False, MUTED)
    return doc.render()
