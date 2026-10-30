"""Solution document and quote drafts: the rules, the content, the reviewer's edits and the PDFs
(pi Brain spec Part 5)."""

import time
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.pi import brain_docs as bd
from app.modules.pi import brain_pdf, decisions
from app.modules.pi.brain_docs import Component, SolutionDraft, WontDo
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.flow import State as S
from app.shared.errors import BusinessRuleViolation

REFS = {"aaa11111", "bbb22222"}


def good(**changes):
    base = {
        "components": [
            Component(
                text="A stock check that would tell each shop when a best-seller is getting low.",
                problems=["aaa11111"],
            ),
        ],
        "covers": ["Your four shops and the main godown"],
        "wont_do": [
            WontDo(
                text="It would not change how you order from your suppliers.", problem="bbb22222"
            )
        ],
        "needs": ["One person in each shop to check the counts"],
    }
    return SolutionDraft(**{**base, **changes})


def test_a_good_draft_has_no_issues():
    assert bd.check_solution(good(), REFS) == []


def test_every_component_must_serve_a_known_problem():
    nobody = good(components=[Component(text="A dashboard of everything.", problems=[])])
    assert any("names no known problem" in i for i in bd.check_solution(nobody, REFS))
    wrong = good(components=[Component(text="Something would help.", problems=["zzz"])])
    assert any("names no known problem" in i for i in bd.check_solution(wrong, REFS))


def test_every_problem_is_addressed_or_listed_under_wont_do():
    only_one = good(wont_do=[WontDo(text="It would not change your suppliers.")])
    issues = bd.check_solution(only_one, REFS)
    assert any("bbb22222" in i and "R-DOC-03" in i for i in issues)


def test_wont_do_is_never_empty():
    assert any("R-DOC-04" in i for i in bd.check_solution(good(wont_do=[]), {"aaa11111"}))


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("It would cost Rs 450,000 to set up.", "R-DOC-09"),
        ("It would be done for $5000.", "R-DOC-09"),
        ("This will increase your sales.", "R-DOC-06"),
        ("We guarantee the stock is always right.", "R-DOC-06"),
        ("A KPI view of each shop would be built.", "R-DOC-05"),
    ],
)
def test_prices_promises_and_jargon_are_caught(text, rule):
    draft = good(components=[Component(text=text, problems=["aaa11111"])])
    assert any(rule in i for i in bd.check_solution(draft, REFS))


@pytest.mark.parametrize(
    "text",
    [
        "It would cover your 4 shops and 12 staff since 2024.",
        "A check for problem 36619855 would help.",
        "It would take about 6 weeks.",
    ],
)
def test_a_year_a_count_or_a_reference_is_not_a_price(text):
    draft = good(components=[Component(text=text, problems=["aaa11111"])])
    assert not any("R-DOC-09" in i for i in bd.check_solution(draft, REFS))


@pytest.mark.parametrize(
    "text",
    [
        "It would cost 5000 to set up.",
        "The fee would be 25k.",
        "It would be 2 lakh in total.",
        "A set-up of 1,500 would be needed.",
    ],
)
def test_more_ways_of_writing_a_price_are_caught(text):
    draft = good(components=[Component(text=text, problems=["aaa11111"])])
    assert any("R-DOC-09" in i for i in bd.check_solution(draft, REFS))


def test_a_sentence_that_is_too_long_is_caught():
    long = " ".join(["word"] * 30) + "."
    draft = good(components=[Component(text=long, problems=["aaa11111"])])
    assert any("R-DOC-05" in i for i in bd.check_solution(draft, REFS))


def problem(ref="aaa11111", title="Best-sellers run out in two shops", **extra):
    row = SimpleNamespace(
        id=uuid4(),
        title=title,
        title_local=extra.get("title_local", ""),
        user_words=["We keep running out of our best-selling items.", "Two of the four."],
        scope={"where": ["Shop B", "Shop D"], "of_total": "2 of 4 shops"},
        frequency={"text": "every week"},
        since={"text": "since we opened the 4th shop"},
    )
    return row


