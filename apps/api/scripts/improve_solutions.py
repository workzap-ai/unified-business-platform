# ruff: noqa: ASYNC240, E501  (an offline tool: small blocking file reads are fine)
"""Improve the industry solutions (Addendum 2, Part 4) with a generate, check and judge loop.

For every problem of every industry it asks a model for two NEW free ideas of different kinds (one
to measure the gap, one to fix the routine), checks each with pi's own idea guard
(`solution_rules.check_idea`), has a second model judge it, and gives the failures back with the
reasons for up to three rounds. Entries none of whose seed ideas passes the guard also get two
replacement ideas. Nothing in the seed is overwritten: the result goes to `extra_ideas` (tested on
a tenth of the chats, never replacing a seed idea) and, for the unusable ones, `quick_ideas` with
the original kept in `quick_ideas_original`.

    OPENAI_API_KEY=... python scripts/improve_solutions.py --out /tmp/improved [--only key,key] [--apply]

The key is read from the environment only. Run from apps/api.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import solution_rules, solutions  # noqa: E402

GEN_MODEL = os.environ.get("GEN_MODEL", "gpt-5.4")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-5.4-mini")
SOLUTIONS_DIR = Path(__file__).resolve().parents[1] / "app/modules/pi/packs/solutions"
INDUSTRY_DIR = Path(__file__).resolve().parents[1] / "app/modules/pi/packs/industry"
ROUNDS = 3
# Stock endings the first try repeated on almost every idea: at most twice in one industry.
STOCK = (
    "depend on memory",
    "depending on memory",
    "in heads",
    "in people's heads",
    "in people’s heads",
    "becomes visible",
    "become visible",
    "is visible",
    "gap shows",
    "gap becomes",
)

RULES = """You write FREE quick ideas that pi, a WhatsApp business assistant, may say to an owner of a
small or medium business in Pakistan, the UAE or Canada, before any paid work.
Each idea:
- is ONE plain sentence of 12 to 24 words: what to do, a comma, then "so" and why it helps;
- can be done THIS WEEK by the owner or staff with what they already have: a pen, the phone they own,
  a notebook, a chat group, a walk round the shop. Nothing to buy, install or set up;
- names no app, software, spreadsheet product, template, dashboard, tool, brand or vendor;
- contains no digits, no percentages, no amounts, no promised result, no guarantee;
- has no steps, no settings, no wording to copy, no "first, then";
- asks no question and asks for no names, phone numbers, ID or card details;
- gives no legal, medical, tax, financial or safety-critical advice;
- is about the owner's business routine, not about people's private lives.
Kind A (measure): count, compare, note or look at something once, so the owner sees the size of the gap.
Kind B (fix the routine): give one person the job, one place for the list, a fixed time, a handover, so it stops depending on memory.
The two ideas must differ from each other and from the existing ideas, and be specific to the
problem's own words, not generic. Vary the "so" part: say the concrete benefit in the owner's own
terms. Do not end ideas with "depending on memory", "in people's heads", "becomes visible" or
"the gap shows" (one idea in the whole answer may).
Answer with a JSON object only."""


async def chat(
    client: httpx.AsyncClient, model: str, system: str, user: str, key: str
) -> dict[str, Any]:
    for attempt in range(4):
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "max_completion_tokens": 6000,
                },
                timeout=240,
            )
            if response.status_code == 429 or response.status_code >= 500:
                await asyncio.sleep(3 * (attempt + 1))
                continue
            response.raise_for_status()
            return json.loads(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, json.JSONDecodeError, KeyError):
            await asyncio.sleep(2 * (attempt + 1))
    return {}


def guard(text: str, said: str) -> tuple[bool, list[str], bool]:
    """(passes, reasons it fails, needs a person) by pi's own idea guard."""
    verdict = solution_rules.check_idea(text, said)
    return (not verdict.reject, list(verdict.reject), bool(verdict.review))


def needs_replacement(industry: str, problem: dict[str, Any]) -> bool:
    ideas = solutions.ideas(industry, problem)
    return not any(solution_rules.check_idea(i.text).ok for i in ideas if not i.extra)


