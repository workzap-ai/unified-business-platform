"""A fake nori for the bridge tests: the contract of docs/credits-pi-contract.md in a few dozen
lines, behind an httpx MockTransport. No network. It checks the signature and the timestamp the way
nori does, so a request pi signs wrongly or stale is refused here as it would be there."""

import json
import re
import time
from typing import Any

import httpx

from app.modules.pi_saas.nori_credits import signing

SECRET = "bridge-test-secret-0123456789"
BASE = "https://nori.test"

OWNER = "923009998888"
MEMBER = "923002222222"
HEAD = "923001111111"
STRANGER = "923005550000"
STAFF = "923009990001"


class FakeNori:
    def __init__(self, secret: str = SECRET) -> None:
        self.secret = secret
        self.members: dict[str, dict[str, Any]] = {
            OWNER: {"full_name": "Olive Owner", "is_owner": True, "head": False},
            MEMBER: {"full_name": "Ali Member", "is_owner": False, "head": False},
            HEAD: {"full_name": "Hana Head", "is_owner": False, "head": True},
            "923004444444": {"full_name": "Maint Member", "is_owner": False, "head": False},
        }
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.mode = "ok"  # ok | timeout | connect | 500 | 401 | badjson | list | slow_403
        self.seen_ids: dict[str, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.dups: set[tuple[str, str]] = set()
        self.credits = 12000
        self.next_number = 11
        self.team_question: str | None = None
        self.item_status_value = "new"
        self.board_cards: list[dict[str, Any]] = []
        self.board_card_reason: str | None = None  # a 400 reason nori answers
        self.welcome: dict[str, Any] = {}  # number -> the welcome_ok value nori answers

    # --- helpers ----------------------------------------------------------------------------
    def calls(self, path: str, action: str | None = None) -> list[dict[str, Any]]:
        return [
            body
            for p, body in self.requests
            if p == path and (action is None or body.get("action") == action)
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        raw = request.content
        if self.mode == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if self.mode == "connect":
            raise httpx.ConnectError("down", request=request)
        if self.mode == "500":
            return httpx.Response(500, text="boom")
        if self.mode == "401":
            return httpx.Response(401, json={"ok": False, "error": "bad signature"})
        if self.mode == "badjson":
            return httpx.Response(200, text="<html>not json</html>")
        if self.mode == "list":
            return httpx.Response(200, json=["not", "a", "dict"])
        if not signing.verify(self.secret, raw, request.headers.get("x-workzap-signature")):
            return httpx.Response(401, json={"ok": False, "error": "bad signature"})
        body = json.loads(raw)
        stamp = body.get("ts")
        if path == "/api/credits/pi" and (
            stamp is None or abs(time.time() * 1000 - float(stamp)) > 600_000
        ):
            return httpx.Response(401, json={"ok": False, "error": "stale"})
        self.requests.append((path, body))
        if path == "/api/pi/board-card":
            if self.board_card_reason:
                return httpx.Response(400, json={"ok": False, "reason": self.board_card_reason})
            dup = any(c["card_id"] == body["card_id"] for c in self.board_cards)
            if not dup:
                self.board_cards.append(body)
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "id": "i-1",
                    "ref": "R12",
                    **({"duplicate": True} if dup else {}),
                },
            )
        if path == "/api/workzap/inbound":
            return httpx.Response(200, json=self.inbound(body))
        if path == "/api/credits/pi":
            data = self.structured(body)
            status = 429 if data.get("reason") == "rate_limited" else 200
            return httpx.Response(status, json=data)
        return httpx.Response(404, json={"ok": False})

    # --- the simple door --------------------------------------------------------------------
    def inbound(self, body: dict[str, Any]) -> dict[str, Any]:
        sender, text = body["from"], str(body.get("text") or "")
        if sender not in self.members:
            return {"handled": False, "reply": None}
        key = f"in:{body['message_id']}"
        if key in self.seen_ids:
            return self.seen_ids[key]
        lowered = text.strip().lower()
        answer: dict[str, Any] = {"handled": False, "reply": None}
        if lowered == "balance":
            answer = {"handled": True, "reply": f"You have {self.credits:,} credits left."}
        elif match := re.match(r"(?:fix|change|new build|question|meeting):\s*(.+)", text, re.I):
            number = self.next_number
            self.next_number += 1
            self.items[str(number)] = {"title": match.group(1), "sender": sender}
            answer = {"handled": True, "reply": f"Request #{number} received: {match.group(1)}"}
        elif match := re.fullmatch(r"(?:make #(\d+) urgent|urgent #(\d+))", lowered):
            number = match.group(1) or match.group(2)
            answer = {"handled": True, "reply": f"Request #{number} is now urgent."}
        elif lowered.startswith("top up"):
            answer = {"handled": True, "reply": "Top up of 5,000 credits: pay with the link sent."}
        self.seen_ids[key] = answer
        return answer

    # --- the structured door ----------------------------------------------------------------
    def structured(self, body: dict[str, Any]) -> dict[str, Any]:
        action, sender = body.get("action"), body.get("from")
        if action == "identify":
            member = self.members.get(sender)
            if member is None:
                extra = {"welcome_ok": self.welcome[sender]} if sender in self.welcome else {}
                return {"ok": True, "known": False, **extra}
            return {
                "ok": True,
                "known": True,
                "member": {"member_id": "m-" + sender[-4:], "tenant_id": "t-acme", **member},
                "workspace": {"credits": True},
            }
        if sender not in self.members:
            return {"ok": False, "reason": "not_set_up", "reply": "This number is not set up."}
        message_id = body.get("message_id")
        if message_id and (action, message_id) in self.dups:
            return {"ok": True, "duplicate": True}
        if action == "capture":
            if body.get("kind") not in {"feature", "problem", "question", "meeting", "change"}:
                return {"ok": False, "reason": "invalid_kind"}
            number = self.next_number
            self.next_number += 1
            ref = f"R{number}"
            self.items[ref] = {"title": body.get("title"), "sender": sender, "body": body}
            if message_id:
                self.dups.add(("capture", message_id))
            return {
                "ok": True,
                "id": f"item-{number}",
                "number": number,
                "ref": ref,
                "route": "credits",
                "status": "new",
                "status_text": "New",
                "reply": f"Noted as {ref}. The team will look at it.",
            }
        if action == "item_status":
            item = body.get("item")
            if item:
                found = self.items.get(item)
                if found is None or found["sender"] != sender:
                    return {"ok": False, "reason": "no_such_item"}
                return {
                    "ok": True,
                    "item": {
                        "ref": item,
                        "title": found["title"],
                        "status": self.item_status_value,
                    },
                }
            return {"ok": True, "items": [{"ref": r} for r in self.items]}
        if action == "item_followups":
            if not self.team_question:
                return {"ok": True, "items": []}
            return {"ok": True, "items": [{"ref": "R11", "question": self.team_question}]}
        if action == "item_reply":
            if body.get("item") not in self.items:
                return {"ok": False, "reason": "no_such_item"}
            return {"ok": True, "status": "reviewing", "reply": "Thanks, the team has your answer."}
        if action == "item_feedback":
            closed = body.get("outcome") == "fixed"
            return {"ok": True, "status": "closed" if closed else "reopened", "reply": "Thanks."}
        if action == "request":
            if body.get("type") == "New build" and sender == "923004444444":
                return {
                    "ok": False,
                    "reason": "new_builds_not_allowed",
                    "reply": "Not on your plan.",
                }
            number = self.next_number
            self.next_number += 1
            if message_id:
                self.dups.add(("request", message_id))
            return {"ok": True, "id": f"r-{number}", "number": number}
        if action == "balance":
            return {"ok": True, "reply": f"You have {self.credits:,} credits left."}
        if action == "topup":
            if not self.members[sender]["is_owner"]:
                return {"ok": True, "reply": "Only the company owner can buy credits."}
            return {
                "ok": True,
                "reply": f"Top up of {body['credits']:,} credits: pay with the link.",
            }
        if action == "priority":
            return {"ok": True}
        if action == "attach":
            return {"ok": True}
        return {"ok": False, "reason": "unknown_action"}


class FakeProvider:
    """The WhatsApp side: records what pi sends and can be told to refuse."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.refuse_code: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if self.refuse_code:
            return httpx.Response(400, json={"error": {"code": self.refuse_code, "message": "no"}})
        self.sent.append(body)
        return httpx.Response(200, json={"messages": [{"id": f"wamid.OUT{len(self.sent)}"}]})


def router(nori: FakeNori, provider: FakeProvider):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nori.test":
            return nori(request)
        return provider(request)

    return handle


def signed(secret: str, payload: dict[str, Any]) -> tuple[bytes, str]:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return raw, signing.sign(secret, raw)
