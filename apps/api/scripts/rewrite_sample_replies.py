"""Rewrite the 211 sample solution replies (platform spec A2-FIX-4, Addendum 2 Part 1.9).

The sample replies seed the example bank, and pi copies what it is taught. As written, 210 of 211
end the build sentence on the same "automatically" line, every reply opens the same way, and some
carry tool words. This keeps each sample's own two ideas and the build clause it describes, and
rebuilds the rest:

* the opener differs for every industry in a sector (17 is the largest sector),
* the two ideas are told as plain "First, ... Second, ..." ("Pehle, ... Doosra, ..." in Roman
  Urdu), never as numbered dots,
* the Workzap lead-in no longer says "automatically" and rotates too,
* the offer line is the one pi itself uses, and it stays last.

Every rewritten reply is checked with `solution_rules.check_sample_reply`; a sample that cannot be
parsed or whose result fails is left as it was and listed. Nothing is invented.

    python scripts/rewrite_sample_replies.py [--apply]     (from apps/api, repo .venv)
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import solution_rules, solutions  # noqa: E402

DIR = solutions.SOLUTIONS_DIR

OPENERS = {
    "english": (
        (
            "Yes, this can be fixed",
            "Sure, this can be sorted",
            "Yes, there is a way through this",
            "Yes, this can be brought under control",
            "Sure, this is fixable",
            "Yes, this can be improved",
            "Yes, there are practical first steps",
            "Sure, you can start on this now",
        ),
        (
            ", and the first steps are simple.",
            ", and none of it needs special equipment.",
            ", and the first step is a small one.",
        ),
    ),
    "roman_urdu": (
        (
            "Ji haan, ye theek ho sakta hai",
            "Bilkul, is ka hal mumkin hai",
            "Haan, is par kaam ho sakta hai",
            "Ji, is ka rasta nikal sakta hai",
            "Zaroor, ye sambhal sakta hai",
            "Haan, is ko behtar kiya ja sakta hai",
            "Ji haan, shuruaat chhoti si ho sakti hai",
            "Bilkul, ye masla hal ho sakta hai",
        ),
        (
            ", aur pehla qadam aasan hai.",
            ", aur is ke liye bade kharch ki zaroorat nahi.",
            ", aur shuruaat chhoti si ho sakti hai.",
        ),
    ),
}
LEADS = {
    "english": (
        "Workzap could build this for you:",
        "For a lasting fix, Workzap could set up:",
        "Here is what Workzap would build:",
        "Workzap's part would be:",
        "To make it last, Workzap could put in place:",
        "Beyond these, Workzap could provide:",
        "What Workzap would add is:",
        "On top of this, Workzap could arrange:",
        "To make it stick, Workzap could build:",
        "Workzap could take it further with:",
        "The next step up would be:",
        "A lasting version would be:",
        "Workzap could make it permanent with:",
        "To keep it going, Workzap could set up:",
        "Workzap could then give you:",
        "A fuller fix would be:",
        "Workzap's build would be:",
    ),
    "roman_urdu": (
        "Workzap is ke liye ye bana sakta hai:",
        "Pakke hal ke liye Workzap ye banwa sakta hai:",
        "Workzap ye tayyar kar sakta hai:",
        "Lambay arse ke liye Workzap ye set kar sakta hai:",
        "Is mein Workzap ye shamil kar sakta hai:",
        "Workzap is tarah ka intezam kar sakta hai:",
        "Is ko mazboot karne ke liye Workzap ye de sakta hai:",
        "Workzap aap ke liye ye rakh sakta hai:",
        "Is ka pakka hal Workzap ye bana sakta hai:",
        "Workzap is se aage ye kar sakta hai:",
        "Workzap ye tarteeb de sakta hai:",
        "Is ke baad Workzap ye bana sakta hai:",
        "Workzap ye banwane mein madad kar sakta hai:",
        "Workzap ye sab ek jagah rakh sakta hai:",
        "Is ke liye Workzap ye intezam de sakta hai:",
        "Workzap ye tayyar karwa sakta hai:",
        "Workzap ka hissa ye hoga:",
    ),
}
GERUND_LEADS = (
    "Workzap could do this for you by",
    "Workzap would handle this by",
    "Workzap could take this on by",
    "Workzap could build it so that it is done by",
    "The lasting fix would work by",
    "Workzap could keep it going by",
    "Workzap could make it stick by",
    "Workzap could set this up by",
    "Workzap could cover this by",
    "Workzap could look after this by",
    "A lasting version would work by",
    "Workzap could carry it by",
    "Workzap could arrange this by",
    "Workzap could handle the rest by",
    "Workzap's part would be",
    "Workzap could do the rest by",
    "Workzap could finish the job by",
)
ORDINALS = {"english": ("First", "Second"), "roman_urdu": ("Pehle", "Doosra")}
OFFER_AT = re.compile(r"\s+(?=(?:Kya main|Would you like|Shall I)\b)")


def parse(pi: str) -> tuple[str, str, str, str] | None:
    """(idea 1, idea 2, build clause, offer) of a sample reply, or None."""
    offer_cut = OFFER_AT.search(pi)
    if not offer_cut:
        return None
    body, offer = pi[: offer_cut.start()].strip(), pi[offer_cut.end() :].strip()
    marks = re.split(r"\s*\b[12][.)]\s+", body)
    if len(marks) != 3:
        return None
    tail = re.search(r"\s+(Workzap.*)$", marks[2])
    if not tail:
        return None
    idea2 = marks[2][: tail.start()].strip()
    sentence = tail.group(1)
    if ":" in sentence:
        clause = sentence.split(":", 1)[1]
    else:
        cut = re.search(
            r"automatically(?: for you)?\s*(?:[:,]\s*|\s+(?:with|by|through|using)\s+)?"
            r"|khud[- ]?ba[- ]?khud kar sakta hai\s*[—–:-]?\s*",
            sentence,
        )
        if not cut:
            return None
        clause = sentence[cut.end() :]
    clause = clause.strip().rstrip(".")
    if not clause:
        return None
    return marks[1].strip(), idea2, clause, offer


# The few samples whose own words trip pi's checks (a tool word, a how-to marker, a contact-like
# word): the same meaning in plain words, per industry, so nothing is invented.
REPAIRS: dict[str, tuple[tuple[str, str], ...]] = {
    "freelancers_solopreneurs_and_home_based_businesses": (("Dono apps se", "Dono jagah se"),),
    "ground_handling_and_airport_services": (("step by step", "stage by stage"),),
    "ride_hailing_fleet_owners_and_taxi_operators": (
        ("platform payouts", "ride-hailing company payouts"),
    ),
    "cloud_kitchens_and_virtual_brands": (
        ("app's", "delivery partner's"),
        ("app statement", "delivery partner statement"),
        ("brand and app", "brand and delivery partner"),
    ),
    "fast_food_and_qsr_chains": (("one dashboard by", "one daily view by"),),
    "packaged_food_and_fmcg_brands": (
        ("a distributor portal where", "a shared form where"),
        ("a dashboard of stock", "a simple view of stock"),
    ),
    "restaurants": (("card aur app payments", "card aur online payments"),),
    "entertainment_centres_gaming_zones_and_play_areas": (
        ("your card system", "your card machine"),
    ),
    "fish_and_shrimp_farming": (("raat ka check-in system", "raat ka check-in record"),),
    "hatcheries": (("a booking system with", "a booking list with"),),
    "florists_and_gifting": (("a portal where", "a page where"),),
    "tiles_marble_and_bathroom_kitchen_showrooms": (
        ("because the system only tracks", "because the stock record only tracks"),
    ),
    "meat_shops_and_butchers": (("aate waqt aur phir boti", "aate waqt, aur boti"),),
    "banquet_halls_and_marquees": (("client WhatsApp pe count", "client message pe count"),),
}


def repaired(key: str, parts: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    out = list(parts)
    for old, new in REPAIRS.get(key, ()):
        out = [text.replace(old, new) for text in out]
    return (out[0], out[1], out[2], out[3])


def rebuild(language: str, index: int, parts: tuple[str, str, str, str]) -> str:
    idea1, idea2, clause, offer = parts
    lead_in, endings = OPENERS[language]
    opener = lead_in[index % len(lead_in)] + endings[(index // len(lead_in)) % len(endings)]
    first, second = ORDINALS[language]

    def sentence(ordinal: str, idea: str) -> str:
        idea = idea.strip().rstrip(".")
        return f"{ordinal}, {idea[:1].lower()}{idea[1:]}."

    lead = LEADS[language][index % len(LEADS[language])]
    if language == "english" and re.match(r"[A-Za-z]+ing", clause):
        lead = GERUND_LEADS[index % len(GERUND_LEADS)]
    return (
        f"{opener}\n{sentence(first, idea1)}\n{sentence(second, idea2)}\n"
        f"{lead} {clause[:1].lower()}{clause[1:]}.\n\n{offer}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    by_sector: dict[str, list[str]] = defaultdict(list)
    for key in solutions.industries():
        by_sector[solutions.load(key)["sector"]].append(key)  # type: ignore[index]
    done, left = 0, []
    for keys in by_sector.values():
        for index, key in enumerate(sorted(keys)):
            path = DIR / f"{key}.json"
            raw = path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw)
            sample = data["sample_reply"]
            language = sample.get("language")
            parts = parse(sample["pi"]) if language in OPENERS else None
            if not parts:
                left.append((key, "not parsed or not en/roman_urdu"))
                continue
            parts = repaired(key, parts)
            new = rebuild(language, index, parts)
            problems = solution_rules.check_sample_reply(new, sample["person"])
            if problems:
                left.append((key, "; ".join(problems)))
                continue
            sample["pi"] = new
            done += 1
            if args.apply:
                nl = "\r\n" if "\r\n" in raw else "\n"
                out = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", nl)
                path.write_text(
                    out + (nl if raw.endswith(nl) else ""), encoding="utf-8", newline=""
                )
    print(f"rewritten {done} of {sum(map(len, by_sector.values()))}; left {len(left)}")
    for key, why in left:
        print(" ", key, "-", why)


if __name__ == "__main__":
    main()
