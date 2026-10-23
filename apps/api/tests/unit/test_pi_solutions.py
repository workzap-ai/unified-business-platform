"""Industry solutions (Addendum 2, Parts 1.9, 2 and 4): the packs parsed from the addendum."""

import json
import re

import pytest

from app.modules.pi import industry_packs, solutions, taxonomy
from app.modules.pi.solutions import (
    ACTION_BUILDS,
    CATALOGUE,
    VIEW_BUILDS,
    banned_tool_words,
    build_phrase,
    ideas,
    load,
)

MONEY = re.compile(r"\d\s*(?:%|percent)|\b(?:rs\.?|pkr|aed|usd)\s*\d|[$₨]\s*\d", re.IGNORECASE)
INDUSTRIES = solutions.industries()


def test_every_industry_has_solutions_linked_to_its_pack():
    assert len(INDUSTRIES) == 211
    packs = {p.stem for p in industry_packs.PACKS_DIR.glob("*.json")}
    assert set(INDUSTRIES) <= packs


@pytest.mark.parametrize("key", INDUSTRIES)
def test_each_entry_is_complete_and_inside_the_value_line(key):
    data = load(key)
    assert data and data["version"] == "1.0" and data["industry"] == key
    assert data["problems"] and data["never_say"]
    assert data["sample_reply"]["person"] and data["sample_reply"]["pi"]
    seen = set()
    for problem in data["problems"]:
        assert problem["id"] not in seen
        seen.add(problem["id"])
        assert problem["category"] in taxonomy.BY_KEY
        assert len(problem["quick_ideas"]) == 2  # RVAL01: exactly two
        assert problem["workzap_build"]["keys"]
        assert set(problem["workzap_build"]["keys"]) <= set(CATALOGUE)
        assert problem["free_stops"] and problem["words"]
        blob = " ".join([*problem["quick_ideas"], problem["workzap_build"]["text"]])
        assert not MONEY.search(blob), (key, problem["id"])


def test_a_view_build_leads_only_for_visibility_problems_when_an_action_is_listed():
    for key in INDUSTRIES:
        for problem in load(key)["problems"]:
            keys = problem["workzap_build"]["keys"]
            if problem["category"] != "reporting_visibility" and keys[0] in VIEW_BUILDS:
                assert all(k in VIEW_BUILDS for k in keys), (key, problem["id"], keys)


def test_the_catalogue_splits_into_views_and_actions():
    assert VIEW_BUILDS == {"dashboards_reports", "nori_daily_read"}
    assert ACTION_BUILDS.isdisjoint(VIEW_BUILDS)
    assert {"stock_alerts", "attribution_codes", "customer_messaging"} <= ACTION_BUILDS
    assert "Roman" not in build_phrase("stock_alerts", "en")
    assert build_phrase("stock_alerts", "roman_ur").startswith("Jis din best-seller")
    assert build_phrase("not_a_build") == build_phrase("custom_build")


def test_tool_words_are_banned_unless_the_person_said_them_first():
    assert banned_tool_words("Workzap can build a dashboard for every shop") == ["dashboard"]
    assert banned_tool_words("a system and a portal, plus an app") == ["system", "portal", "app"]
    assert banned_tool_words("a dashboard for me", said="I want a dashboard") == []
    assert banned_tool_words("har subah aap ke WhatsApp par message aa jaye") == []
    assert banned_tool_words("apply and happen", said="") == []  # words inside other words


def test_each_quick_idea_is_an_arm_with_a_stable_id():
    problem = load("retail_shops_and_chains")["problems"][0]
    arms = ideas("retail_shops_and_chains", problem)
    assert [a.arm_id for a in arms] == [
        f"retail_shops_and_chains:{problem['id']}:q1",
        f"retail_shops_and_chains:{problem['id']}:q2",
    ]
    assert load("../etc/passwd") is None
    assert load("no_such_industry") is None


def test_the_pack_files_are_valid_utf8_json_with_the_expected_keys():
    for path in solutions.SOLUTIONS_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert {
            "industry",
            "name",
            "sector",
            "version",
            "problems",
            "never_say",
            "sample_reply",
        } <= set(data)
