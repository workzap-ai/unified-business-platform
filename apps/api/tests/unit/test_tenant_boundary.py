from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.tenants.schemas import BranchCreate, DepartmentCreate, Rename


def test_identity_headers_and_query_ids_cannot_bypass_auth_boundary(client):
    for path in ("/api/v1/tenants", f"/api/v1/tenants/{uuid4()}/branches"):
        response = client.get(
            path,
            headers={"x-user-id": str(uuid4()), "x-tenant-id": str(uuid4())},
            params={"user_id": str(uuid4())},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("schema", [BranchCreate, DepartmentCreate])
def test_payload_cannot_set_tenant_or_id(schema):
    with pytest.raises(ValidationError):
        schema(name="Branch", code="branch", tenant_id=uuid4())
    with pytest.raises(ValidationError):
        schema(name="Branch", code="branch", id=uuid4())


def test_names_and_codes_are_validated():
    with pytest.raises(ValidationError):
        Rename(name="   ")
    with pytest.raises(ValidationError):
        BranchCreate(name="Valid", code="INVALID CODE")
    assert Rename(name="  Good  ").name == "Good"
