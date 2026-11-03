"""Business Profile grounding for the idea filter (platform spec v1.4, 16.3, G2, OT13): an idea may
rely on a business fact only if the owner said it in the chat or it is a confirmed profile fact."""

from app.modules.pi import business_profile, business_profile_store, idea_filter, public_page

IDEA = "Show the old sets on your website first."
OWNER_WORDS = "mera clothing brand hai, kapre bik nahi rahe"


def page_profile() -> dict:
    profile = business_profile.new_profile()
    result = public_page.PageResult(
        status="ok",
        url="https://ata.example",
        title="Ata Clothing | Home",
        description="We sell clothes online",
        orders_online=True,
    )
    return business_profile.from_page(profile, result)


def test_a_website_idea_fails_without_any_grounding() -> None:
    assert idea_filter.failures(IDEA, OWNER_WORDS) == ["G2"]


def test_an_unconfirmed_page_fact_does_not_ground_the_idea() -> None:
    profile = business_profile.new_profile()
    business_profile.add_fact(
        profile, "what_they_do", "an online store with a website shop", business_profile.PAGE
    )
    assert business_profile.grounding_text(profile) == ""
    ctx = idea_filter.with_grounding(None, business_profile.grounding_text(profile))
    assert idea_filter.failures(IDEA, OWNER_WORDS, ctx) == ["G2"]


def test_a_confirmed_profile_fact_grounds_the_idea() -> None:
    profile = business_profile.confirm(page_profile(), ["website_url", "online_orders"])
    grounded = business_profile.grounding_text(profile)
    assert "website_url" in grounded
    ctx = idea_filter.with_grounding(None, f"website {grounded}")
    assert idea_filter.failures(IDEA, OWNER_WORDS, ctx) == []


def test_grounding_keeps_the_other_guards_of_the_context() -> None:
    base = idea_filter.IdeaContext(subtype="stockout", industries=("apparel",))
    ctx = idea_filter.with_grounding(base, "website shop")
    assert ctx is not None and ctx.subtype == "stockout" and ctx.grounded == "website shop"
    assert ctx.active() is base.active()


def test_without_facts_the_context_is_unchanged() -> None:
    base = idea_filter.IdeaContext(subtype="stockout")
    assert idea_filter.with_grounding(base, "  ") is base
    assert idea_filter.with_grounding(None, "") is None


def test_grounding_does_not_loosen_the_goal_rule() -> None:
    ctx = idea_filter.with_grounding(None, "website shop")
    stock = "mera clothing brand hai 6 crore ka stock bechna hai"
    assert idea_filter.failures("Keep a buffer of the fast sellers back.", stock, ctx) == ["G1"]


def test_the_summary_columns_come_from_the_facts() -> None:
    summary = business_profile_store.summary_from(
        {
            "business_name": "Ata Clothing",
            "what_they_do": "baby and male clothes",
            "since": "since 2011, two outlets",
            "channels": "walk-in, whatsapp",
            "social_urls": "https://instagram.com/ata https://facebook.com/ata",
            "website": "none",
        }
    )
    assert summary["display_name"] == "Ata Clothing"
    assert summary["since_year"] == 2011
    assert summary["channels"] == ["walk-in", "whatsapp"]
    assert len(summary["social_urls"]) == 2
    assert summary["digital_flags"] == {"website": "none"}  # a fact, not a problem


def test_stored_rows_become_the_dict_the_warmup_reads() -> None:
    class Row:
        key, value, source, confirmed = "what_they_do", "baby clothes", "page", False
        evidence_snippet, source_url = "Ata", "https://ata.example"

    profile = business_profile_store.as_dict([Row()])  # type: ignore[list-item]
    assert business_profile.fact(profile, "what_they_do")["source"] == "page"
    assert business_profile.grounded(profile) == {}