def test_section_one_uses_the_persons_words_and_the_facts_in_one_line():
    row = problem()
    ref = str(row.id)[:8]
    draft = good(components=[Component(text="A stock check would help.", problems=[ref])])
    content = bd.solution_content(
        draft, [row], business="Bright Studio", ref="SD-0001", language="en", local=False
    )
    [entry] = content["problems"]
    assert entry["title"] == "Best-sellers run out in two shops"
    assert entry["quotes"] == ["We keep running out of our best-selling items.", "Two of the four."]
    assert (
        entry["line"]
        == "Where: Shop B, Shop D | How often: every week | Since: since we opened the 4th shop"
    )
    assert content["components"][0]["refs"] == [ref]
    assert content["components"][0]["problems"] == ["Best-sellers run out in two shops"]
    assert content["ref"] == "SD-0001" and content["business"] == "Bright Studio"


def test_a_document_in_the_persons_language_keeps_an_english_copy():
    row = problem(title_local="Best-seller maal khatam")
    ref = str(row.id)[:8]
    draft = good(
        components=[
            Component(
                text="A stock check would help.", local="Stock check madad karega.", problems=[ref]
            )
        ],
        covers=["Four shops"],
        covers_local=["Chaar shops"],
    )
    local = bd.solution_content(
        draft, [row], business="B", ref="SD-0001", language="roman_ur", local=True
    )
    english = bd.solution_content(
        draft, [row], business="B", ref="SD-0001", language="roman_ur", local=False
    )
    assert local["components"][0]["text"] == "Stock check madad karega."
    assert local["problems"][0]["title"] == "Best-seller maal khatam"
    assert local["covers"] == ["Chaar shops"]
    assert english["components"][0]["text"] == "A stock check would help."
    assert english["covers"] == ["Four shops"] and english["language"] == "en"


def solution_doc(**changes):
    row = problem()
    ref = str(row.id)[:8]
    draft = good(
        components=[Component(text="A stock check would help.", problems=[ref])],
        wont_do=[WontDo(text="It would not change how you order.")],
    )
    content = bd.solution_content(
        draft, [row], business="Bright Studio", ref="SD-0001", language="en", local=False
    )
    values = dict(
        id=uuid4(),
        kind="solution",
        number=1,
        version=1,
        status="in_review",
        drafted_by="pi",
        content=content,
        content_en={},
        language="en",
        customer_id=uuid4(),
        offer_id=uuid4(),
    )
    return PiBrainDocument(**{**values, **changes})


def quote_doc(**changes):
    solution = solution_doc()
    values = dict(
        id=uuid4(), kind="quote", number=1, version=1, status="in_review", drafted_by="pi",
        content=bd.quote_content(solution.content, "PKR"), content_en={}, language="en",
        customer_id=uuid4(), offer_id=uuid4(), currency="PKR",
    )  # fmt: skip
    return PiBrainDocument(**{**values, **changes})


def test_the_quote_is_a_skeleton_with_no_price_and_no_date():
    quote = quote_doc()
    assert quote.content["cost"]["total"] is None
    assert quote.content["time"]["estimate"] == ""
    assert quote.content["included"] == ["A stock check would help."]
    assert quote.content["not_included"] == ["It would not change how you order."]
    assert quote.content["note"] == "A quote is an offer. It isn't a charge."
    assert "bank" in quote.content["payment"].lower()
    assert quote.total is None and quote.valid_until is None


@pytest.mark.parametrize(
    ("phone", "code"),
    [
        ("+923001234567", "PKR"),
        ("971501234567", "AED"),
        ("+14165550100", "CAD"),
        ("4915112345", ""),
    ],
)
def test_the_currency_follows_the_number(phone, code):
    assert bd.currency_for(SimpleNamespace(phone=phone, whatsapp_id=None)) == code
    assert bd.currency_for(SimpleNamespace(phone=None, whatsapp_id=phone.lstrip("+"))) == code


