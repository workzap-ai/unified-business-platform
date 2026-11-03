import json
import re
from collections import Counter
from pathlib import Path

from app.modules.pi import currency_notes as cn
from app.modules.pi.solutions import TOOL_WORD

INDUSTRY_DIR = Path(cn.__file__).parent / "packs" / "industry"
MONEY = re.compile(
    r"(?:[$€£]|\b(?:rs|pkr|aed|cad|usd|dirhams?|rupees?|dollars?)\b)\s*\d|\d\s*(?:%|percent\b)",
    re.IGNORECASE,
)


def _industry_ids() -> set[str]:
    ids = set()
    for path in INDUSTRY_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") == "industry":
            ids.add(data["key"])
    return ids


def _files() -> list[Path]:
    return sorted(cn.CURRENCY_DIR.glob("*.json"))


def test_every_industry_covered_exactly_once() -> None:
    counts: Counter[str] = Counter()
    for path in _files():
        counts.update(json.loads(path.read_text(encoding="utf-8"))["industries"])
    ids = _industry_ids()
    assert len(ids) == 211
    assert set(counts) == ids
    assert [k for k, n in counts.items() if n != 1] == []


def test_files_valid_and_dated() -> None:
    assert _files()
    for path in _files():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert cn.validate(data) == [], path.name
        assert data["cluster"] == path.stem
        assert data["as_of"] == "2026-10"
        assert data["review_status"] == "needs human review"
        assert 3 <= len(data["how_customers_find_and_choose"]) <= 6
        assert 5 <= len(data["what_works_now"]) <= 8
        assert 4 <= len(data["outdated_or_weak"]) <= 8


def test_no_amounts_or_tool_words() -> None:
    for path in _files():
        data = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(data, ensure_ascii=False)
        assert not MONEY.search(text), path.name
        for line in data["what_works_now"]:
            assert not TOOL_WORD.search(line), (path.name, line)
            assert not re.search(r"\d", line), (path.name, line)


def test_block_length_bounded() -> None:
    for key in _industry_ids():
        block = cn.prompt_block(key)
        assert block, key
        assert len(block) <= 1800
        assert len(cn.prompt_block(key, max_chars=500)) <= 500


def test_unknown_industry_is_empty() -> None:
    assert cn.for_industry("no_such_industry") is None
    assert cn.prompt_block("no_such_industry") == ""
    assert cn.prompt_block("") == ""


def test_validate_flags_gaps() -> None:
    assert cn.validate({}) != []
