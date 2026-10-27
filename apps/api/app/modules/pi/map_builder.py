"""Building the problem map from a customer's noted problems (pi platform spec Book 5, 4.2 to 4.4).

`build_map` is pure: problem rows and link rows in, the dict that `map_render.render_map` draws out.
`save_if_changed` stores a new `pi_map_versions` row only when the content changed, so the version
number means "something the owner would see is different". `share_due` is the rule of 4.4 for when
pi may send the map in the chat.

What goes on the map: the owner's own words (title_local, then the first of user_words, then the
English title), no names, no personal data (redacted), numbers only from what the owner said about
that problem (amount, time, since when, how often, how many), links that have evidence. Resolved
problems stay, greyed; parked ones stay too. Withdrawn and merged problems are not drawn.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import box_signals, taxonomy
from app.modules.pi import problems as problem_book
from app.modules.pi.box_models import PiMapVersion
from app.modules.pi.problem_models import PiProblem, PiProblemLink
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

MAX_LABEL_WORDS = 6
MAX_FACTS = 3
LINK_MIN = Decimal("0.5")  # a pi_inferred link under this confidence is not drawn
PARKED_TAG = "parked"
# Statuses drawn on the map: everything in play, plus resolved (greyed, part of the story).
DRAWN = (*taxonomy.ACTIVE, "resolved")
# Link types the map knows (spec 4.2); the older suspicion type is a dashed same_root.
_TYPE_OF = {
    "causes": "causes",
    "worsens": "worsens",
    "blocks": "blocks",
    "competes": "competes",
    "same_root": "same_root",
    "symptom_of": "symptom_of",
    "same_root_suspected": "same_root",
}
_CAUSAL = ("causes", "blocks")

# Share rule numbers (spec 4.4).
FIRST_MIN_NODES = 3
FIRST_MIN_NODES_WITH_LINK = 2
UPDATE_NEW_NODES = 2
MIN_MESSAGES_BETWEEN_SHARES = 6  # at most one share per six pi messages


def share_enabled(response_rules: dict[str, Any] | None) -> bool:
    """Sharing the map in the chat is on only in brain mode with response_rules.brain.map_share
    exactly true (default off)."""
    rules = response_rules or {}
    return rules.get("pi_mode") == "brain" and (rules.get("brain") or {}).get("map_share") is True


def node_id(number: int) -> str:
    return f"P{number}"


def _words(text: str, limit: int) -> str:
    cleaned, _ = problem_book.redact(" ".join((text or "").replace("“", "").split()))
    parts = cleaned.strip(" \"'“”‘’,;:-").split()
    return " ".join(parts[:limit])


def label_of(problem: Any) -> str:
    """The owner's own words, shortened; the English title only when there is nothing else."""
    candidates = [problem.title_local, *(problem.user_words or [])[:1], problem.title]
    for raw in candidates:
        value = _words(str(raw or ""), MAX_LABEL_WORDS)
        if value:
            return value
    return "?"


def facts_of(problem: Any) -> list[str]:
    """What the owner said about it (amount, time, since when, how often, how many)."""
    impact = problem.impact or {}
    raw = [
        impact.get("money_text"),
        impact.get("time_text"),
        (problem.since or {}).get("text"),
        (problem.frequency or {}).get("text"),
        (problem.scope or {}).get("of_total"),
    ]
    out: list[str] = []
    for value in raw:
        text = _words(str(value or ""), 10)
        if text and text not in out:
            out.append(text)
    return out[:MAX_FACTS]


def _type(link: Any) -> str | None:
    return _TYPE_OF.get(str(link.type))


def _evidence(link: Any) -> str:
    if str(link.status) == "confirmed" or str(link.evidence) == "confirmed":
        return "confirmed"
    return "owner_said" if str(link.evidence) == "owner_said" else "pi_inferred"


def _drawn_link(link: Any, number: dict[Any, int], link_min: Decimal) -> dict[str, Any] | None:
    kind = _type(link)
    if kind is None or str(link.status) == "rejected":
        return None
    a, b = number.get(link.from_id), number.get(link.to_id)
    if a is None or b is None or a == b:
        return None
    evidence = _evidence(link)
    if evidence == "pi_inferred" and Decimal(str(link.confidence)) < link_min:
        return None
    return {"from": node_id(a), "to": node_id(b), "type": kind, "label": "", "evidence": evidence}