def test_a_documents_ref_and_version_suffix():
    assert PiBrainDocument(kind="solution", number=7, version=1).ref == "SD-0007"
    assert PiBrainDocument(kind="quote", number=12, version=1).ref == "Q-0012"
    assert PiBrainDocument(kind="quote", number=12, version=2).ref == "Q-0012-v2"


def test_the_reviewer_prices_the_quote():
    quote = quote_doc()
    bd.edit(
        quote,
        {
            "cost": {"total": "450000", "currency": "pkr", "tax_text": "Tax as applicable"},
            "time": {
                "estimate": "About six weeks from kickoff",
                "milestones": ["Week 2: stock check"],
            },
            "valid_until": "2030-12-31",
            "included": ["A stock check", "A kickoff call"],
        },
    )
    assert quote.total == Decimal("450000.00") and quote.currency == "PKR"
    assert quote.valid_until == date(2030, 12, 31)
    assert quote.content["cost"]["total"] == "450000.00"
    assert quote.content["time"]["estimate"] == "About six weeks from kickoff"
    assert quote.content["included"] == ["A stock check", "A kickoff call"]
    assert quote.status == "in_review" and quote.drafted_by == "staff"


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"cost": {"total": "free"}}, "INVALID_TOTAL"),
        ({"cost": {"total": "-5"}}, "INVALID_TOTAL"),
        ({"cost": {"total": "nan"}}, "INVALID_TOTAL"),
        ({"cost": {"currency": "rupees"}}, "INVALID_CURRENCY"),
        ({"valid_until": "next week"}, "INVALID_DATE"),
    ],
)
def test_bad_prices_and_dates_are_refused(patch, code):
    with pytest.raises(BusinessRuleViolation) as caught:
        bd.edit(quote_doc(), patch)
    assert caught.value.code == code


def test_editing_an_approved_document_sends_it_back_to_review_and_a_sent_one_is_locked():
    approved = solution_doc(status="approved", approved_by=uuid4())
    bd.edit(approved, {"covers": ["Four shops"]})
    assert approved.status == "in_review" and approved.approved_by is None
    sent = solution_doc(status="sent")
    with pytest.raises(BusinessRuleViolation) as caught:
        bd.edit(sent, {"covers": ["x"]})
    assert caught.value.code == "DOCUMENT_LOCKED"


def test_the_reviewer_edits_the_solution_and_the_rules_are_checked_again():
    doc = solution_doc()
    ref = doc.content["problems"][0]["ref"]
    bd.edit(
        doc,
        {
            "components": [{"text": "A stock check would help.", "refs": [ref, "bogus"]}],
            "wont_do": [{"text": "It would not change how you order."}],
            "needs": ["A contact in each shop"],
        },
    )
    assert doc.content["components"][0]["refs"] == [ref]
    assert bd.check_content(doc.content) == []
    bd.edit(doc, {"wont_do": []})
    assert any("R-DOC-04" in i for i in bd.check_content(doc.content))
    bd.edit(
        doc, {"wont_do": [{"text": "x"}], "components": [{"text": "Costs Rs 5,000", "refs": [ref]}]}
    )
    assert any("R-DOC-09" in i for i in bd.check_content(doc.content))


def settings():
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        secrets_encryption_key=SecretStr("mock-key-for-tests-1234567890123456"),
        pi_app_public_url="https://pi.example.com",
        app_env="test",
    )


def test_a_document_link_is_signed_and_expires(monkeypatch):
    config = settings()
    doc = SimpleNamespace(id=uuid4(), ref="Q-0001")
    token = bd.doc_token(config, doc.id)
    assert bd.read_doc_token(config, token) == doc.id
    body, mac = token.split(".")
    assert bd.read_doc_token(config, f"{body}.{'x' * len(mac)}") is None
    assert bd.read_doc_token(config, "junk") is None
    other = bd.doc_token(config, uuid4())
    assert bd.read_doc_token(config, other.split(".")[0] + "." + mac) is None
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + bd.DOC_SECONDS + 5)
    assert bd.read_doc_token(config, token) is None


