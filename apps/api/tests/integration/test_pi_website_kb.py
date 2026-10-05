"""Learn a business's website: crawl, extract, draft, publish as documents, refresh."""

import httpx
import pytest
from pi_saas_support import pi_client, pi_register
from test_pi_connectors import public

from app.modules.pi_saas import website_kb

pytestmark = pytest.mark.integration
BASE = "/api/v1/pi-app"

MENU = "<nav>Home About Services Contact</nav>"
FOOTER = "<footer><p>Call us on +971 50 123 4567</p><p>Lagoon Home Collection</p></footer>"


def page(title: str, body: str, links: str = "") -> str:
    return (
        f"<html><head><title>{title}</title><style>.x{{}}</style></head><body>{MENU}"
        f"<main>{body}</main>{links}{FOOTER}<script>track()</script></body></html>"
    )


SITE = {
    "/": page(
        "Lagoon Home Collection",
        "<h1>Hotel towels and linen</h1><p>We supply hotels across the GCC with towels, "
        "bed linen and bathrobes made from long-staple cotton.</p>",
        '<a href="/about">About</a> <a href="https://other.example/x">Other site</a>'
        ' <a href="/catalogue.pdf">PDF</a> <a href="/cart">Cart</a> <a href="/old-services">S</a>',
    ),
    "/about": page(
        "About us",
        "<p>Founded in 2012 in Ajman, UAE. We weave 550gsm and 600gsm towels and print "
        "the client's logo on request.</p>",
    ),
    "/services": page(
        "Services",
        "<ul><li>Custom logo embroidery</li><li>Minimum order 200 pieces per carton</li>"
        "<li>Delivery across Qatar and UAE in 10 working days</li></ul>",
    ),
    "/faq": page(
        "FAQ",
        "<p>Do you ship to Doha? Yes, we ship to Doha with door delivery.</p>"
        "<p>Can we pay by bank transfer? Yes, bank transfer and cheque.</p>",
    ),
}
SITEMAP = (
    '<?xml version="1.0"?><urlset>'
    "<loc>https://lagoonhc.example/services</loc><loc>https://lagoonhc.example/faq</loc>"
    "<loc>https://elsewhere.example/page</loc></urlset>"
)


class Site:
    def __init__(self) -> None:
        self.paths: list[str] = []
        self.pages = dict(SITE)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        if request.url.host != "lagoonhc.example":
            return httpx.Response(404)
        if path == "/sitemap.xml":
            return httpx.Response(200, text=SITEMAP, headers={"content-type": "application/xml"})
        if path == "/old-services":
            return httpx.Response(301, headers={"location": "/services"})
        if path in self.pages:
            return httpx.Response(
                200, text=self.pages[path], headers={"content-type": "text/html; charset=utf-8"}
            )
        return httpx.Response(404)


def test_boilerplate_is_removed_and_contact_details_kept_once():
    pages = [
        {"text": f"Home About\nPage {i} text that is unique\nCall us on +971 50 123 4567"}
        for i in range(4)
    ]
    kept = website_kb.strip_boilerplate(pages)
    assert kept == ["Call us on +971 50 123 4567"]
    assert all(p["text"] == f"Page {i} text that is unique" for i, p in enumerate(pages))
    assert website_kb.normalize("https://WWW.Shop.example/about/?a=1#x") == (
        "https://www.shop.example/about"
    )
    assert website_kb.score("https://x.example/contact") > website_kb.score(
        "https://x.example/blog/2020/01/post"
    )


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


async def test_owner_learns_the_website_and_publishes_pages_as_documents(app):
    site = Site()
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(site))
    app.state.integration_resolver = public
    owner = pi_client(app)
    await pi_register(owner, "Lagoon Home Collection")

    bad = await owner.post(
        f"{BASE}/knowledge/website/crawl", json={"url": "http://lagoonhc.example"}
    )
    assert bad.status_code == 422 or bad.json()["error"]["code"] == "INVALID_URL"

    response = await owner.post(
        f"{BASE}/knowledge/website/crawl", json={"url": "https://lagoonhc.example", "max_pages": 6}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["site"] == "lagoonhc.example"
    titles = [d["title"] for d in result["drafts"]]
    # Home, then the most useful pages; the redirect landed on /services (read once).
    assert titles[0] == "Lagoon Home Collection"
    assert {"About us", "Services", "FAQ", "Contact details"} <= set(titles)
    assert titles.count("Services") == 1
    # Never left the site, never fetched files or cart pages.
    assert "/catalogue.pdf" not in site.paths and "/cart" not in site.paths
    assert all(d["origin"] == "website" and d["status"] == "draft" for d in result["drafts"])
    about = next(d for d in result["drafts"] if d["title"] == "About us")
    assert "550gsm" in about["content"]
    assert "Home About Services Contact" not in about["content"]  # the menu is gone
    assert "+971" not in about["content"]  # the footer is gone from each page...
    contact = next(d for d in result["drafts"] if d["title"] == "Contact details")
    assert "+971 50 123 4567" in contact["content"]  # ...and kept once
    assert about["source_note"].startswith("Imported from https://lagoonhc.example/about on ")

    # Nothing is used before publishing.
    documents = (await owner.get(f"{BASE}/pi/knowledge/documents")).json()
    assert documents == []

    ids = [d["id"] for d in result["drafts"]]
    published = await owner.post(f"{BASE}/knowledge/drafts/publish", json={"ids": ids})
    assert published.status_code == 200, published.text
    assert published.json() == {"published": len(ids), "failed": []}
    documents = (await owner.get(f"{BASE}/pi/knowledge/documents")).json()
    assert len(documents) == len(ids)
    assert {d["source_name"] for d in documents} == {"Website"}
    assert any(d["body"].startswith("Source: https://lagoonhc.example/faq\n\n") for d in documents)

    # Publishing the same draft twice reports it, and a refreshed page replaces the old one.
    again = await owner.post(f"{BASE}/knowledge/drafts/publish", json={"ids": ids[:1]})
    assert again.json()["published"] == 0 and len(again.json()["failed"]) == 1
    site.pages["/faq"] = page("FAQ", "<p>Do you ship to Doha? Yes, in 7 working days now.</p>")
    refresh = await owner.post(
        f"{BASE}/knowledge/website/crawl",
        json={"url": "https://lagoonhc.example/faq", "max_pages": 1},
    )
    assert refresh.status_code == 201, refresh.text
    new_faq = refresh.json()["drafts"][0]
    assert new_faq["title"] == "FAQ" and "7 working days" in new_faq["content"]
    await owner.post(f"{BASE}/knowledge/drafts/publish", json={"ids": [new_faq["id"]]})
    documents = (await owner.get(f"{BASE}/pi/knowledge/documents")).json()
    faq_docs = [d for d in documents if "lagoonhc.example/faq" in d["body"]]
    assert len(faq_docs) == 1 and "7 working days" in faq_docs[0]["body"]
    await owner.aclose()


async def test_unreachable_website_is_a_clear_error(app):
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    app.state.integration_resolver = public
    owner = pi_client(app)
    await pi_register(owner, "Down Co")
    response = await owner.post(
        f"{BASE}/knowledge/website/crawl", json={"url": "https://down.example"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WEBSITE_UNREACHABLE"
    await owner.aclose()
