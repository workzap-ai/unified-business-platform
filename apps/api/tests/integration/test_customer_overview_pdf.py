"""'Share with my team': a customer's picture from pi as a PDF."""

import pytest
from test_pi_deals import _customer_in_chat, _lead
from test_pi_pipeline import pi_workspace

pytestmark = pytest.mark.integration


async def test_the_team_can_download_the_customers_picture(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    await _lead(pi, customer_id, conversation)  # "Branding for Crescent Bakers"
    await pi.db.commit()

    response = await api.get(f"/api/v1/customers/{customer_id}/pi-overview.pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert "pi%20picture.pdf" in response.headers["content-disposition"]
    pdf = response.content
    assert pdf.startswith(b"%PDF-")
    assert b"Branding for Crescent Bakers" in pdf
    assert b"Who they are" in pdf and b"Projects" in pdf
    await pi.close()