def test_the_link_points_at_the_pi_app_pdf(monkeypatch):
    config = settings()
    doc = PiBrainDocument(id=uuid4(), kind="quote", number=3, version=1)
    url = bd.doc_url(config, doc)
    assert url.startswith("https://pi.example.com/api/v1/pi-app/brain-docs/")
    assert url.endswith("/Q-0003.pdf")


def test_the_pdfs_carry_the_text_and_only_the_quote_carries_bank_details():
    solution = solution_doc()
    pdf = brain_pdf.render_solution(
        solution.content,
        business="Bright Studio",
        ref="SD-0001",
        issued=date(2026, 10, 21),
        language="en",
    )
    assert pdf.startswith(b"%PDF") and b"SD-0001" in pdf
    assert (
        b"pi by Workzap" in pdf and b"Bright Studio" in pdf
    )  # Workzap letterhead, their business named (R-DOC-08)
    assert b"What Workzap would build" in pdf and b"What it won't do" in pdf
    assert b"We keep running out" in pdf  # the person's own words
    assert b"IBAN" not in pdf and b"PK36" not in pdf
    quote = quote_doc(total=Decimal("450000"), valid_until=date(2030, 12, 31))
    bank = [
        {
            "bank": "Meezan Bank",
            "account_title": "Bright",
            "account_number": "01",
            "iban": "PK36SCBL0000001123456702",
        }
    ]
    pdf = brain_pdf.render_quote(
        quote.content, business="Bright Studio", ref="Q-0001", solution_ref="SD-0001",
        issued=date(2026, 10, 21), valid_until=quote.valid_until, total=quote.total,
        currency="PKR", language="en", banks=bank, phone="+1 711 137 4618",
    )  # fmt: skip
    assert b"Q-0001" in pdf and b"PKR 450,000.00" in pdf and b"PK36SCBL0000001123456702" in pdf
    assert b"A quote is an offer. It isn't a charge." in pdf
    assert b"We never ask for payment details in chat." in pdf


def test_a_language_the_font_cannot_draw_is_drawn_in_english():
    assert brain_pdf.drawn_language("roman_ur") == "roman_ur"
    assert brain_pdf.drawn_language("ar") == "en" and brain_pdf.drawn_language("ur") == "en"
    pdf = brain_pdf.render_solution(
        solution_doc().content,
        business="B",
        ref="SD-0001",
        issued=date(2026, 10, 21),
        language="ar",
    )
    assert b"Solution document" in pdf


def test_the_cover_message_and_the_three_decision_buttons():
    cover = bd.COVER["en"].format(n=3)
    assert "A quote is an offer, not a charge." in cover
    assert "approve, ask for changes, or say no" in cover
    assert decisions.DECISION_BUTTONS["en"] == ["Approve", "Ask for changes", "Say no"]
    assert "3 problems" not in bd.COVER["en"]


def test_asking_for_changes_is_noted_confirmed_back_and_sent_to_workzap():
    facts = {
        "change_requests": ["Lower the cost", "Add a second shop"],
        "message_id": "m9",
        "brief": {},
    }
    decision = decisions.decide(
        S.S8B_CHANGES_REQUESTED, "cheaper please and add shop two", "en", facts
    )
    assert decision.reply == (
        "I've sent this to Workzap: Lower the cost; Add a second shop. "
        "They'll send a revised version here."
    )
    assert decision.next_state is None and decision.effects == ["request_revision"]
    assert decision.brief["revision_requested"]["changes"] == [
        "Lower the cost",
        "Add a second shop",
    ]
    assert (
        decisions.decide(S.S8B_CHANGES_REQUESTED, "what is included?", "en", {"brief": {}}) is None
    )
