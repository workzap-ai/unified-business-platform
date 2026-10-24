"""Asking for the solution document or quote is never noted as a business problem."""

import pytest

from app.modules.pi import problems


@pytest.mark.parametrize(
    "said",
    [
        "Yes please, prepare the document and the quote.",
        "Haan document aur quote bana dein.",
        "send me the quotation",
        "quote bhej do",
    ],
)
def test_a_request_for_the_document_is_rejected_as_a_note(said):
    assert problems.is_document_request([said])


@pytest.mark.parametrize(
    "said",
    [
        "Our quotes take us two days to write and customers go elsewhere",
        "Quote ka kaam bohat slow hai hamare yahan",
        "documents go missing every week",
    ],
)
def test_a_real_problem_about_quotes_or_documents_is_still_a_problem(said):
    assert not problems.is_document_request([said])