def clusters_of(nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups of nodes tied together by links. The root is the node with the most outgoing
    causes or blocks (a symptom_of link points at its cause); ties go to the lower number."""
    ids = [n["id"] for n in nodes]
    parent = {i: i for i in ids}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for link in links:
        parent[find(link["from"])] = find(link["to"])
    members: dict[str, list[str]] = {}
    for i in ids:
        members.setdefault(find(i), []).append(i)
    outgoing = dict.fromkeys(ids, 0)
    for link in links:
        if link["type"] in _CAUSAL:
            outgoing[link["from"]] += 1
        elif link["type"] == "symptom_of":
            outgoing[link["to"]] += 1
    label = {n["id"]: n["label"] for n in nodes}
    out: list[dict[str, Any]] = []
    for group in members.values():
        if len(group) < 2:
            continue
        root = min(group, key=lambda i: (-outgoing[i], ids.index(i)))
        out.append({"id": f"c{root}", "title": label[root], "node_ids": group, "root": root})
    out.sort(key=lambda c: ids.index(c["root"]))
    return out


def content_hash(map_: dict[str, Any]) -> str:
    """Hash of what the owner sees, apart from the version number, the 'new' tags (they depend on
    the version before) and the hash itself."""
    core = {
        "nodes": [{k: v for k, v in n.items() if k != "is_new"} for n in map_.get("nodes") or []],
        "links": map_.get("links") or [],
        "clusters": map_.get("clusters") or [],
    }
    body = json.dumps(core, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def build_map(
    problems: list[Any],
    links: list[Any],
    *,
    version: int = 1,
    previous: dict[str, Any] | None = None,
    link_min: Decimal = LINK_MIN,
) -> dict[str, Any]:
    """The map dict for `map_render.render_map`, plus `hash` (see `content_hash`). `previous` is
    the map of the version before: a problem not in it is new."""
    rows = sorted(
        (p for p in problems if str(p.status) in DRAWN and p.merged_into is None),
        key=lambda p: p.number,
    )
    before = {n["id"] for n in (previous or {}).get("nodes") or []}
    nodes: list[dict[str, Any]] = []
    number: dict[Any, int] = {}
    for p in rows:
        number[p.id] = p.number
        status = "resolved" if str(p.status) == "resolved" else "open"
        if status == "open" and PARKED_TAG in (p.tags or []):
            status = "parked"
        node: dict[str, Any] = {
            "id": node_id(p.number),
            "label": label_of(p),
            "facts": facts_of(p),
            "category": p.category if p.category in taxonomy.KEYS else taxonomy.OTHER,
            "status": status,
            "is_new": previous is not None and node_id(p.number) not in before,
        }
        if (rank := box_signals.rank_of(p.tags)) is not None:
            node["rank"] = rank  # the owner's own order (B4), shown on the page, only when set
        nodes.append(node)
    drawn: list[dict[str, Any]] = []
    for link in links:
        item = _drawn_link(link, number, link_min)
        if item is not None and item not in drawn:
            drawn.append(item)
    out: dict[str, Any] = {
        "version": version,
        "nodes": nodes,
        "links": drawn,
        "clusters": clusters_of(nodes, drawn),
    }
    out["hash"] = content_hash(out)
    return out


# --- the database ------------------------------------------------------------------------------


async def current_inputs(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> tuple[list[PiProblem], list[PiProblemLink]]:
    """This customer's problems and the links between them, nothing from anyone else."""
    problems = list(
        await session.scalars(
            WorkspaceRepository(session, PiProblem, scope)
            .select()
            .where(PiProblem.customer_id == customer_id, PiProblem.status.in_(DRAWN))
            .order_by(PiProblem.number)
        )
    )
    ids = [p.id for p in problems]
    if not ids:
        return [], []
    links = list(
        await session.scalars(
            WorkspaceRepository(session, PiProblemLink, scope)
            .select()
            .where(PiProblemLink.from_id.in_(ids), PiProblemLink.to_id.in_(ids))
            .order_by(PiProblemLink.created_at)
        )
    )
    return problems, links


async def latest_version(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> PiMapVersion | None:
    found: PiMapVersion | None = await session.scalar(
        WorkspaceRepository(session, PiMapVersion, scope)
        .select()
        .where(PiMapVersion.customer_id == customer_id)
        .order_by(PiMapVersion.version.desc())
        .limit(1)
    )
    return found


async def save_if_changed(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    link_min: Decimal = LINK_MIN,
) -> tuple[PiMapVersion | None, bool]:
    """Build the map now; store a new version only when it differs from the latest one.

    Returns (the latest version, whether a new one was stored). (None, False) while the customer
    has nothing to draw. Does not commit; the caller's unit of work does."""
    problems, links = await current_inputs(session, scope, customer_id)
    latest = await latest_version(session, scope, customer_id)
    previous = dict(latest.map_json) if latest is not None else None
    fresh = build_map(
        problems,
        links,
        version=(latest.version + 1) if latest else 1,
        previous=previous,
        link_min=link_min,
    )
    if not fresh["nodes"]:
        return latest, False
    if latest is not None and (latest.map_json or {}).get("hash") == fresh["hash"]:
        return latest, False
    row = PiMapVersion(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        version=fresh["version"],
        map_json=fresh,
    )
    session.add(row)
    await session.flush()
    return row, True


async def last_shared(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> PiMapVersion | None:
    found: PiMapVersion | None = await session.scalar(
        WorkspaceRepository(session, PiMapVersion, scope)
        .select()
        .where(PiMapVersion.customer_id == customer_id, PiMapVersion.shared_at.is_not(None))
        .order_by(PiMapVersion.version.desc())
        .limit(1)
    )
    return found


async def versions(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> list[PiMapVersion]:
    return list(
        await session.scalars(
            select(PiMapVersion)
            .where(
                PiMapVersion.tenant_id == scope.tenant_id,
                PiMapVersion.environment_id == scope.environment_id,
                PiMapVersion.customer_id == customer_id,
            )
            .order_by(PiMapVersion.version)
        )
    )


# --- when pi shares the map (spec 4.4) ---------------------------------------------------------


def new_since(shared: dict[str, Any] | None, latest: dict[str, Any]) -> tuple[int, bool]:
    """(how many problems are new since the shared version, whether a new problem has a link)."""
    seen = {n["id"] for n in (shared or {}).get("nodes") or []}
    fresh = {n["id"] for n in latest.get("nodes") or [] if n["id"] not in seen}
    linked = any(link["from"] in fresh or link["to"] in fresh for link in latest.get("links") or [])
    return len(fresh), linked


@dataclass(frozen=True)
class ShareFacts:
    nodes: int = 0
    links: int = 0
    ever_shared: bool = False
    new_nodes: int = 0  # since the last shared version
    new_node_linked: bool = False  # one of them has a link
    pi_messages_since_share: int | None = None  # None: never shared
    hurried: bool = False
    openness: int = 1  # 0 is closed (spec 2)
    asked: bool = False  # "naqsha dikhao"
    at_offer: bool = False  # the set check-in before the Solution Box offer


def share_due(facts: ShareFacts) -> tuple[bool, str]:
    """(share, why). Spec 4.4: the first map at 3 problems, or 2 with a link, if the owner is not
    hurried and openness is not 0; an update at a new problem with a link or two new problems;
    never more than one share per six pi messages unless asked; a hurried owner gets it only when
    they ask or at the offer."""
    if facts.nodes < 1:
        return False, "empty"
    if facts.asked:
        return True, "asked"
    if facts.at_offer:
        return True, "offer"
    if facts.hurried:
        return False, "hurried"
    since = facts.pi_messages_since_share
    if since is not None and since < MIN_MESSAGES_BETWEEN_SHARES:
        return False, "limit"
    if not facts.ever_shared:
        if facts.openness <= 0:
            return False, "closed"
        enough = facts.nodes >= FIRST_MIN_NODES or (
            facts.nodes >= FIRST_MIN_NODES_WITH_LINK and facts.links >= 1
        )
        return (True, "first") if enough else (False, "not_enough")
    if facts.new_nodes >= UPDATE_NEW_NODES or (facts.new_nodes >= 1 and facts.new_node_linked):
        return True, "update"
    return False, "no_change"