async def improve_industry(
    client: httpx.AsyncClient, key: str, industry: str, sem: asyncio.Semaphore
) -> dict[str, Any]:
    seed = solutions.load(industry) or {}
    pack = json.loads((INDUSTRY_DIR / f"{industry}.json").read_text(encoding="utf-8"))
    problems = {p["id"]: p for p in seed.get("problems", [])}
    replace_ids = {pid for pid, p in problems.items() if needs_replacement(industry, p)}
    accepted: dict[str, list[dict[str, Any]]] = {}
    replaced: dict[str, list[str]] = {}
    notes: dict[str, list[str]] = {pid: [] for pid in problems}
    pending = set(problems)
    log: list[str] = []
    stock_used: dict[str, int] = {}
    for round_no in range(1, ROUNDS + 1):
        if not pending:
            break
        ask = [
            {
                "id": pid,
                "owner_says": problems[pid]["words"],
                "category": f"{problems[pid]['category']}/{problems[pid]['subtype']}",
                "existing_ideas": [
                    i.text for i in solutions.ideas(industry, problems[pid]) if not i.extra
                ],
                "replace_the_existing_ideas": pid in replace_ids,
                "fix_these_problems_from_the_last_try": notes[pid][-4:],
            }
            for pid in sorted(pending)
        ]
        user = json.dumps(
            {
                "industry": seed.get("name"),
                "never_say_in_this_industry": seed.get("never_say", []),
                "care_notes": pack.get("care", [])[:6],
                "problems": ask,
                "answer_as": {"problems": [{"id": "...", "ideas": ["kind A idea", "kind B idea"]}]},
            },
            ensure_ascii=False,
        )
        async with sem:
            out = await chat(client, GEN_MODEL, RULES, user, key)
        candidates: dict[str, list[str]] = {}
        for item in out.get("problems") or []:
            pid = str(item.get("id"))
            if pid in pending:
                candidates[pid] = [str(t).strip() for t in (item.get("ideas") or [])][:2]
        judged_input = []
        verdicts: dict[str, list[tuple[bool, list[str], bool]]] = {}
        for pid, texts in candidates.items():
            verdicts[pid] = [guard(t, problems[pid]["words"]) for t in texts]
            judged_input.append(
                {
                    "id": pid,
                    "owner_says": problems[pid]["words"],
                    "existing_ideas": [
                        i.text for i in solutions.ideas(industry, problems[pid]) if not i.extra
                    ],
                    "candidates": texts,
                }
            )
        async with sem:
            scored = (
                await chat(
                    client,
                    JUDGE_MODEL,
                    "You are a strict reviewer of free business ideas. Score each candidate 1 to 5 "
                    "on: specific (to this owner's problem, not generic), doable (this week, with "
                    "what they have), plain (an owner understands it at once), safe (no advice on "
                    "law, medicine, tax, money or safety; no invented claim). Give one line of "
                    "reason when any score is below 4. Answer with a JSON object only, shaped as "
                    '{"scores":[{"id":"...","items":[{"specific":5,"doable":5,"plain":5,"safe":5,'
                    '"reason":""}]}]}',
                    json.dumps(judged_input, ensure_ascii=False),
                    key,
                )
                if judged_input
                else {}
            )
        by_id = {str(s.get("id")): s.get("items") or [] for s in scored.get("scores") or []}
        for pid, texts in candidates.items():
            good: list[dict[str, Any]] = []
            for n, text in enumerate(texts):
                passes, reasons, review = verdicts[pid][n]
                score = (by_id.get(pid) or [{}] * 2)[n] if n < len(by_id.get(pid) or []) else {}
                ok_judge = (
                    bool(score)
                    and all(int(score.get(f, 0)) >= 4 for f in ("specific", "doable", "plain"))
                    and int(score.get("safe", 0)) >= 5
                )
                low = text.lower()
                overused = [p for p in STOCK if p in low and stock_used.get(p, 0) >= 2]
                if overused:
                    notes[pid].append(
                        f'"{text}": the ending "{overused[0]}" is overused in this industry: say the benefit another way'
                    )
                    continue
                if passes and ok_judge:
                    good.append({"text": text.rstrip(". ") + ".", "review": review})
                    for phrase in STOCK:
                        if phrase in low:
                            stock_used[phrase] = stock_used.get(phrase, 0) + 1
                else:
                    why = reasons or [str(score.get("reason") or "judge: too generic or unsafe")]
                    notes[pid].append(f'"{text}": {"; ".join(why)}')
            if len(good) == 2 and len({g["text"] for g in good}) == 2:
                if pid in replace_ids:
                    replaced[pid] = [g["text"] for g in good if not g["review"]]
                    if len(replaced[pid]) < 2:
                        replaced.pop(pid)
                        continue
                else:
                    accepted[pid] = good
                pending.discard(pid)
        log.append(f"round {round_no}: {len(problems) - len(pending)}/{len(problems)} done")
    return {
        "industry": industry,
        "extra": accepted,
        "replaced": replaced,
        "unresolved": sorted(pending),
        "notes": {pid: n[-2:] for pid, n in notes.items() if pid in pending},
        "log": log,
    }


def apply(out_dir: Path) -> None:
    """Write the accepted ideas into the solution files (extra_ideas, replaced quick_ideas)."""
    changed = 0
    for result_file in sorted(out_dir.glob("*.json")):
        result = json.loads(result_file.read_text(encoding="utf-8"))
        path = SOLUTIONS_DIR / f"{result['industry']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for problem in data["problems"]:
            pid = problem["id"]
            if pid in result["extra"] and not problem.get("extra_ideas"):
                problem["extra_ideas"] = result["extra"][pid]
                changed += 1
            if pid in result["replaced"] and "quick_ideas_original" not in problem:
                problem["quick_ideas_original"] = problem["quick_ideas"]
                problem["quick_ideas"] = result["replaced"][pid]
                changed += 1
        data["version"] = "1.1"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("entries changed:", changed)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.apply:
        apply(out_dir)
        return
    key = os.environ["OPENAI_API_KEY"]
    keys = [k for k in args.only.split(",") if k] or list(solutions.industries())
    sem = asyncio.Semaphore(args.workers)
    async with httpx.AsyncClient() as client:

        async def one(industry: str) -> None:
            target = out_dir / f"{industry}.json"
            if target.exists():
                return
            result = await improve_industry(client, key, industry, sem)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            print(
                industry[:44].ljust(44), result["log"][-1], "unresolved", len(result["unresolved"])
            )

        await asyncio.gather(*(one(k) for k in keys))


if __name__ == "__main__":
    asyncio.run(main())
