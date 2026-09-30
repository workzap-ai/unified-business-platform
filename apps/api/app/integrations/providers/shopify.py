"""Shopify Admin GraphQL API (https://shopify.dev/docs/api/admin-graphql).

* Connect: the store owner authorizes the platform's Shopify app with the authorization
  code grant (per-shop URLs, HMAC-verified callback; see app.modules.pi_saas.connectors).
  Expiring offline tokens (`expiring=1`) are refreshed with the stored refresh token.
  Scopes: read_orders, read_customers (order lookup for the verified WhatsApp customer).
  Customer email/phone are protected customer data: the Shopify app must be approved for
  that access in the Shopify Dev Dashboard before real stores can connect.
* Test connection: `{ shop { name currencyCode } }` (read-only).
* Orders are read only for a customer found by the conversation's verified phone number
  (or the CRM email on file); a customer never sees another customer's orders.
"""

import re
import time
from collections.abc import Mapping
from typing import Any

from app.integrations.errors import IntegrationError
from app.integrations.providers.base import credential, ok
from app.integrations.registry import (
    CommerceProvider,
    ConfigField,
    HealthResult,
    IntegrationDefinition,
    ProviderContext,
    SyncPage,
)

SHOP = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*\.myshopify\.com$")
SCOPES = ("read_orders", "read_customers")
# Shopify search syntax: quote values and drop characters that change the query.
_UNSAFE = re.compile(r'["\\:()]')

DEFINITION = IntegrationDefinition(
    key="shopify",
    name="Shopify",
    description="Let Pi share order and delivery status from your Shopify store.",
    category="commerce",
    provider="Shopify",
    auth_type="oauth2",
    # Connected from the Pi app's Tools page (per-shop OAuth); not the generic flow.
    availability="beta",
    capabilities=("orders",),
    supported_scopes=SCOPES,
    required_scopes=SCOPES,
    documentation_url="https://shopify.dev/docs/api/admin-graphql/latest/queries/orders",
    config_schema=(ConfigField("shop_domain", "Store address", help="your-store.myshopify.com"),),
)

ORDER_FIELDS = """
  id name createdAt displayFinancialStatus displayFulfillmentStatus cancelledAt
  totalPriceSet { shopMoney { amount currencyCode } }
  lineItems(first: 10) { edges { node { title quantity } } }
"""


def valid_shop(shop: str) -> str:
    shop = shop.strip().lower()
    if shop.startswith("https://"):
        shop = shop[8:]
    shop = shop.rstrip("/")
    if not SHOP.fullmatch(shop) or len(shop) > 120:
        raise IntegrationError("INVALID_SHOP", "Enter your store address, like shop.myshopify.com")
    return shop


def _term(value: str) -> str:
    return '"' + _UNSAFE.sub(" ", value).strip()[:120] + '"'


def _order(node: Mapping[str, Any]) -> dict[str, Any]:
    money = (node.get("totalPriceSet") or {}).get("shopMoney") or {}
    return {
        "name": str(node.get("name") or "")[:40],
        "created_at": str(node.get("createdAt") or ""),
        "payment_status": str(node.get("displayFinancialStatus") or "UNKNOWN")[:40],
        "fulfillment_status": str(node.get("displayFulfillmentStatus") or "UNKNOWN")[:40],
        "cancelled": bool(node.get("cancelledAt")),
        "total": str(money.get("amount") or ""),
        "currency": str(money.get("currencyCode") or "")[:3],
        "items": [
            {
                "title": str(e["node"].get("title") or "")[:120],
                "quantity": e["node"].get("quantity"),
            }
            for e in ((node.get("lineItems") or {}).get("edges") or [])[:10]
            if isinstance(e, dict) and isinstance(e.get("node"), dict)
        ],
    }


