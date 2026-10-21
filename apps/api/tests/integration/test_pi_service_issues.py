# ruff: noqa: F811 - pytest fixtures imported from the portal tests
"""A customer's problems with the service itself (an invoice they can't download, a
missing payment link, pi's wording) stay off their Problem Map: it shows their business
problems only. The service matters are kept apart for the team."""

from types import SimpleNamespace

import pytest
from test_pi_customer_portal import (  # noqa: F401 - fixtures
    PORTAL,
    _business_with_chat,
    _sign_in,
    app,
    provider,
)

from app.ai.manager import LLMManager
from app.modules.pi.models import PiConversation
from app.modules.pi_customer.service import Issue, IssueLink, IssueReport

pytestmark = pytest.mark.integration

REPORT = IssueReport(
    headline="The team is on it",
    issues=[
        Issue(title="Employee tracking system", stage="on_it", area="Operations"),
        Issue(
            title="Invoice download issue",
            stage="noted",
            about_service=True,
            original_words="how do i download the invoice? there is no link",
        ),
        Issue(title="Website and logo", stage="on_it", area="Sales"),
    ],
    links=[
        IssueLink(a=0, b=1, type="same_cause", confidence=0.9, reason="tracking and reports"),
        IssueLink(a=0, b=2, type="shared_data", confidence=0.9, reason="same staff data"),
    ],
)


async def test_service_problems_stay_off_the_problem_map(app, provider, business_db, monkeypatch):
    async def complete(self, scope, output, **kwargs):
        return SimpleNamespace(value=REPORT, response=SimpleNamespace(attempts=[]))

    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    await customer.get(f"{PORTAL}/conversations/{conversation_id}/issues")

    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert [i["title"] for i in listed["issues"]] == [
        "Employee tracking system",
        "Website and logo",
    ]
    assert [(x["a_title"], x["b_title"]) for x in listed["links"]] == [
        ("Employee tracking system", "Website and logo")
    ]
    conversation = await business_db.get(PiConversation, conversation_id)
    await business_db.refresh(conversation)
    [kept] = conversation.service_brief["customer_issues"]["service_issues"]
    assert kept["title"] == "Invoice download issue"
    await business.aclose()
    await customer.aclose()


async def test_a_request_for_work_always_stays_on_the_map(app, provider, business_db, monkeypatch):
    wrong = IssueReport(
        headline="Waiting on the team",
        issues=[
            # The model wrongly marks the customer's own request as a service matter.
            # Early: no solution outline yet, and the model wrongly marks it.
            Issue(title="ERP System Requirements", category="inquiry", about_service=True),
            # Filed as an inquiry, but it's about paying: stays off.
            Issue(title="Payment Method Inquiry", category="inquiry", about_service=True),
            Issue(title="Invoice download issue", category="support", about_service=True),
            # A question about a meeting is not a problem of theirs.
            Issue(title="Meeting link request", category="booking", about_service=True),
        ],
    )

    async def complete(self, scope, output, **kwargs):
        return SimpleNamespace(value=wrong, response=SimpleNamespace(attempts=[]))

    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    await customer.get(f"{PORTAL}/conversations/{conversation_id}/issues")
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert [i["title"] for i in listed["issues"]] == ["ERP System Requirements"]
    await business.aclose()
    await customer.aclose()


def test_titles_that_name_something_to_build_stay_on_the_map():
    from app.modules.pi_customer.service import BUILD_WORD, SERVICE_MATTER

    def kept(title: str) -> bool:
        return bool(BUILD_WORD.search(title) or not SERVICE_MATTER.search(title))

    for title in (
        "Sales dashboard for my shop",
        "Admin dashboard",
        "Login system for my app",
        "Order status tracking",
        "Stripe checkout for my store",
        "Payment gateway integration",
        "ERP System Requirements",
    ):
        assert kept(title), title
    for title in (
        "Payment Method Inquiry",
        "Project Completion Status",
        "Meeting Link Request",
        "Invoice download issue",
    ):
        assert not kept(title), title
