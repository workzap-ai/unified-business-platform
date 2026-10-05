"""Editing and deleting PI knowledge: what PI can find changes immediately."""

import pytest
from test_pi_pipeline import pi_workspace
from test_service_lifecycle import create

pytestmark = pytest.mark.integration
K = "/api/v1/pi/knowledge"


async def found(api, query):
    response = await api.get(f"{K}/search", params={"q": query})
    assert response.status_code == 200, response.text
    return [r["title"] for r in response.json()]


async def test_edit_and_delete_documents_and_sources(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    source = await create(api, "pi/knowledge/sources", {"name": "Old site", "kind": "company_info"})
    doc = await create(
        api,
        "pi/knowledge/documents",
        {"source_id": source["id"], "title": "Towels", "body": "We sell 550gsm hotel towels."},
    )
    keep = await create(
        api,
        "pi/knowledge/documents",
        {"source_id": source["id"], "title": "Hours", "body": "Open Monday to Saturday."},
    )
    assert await found(api, "towels") == ["Towels"]

    # Edit: new title and text; PI forgets the old text and finds the new one.
    edited = await api.patch(
        f"{K}/documents/{doc['id']}",
        json={"title": "Bed linen", "body": "We sell 300 thread count bedsheets."},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Bed linen" and edited.json()["status"] == "ready"
    assert await found(api, "towels") == []
    assert await found(api, "bedsheets") == ["Bed linen"]
    # Only the title.
    renamed = await api.patch(f"{K}/documents/{doc['id']}", json={"title": "Linen"})
    assert renamed.json()["title"] == "Linen" and "bedsheets" in renamed.json()["body"]
    blank = await api.patch(f"{K}/documents/{doc['id']}", json={"title": "  "})
    assert blank.status_code == 422

    # Edit a source.
    updated = await api.patch(
        f"{K}/sources/{source['id']}", json={"name": "Website", "description": "From workzap.ai"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Website" and updated.json()["documents"] == 2

    # Delete one document, then the source with what's left.
    assert (await api.delete(f"{K}/documents/{doc['id']}")).status_code == 204
    assert await found(api, "bedsheets") == []
    deleted = await api.delete(f"{K}/sources/{source['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted_documents": 1}
    assert await found(api, "monday") == []
    assert (await api.get(f"{K}/documents/{keep['id']}")).status_code == 404
    assert all(s["id"] != source["id"] for s in (await api.get(f"{K}/sources")).json())
    await pi.close()