class ShopifyProvider(CommerceProvider):
    key = "shopify"
    capabilities = frozenset(DEFINITION.capabilities)

    @staticmethod
    def shop(ctx: ProviderContext) -> str:
        return valid_shop(str(ctx.config.get("shop_domain") or ""))

    async def graphql(
        self, ctx: ProviderContext, query: str, variables: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        version = ctx.settings.shopify_api_version
        response = await ctx.http.request(
            "POST",
            f"https://{self.shop(ctx)}/admin/api/{version}/graphql.json",
            headers={"x-shopify-access-token": credential(ctx.credentials, "access_token")},
            json_body={"query": query, "variables": dict(variables or {})},
            max_bytes=512 * 1024,
            context=ctx.call,
        )
        data = response.ensure_success().json_object()
        if data.get("errors"):
            # GraphQL errors (including THROTTLED) arrive with HTTP 200.
            throttled = any(
                isinstance(e, dict) and (e.get("extensions") or {}).get("code") == "THROTTLED"
                for e in data["errors"]
            )
            raise IntegrationError(
                "SHOPIFY_THROTTLED" if throttled else "SHOPIFY_QUERY_FAILED",
                "Shopify is busy; try again shortly"
                if throttled
                else "Shopify rejected the request",
                kind="rate_limited" if throttled else "invalid_response",
            )
        body = data.get("data")
        if not isinstance(body, dict):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "Shopify returned an unexpected response",
                kind="invalid_response",
            )
        return body

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        data = await self.graphql(ctx, "{ shop { name currencyCode } }")
        if not isinstance(data.get("shop"), dict):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "Shopify returned an unexpected response",
                kind="invalid_response",
            )
        return ok("Shopify store reachable", int((time.perf_counter() - started) * 1000))

    async def customer_orders(
        self, ctx: ProviderContext, *, phone: str | None, email: str | None, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Orders of exactly one Shopify customer matched by phone (preferred) or email.
        No match or an ambiguous match returns nothing rather than guessing."""
        customer_id: str | None = None
        for field, value in (("phone", phone), ("email", email)):
            if not value:
                continue
            found = await self.graphql(
                ctx,
                "query($q: String!) { customers(first: 2, query: $q) { edges { node { id } } } }",
                {"q": f"{field}:{_term(value)}"},
            )
            edges = ((found.get("customers") or {}).get("edges")) or []
            if len(edges) == 1:
                customer_id = str(edges[0]["node"]["id"])
                break
            if len(edges) > 1:
                return []  # Ambiguous: never show one customer another customer's orders.
        if customer_id is None:
            return []
        numeric = customer_id.rsplit("/", 1)[-1]
        if not numeric.isdigit():
            return []
        data = await self.graphql(
            ctx,
            "query($q: String!, $n: Int!) { orders(first: $n, query: $q, sortKey: CREATED_AT,"
            f" reverse: true) {{ edges {{ node {{ {ORDER_FIELDS} }} }} }} }}",
            {"q": f"customer_id:{numeric}", "n": max(1, min(limit, 10))},
        )
        edges = ((data.get("orders") or {}).get("edges")) or []
        return [_order(e["node"]) for e in edges if isinstance(e, dict) and e.get("node")]

    async def list_orders(
        self, ctx: ProviderContext, cursor: str | None
    ) -> SyncPage[Mapping[str, Any]]:
        data = await self.graphql(
            ctx,
            "query($after: String) { orders(first: 50, after: $after) { pageInfo "
            f"{{ hasNextPage endCursor }} edges {{ node {{ {ORDER_FIELDS} }} }} }} }}",
            {"after": cursor},
        )
        orders = data.get("orders") or {}
        info = orders.get("pageInfo") or {}
        return SyncPage(
            [_order(e["node"]) for e in orders.get("edges") or []],
            str(info["endCursor"]) if info.get("hasNextPage") and info.get("endCursor") else None,
        )

    async def list_products(
        self, ctx: ProviderContext, cursor: str | None
    ) -> SyncPage[Mapping[str, Any]]:
        raise IntegrationError(
            "UNSUPPORTED_OPERATION",
            "Product import is not part of this connection",
            kind="permanent",
        )
