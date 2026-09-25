"""Specialist agents (support, customer/memory, requirement, sales/order, handoff).

Each specialist is a LangGraph node that acts only through the ToolRegistry and composes
replies exclusively from tool results. Specialists may transfer to one another; transfers
are bounded by MAX_AGENT_TRANSFERS, after which the conversation goes to a person.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.graph import RouteState
from app.modules.pi.knowledge import remember
from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage, PiSettings
from app.modules.pi.tools.base import ToolResult
from app.modules.pi.tools.confirmation import issue
from app.modules.pi.tools.registry import ToolRegistry
from app.modules.sales.service import SalesService
from app.shared.errors import BusinessRuleViolation, PermissionDenied
from app.shared.scope import WorkspaceScope

MAX_AGENT_TRANSFERS = 3
SPECIALISTS = ("support", "customer_memory", "requirement", "sales_order", "handoff")


class AgentState(TypedDict):
    agent: str
    path: list[str]
    transfers: int
    transfer_to: str | None
    reply: str | None
    handoff_reason: str | None
    lead: bool


@dataclass
class AgentContext:
    session: AsyncSession
    scope: WorkspaceScope
    conversation: PiConversation
    message: PiMessage
    run: PiAgentRun
    policy: PiSettings
    decision: RouteState
    registry: ToolRegistry
    extra_passages: list[dict[str, str]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    tool_failures: int = 0

    async def tool(
        self, agent: str, name: str, args: dict[str, Any], confirmation: str | None = None
    ) -> ToolResult:
        result = await self.registry.execute(
            self.scope,
            self.conversation,
            name,
            args,
            confirmation,
            run=self.run,
            agent_key=agent,
        )
        if result.ok and result.data is not None:
            self.facts.append(json.dumps(result.data, default=str))
        elif result.status in {"error", "denied"}:
            self.tool_failures += 1
        return result


def _transfer(state: AgentState, target: str, **extra: Any) -> dict[str, Any]:
    return {"transfer_to": target, "transfers": state["transfers"] + 1, **extra}


def _quantity(text: str) -> int:
    match = re.search(r"(?<![\w-])(\d{1,4})(?![\w.-])", text)
    return max(1, min(int(match.group(1)), 10_000)) if match else 1


def build_graph(ctx: AgentContext) -> Any:
    body = ctx.message.body
    intent = ctx.decision["intent"]

    def entering(state: AgentState, name: str) -> dict[str, Any]:
        return {"agent": name, "path": [*state["path"], name], "transfer_to": None}

    async def support(state: AgentState) -> dict[str, Any]:
        update = entering(state, "support")
        if intent == "greeting":
            greeting = str(ctx.policy.response_rules.get("greeting") or "Hello! How can we help?")
            ctx.facts.append(greeting)
            return {**update, "reply": greeting}
        found = await ctx.tool(
            "support",
            "search_knowledge_base",
            {"query": body[:500], "limit": int(ctx.policy.knowledge_config.get("top_k", 5))},
        )
        passages = list((found.data or {}).get("passages", [])) + ctx.extra_passages
        if not passages:
            return {**update, **_transfer(state, "handoff", handoff_reason="low_confidence")}
        snippet = str(passages[0]["snippet"])[:3000]
        ctx.facts.append(snippet)
        return {**update, "reply": "From our approved information:\n" + snippet}

    async def customer_memory(state: AgentState) -> dict[str, Any]:
        update = entering(state, "customer_memory")
        await ctx.tool("customer_memory", "search_customer_memory", {"limit": 10})
        if intent == "invoice":
            balance = await ctx.tool("customer_memory", "get_customer_balance", {})
            if not balance.ok or balance.data is None:
                return {**update, **_transfer(state, "handoff", handoff_reason="tool_failure")}
            reply = f"Your open balance is {balance.data['balance']} {balance.data['currency']}."
            if balance.data["balance"] != "0.00":
                reply += " A team member can share invoice copies if you need them."
            return {**update, "reply": reply}
        orders = await ctx.tool("customer_memory", "get_customer_orders", {"limit": 3})
        if not orders.ok or orders.data is None:
            return {**update, **_transfer(state, "handoff", handoff_reason="tool_failure")}
        rows = orders.data["orders"]
        mentioned = [o for o in rows if o["number"].casefold() in body.casefold()]
        rows = mentioned or rows
        if not rows:
            return {
                **update,
                "reply": "We couldn't find an order for this WhatsApp number. "
                "A team member can check with your order reference.",
            }
        lines = [f"Order {o['number']}: {o['status']} ({o['total']} {o['currency']})" for o in rows]
        return {**update, "reply": "\n".join(lines)}

    async def requirement(state: AgentState) -> dict[str, Any]:
        update = entering(state, "requirement")
        try:
            await remember(
                ctx.session, ctx.scope, ctx.conversation.customer_id, body, ctx.message.id
            )
            await SalesService(ctx.session, ctx.scope).upsert_requirement(
                ctx.conversation.customer_id,
                ctx.conversation.id,
                body[:200],
                {"request": body},
                ["scope", "budget", "target_date"],
            )
        except (PermissionDenied, BusinessRuleViolation):
            return {**update, **_transfer(state, "handoff", handoff_reason="tool_failure")}
        return {**update, **_transfer(state, "sales_order", lead=True)}

    async def sales_order(state: AgentState) -> dict[str, Any]:
        update = entering(state, "sales_order")
        found = await ctx.tool("sales_order", "search_products", {"query": body[:200]})
        if not found.ok or found.data is None:
            return {**update, **_transfer(state, "handoff", handoff_reason="tool_failure")}
        products = found.data["products"]
        products = [p for p in products if p["variants"]]
        if not products:
            return {
                **update,
                "reply": "Please describe the item or service you need. "
                "A team member can confirm pricing and availability.",
            }
        options = [(p, p["variants"][0]) for p in products[:3]]
        listing = "\n".join(
            f"{p['name']} — {v['name']}: {v['price']} {v['currency']}" for p, v in options
        )
        if intent == "product_availability":
            tracked = [v["id"] for p in products[:3] for v in p["variants"][:3] if v["tracked"]]
            levels: dict[str, Any] = {}
            if tracked:
                stock = await ctx.tool("sales_order", "check_inventory", {"variant_ids": tracked})
                if not stock.ok or stock.data is None:
                    return {**update, **_transfer(state, "handoff", handoff_reason="tool_failure")}
                levels = {str(x["variant_id"]): x for x in stock.data["items"]}
            lines = []
            for p in products[:3]:
                for v in p["variants"][:3]:
                    level = levels.get(str(v["id"]))
                    lines.append(
                        f"{p['name']} — {v['name']}: {level['available']} available"
                        if level and level["tracked"]
                        else f"{p['name']} — {v['name']}: not stock-tracked; "
                        "the team confirms availability"
                    )
            return {**update, "reply": "\n".join(lines)}
        if intent == "order":
            chosen = [
                (p, v)
                for p in products
                for v in p["variants"]
                if len(products) == 1
                and (
                    len(p["variants"]) == 1
                    or v["sku"].casefold() in body.casefold()
                    or v["name"].casefold() in body.casefold()
                )
            ]
            if len(chosen) != 1:
                return {
                    **update,
                    "reply": "Available options:\n"
                    + listing
                    + "\nPlease tell us exactly which option you want to order.",
                }
            product, variant = chosen[0]
            quantity = _quantity(body.replace(variant["sku"], ""))
            if variant["tracked"]:
                stock = await ctx.tool(
                    "sales_order", "check_inventory", {"variant_ids": [variant["id"]]}
                )
                if not stock.ok or stock.data is None or not stock.data["items"]:
                    return {**update, **_transfer(state, "handoff", handoff_reason="tool_failure")}
                available = stock.data["items"][0]["available"]
                if available is not None and available < quantity:
                    return {
                        **update,
                        "reply": f"{product['name']} — {variant['name']}: {available} available. "
                        "Please choose a smaller quantity or ask for a team member.",
                    }
            draft_lines = [{"variant_id": variant["id"], "quantity": quantity}]
            draft = await ctx.tool("sales_order", "create_order_draft", {"lines": draft_lines})
            if not draft.ok or draft.data is None:
                return {**update, **_transfer(state, "handoff", handoff_reason="tool_failure")}
            pending, _token = await issue(ctx.session, ctx.scope, ctx.conversation, draft.data)
            ctx.facts.append(pending.summary)
            return {
                **update,
                "reply": pending.summary
                + f"\nTo place this order, reply exactly CONFIRM {draft.data['number']}. "
                "Reply CANCEL to discard it.",
            }
        reply = "Available offerings:\n" + listing
        if intent == "quote":
            quote = await ctx.tool(
                "sales_order",
                "create_quote_draft",
                {"lines": [{"variant_id": v["id"], "quantity": 1} for _, v in options]},
            )
            if quote.ok and quote.data is not None:
                reply += (
                    f"\nDraft {quote.data['number']} is ready for team review. "
                    "Scope and delivery are not confirmed."
                )
        if state["lead"]:
            reply += "\nWhat scope, budget and target date should the team consider?"
        return {**update, "reply": reply}

    async def handoff(state: AgentState) -> dict[str, Any]:
        update = entering(state, "handoff")
        reason = state["handoff_reason"] or "low_confidence"
        if state["transfers"] > MAX_AGENT_TRANSFERS:
            reason = "policy"
        return {**update, "reply": None, "handoff_reason": reason}

    def after(state: AgentState) -> str:
        target = state["transfer_to"]
        if target is None:
            return END
        if state["transfers"] > MAX_AGENT_TRANSFERS or target not in SPECIALISTS:
            return "handoff"
        return target

    graph = StateGraph(AgentState)
    for name, node in (
        ("support", support),
        ("customer_memory", customer_memory),
        ("requirement", requirement),
        ("sales_order", sales_order),
        ("handoff", handoff),
    ):
        graph.add_node(name, node)
        if name != "handoff":
            graph.add_conditional_edges(name, after)
    graph.add_conditional_edges(
        START, lambda s: s["agent"] if s["agent"] in SPECIALISTS else "handoff"
    )
    graph.add_edge("handoff", END)
    return graph.compile()


async def run_specialists(ctx: AgentContext, first: str, reason: str | None) -> AgentState:
    graph = build_graph(ctx)
    result = await graph.ainvoke(
        {
            "agent": first,
            "path": [],
            "transfers": 0,
            "transfer_to": None,
            "reply": None,
            "handoff_reason": reason,
            "lead": False,
        },
        {"recursion_limit": 2 * (MAX_AGENT_TRANSFERS + 3)},
    )
    return cast(AgentState, result)
