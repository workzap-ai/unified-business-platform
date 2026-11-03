# ruff: noqa: E501  (the owner's sentences stay on one line each)
"""Build packs/library/modern_ideas.json from docs/pi-saas/pi-modern-ideas.md (the owner's modern,
brand-free, owner-action ideas by problem kind), mapped to the library's categories.

    python scripts/build_modern_ideas.py

Each idea gets a stable id (modern:<kind>:<n>) so learning can score it. solution_library puts them
before the spec's own ideas of the same category when two fit equally; nothing is hidden."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs" / "pi-saas" / "pi-modern-ideas.md"
OUT = Path(__file__).resolve().parents[1] / "app" / "modules" / "pi" / "packs" / "library"

CATEGORY = {
    "sales_conversion": "sales_revenue",
    "attention_without_orders": "marketing_leads",
    "no_customers_yet": "marketing_leads",
    "repeat_customers": "customers_retention",
    "footfall_local_shop": "marketing_leads",
    "cash_and_stock_loss": "loss_security",
    "payments_late": "cash_collections",
    "orders_and_delivery": "orders_fulfilment",
    "staff_and_work": "people_staff",
    "bookings_and_no_shows": "customer_experience_digital",
}


def parse(text: str) -> list[dict[str, str]]:
    found = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|", 1)]
        if len(cells) != 2 or not cells[0] or cells[0].startswith(("Problem kind", "---")):
            continue
        kind = re.match(r"[a-z_]+", cells[0])
        if not kind or kind.group(0) not in CATEGORY:
            continue
        ideas = [i.strip().lstrip("•").strip() for i in cells[1].split("<br>")]
        for n, idea in enumerate((i for i in ideas if i), start=1):
            found.append(
                {
                    "id": f"modern:{kind.group(0)}:{n}",
                    "category": CATEGORY[kind.group(0)],
                    "text": idea,
                }
            )
    return found


# Owner-approved on 2026-10-26 (live test 6), not in the document: excess or slow stock to sell off
EXTRA = {
    "excess_stock": (
        "stock_inventory",
        [
            "Offer past buyers a first look at the unsold sets in a private chat with photos and one clear rate, so they get first pick.",
            "Show each ready set in a short video with the fabric close up, so viewers can judge it without asking.",
            "Display the slow sets at the front of the outlet with the most walk-ins, so more shoppers see them.",
            "Send a simple photo list of the sets to bulk buyers and nearby shops, so a large part of the stock can move in one deal.",
            "Group the unsold pieces into ready sets with one clear offer, so buyers see a simple choice.",
        ],
    )
}


def main() -> None:
    ideas = parse(SOURCE.read_text(encoding="utf-8"))
    for kind, (category, texts) in EXTRA.items():
        for n, text in enumerate(texts, start=1):
            ideas.append({"id": f"modern:{kind}:{n}", "category": category, "text": text})
    data = {
        "note": "Owner's modern, brand-free, owner-action ideas (docs/pi-saas/pi-modern-ideas.md), "
        "by library category. Preferred over the spec's older ideas when two fit equally.",
        "ideas": ideas,
    }
    (OUT / "modern_ideas.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(len(ideas), "ideas")


if __name__ == "__main__":
    main()
