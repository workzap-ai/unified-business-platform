from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.memberships.models import Membership
from app.modules.notifications.service import notify
from app.modules.pi.models import (
    PiAgentRun,
    PiConversation,
    PiHandoff,
    PiMessage,
    PiPendingAction,
    WhatsAppConnection,
)
from app.modules.pi.schemas import ConversationView, HandoffView
from app.modules.products.service import enabled_products
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, PermissionDenied
from app.shared.scope import WorkspaceScope
from app.shared.state_machine import StateMachine
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

ACTIVE_HANDOFF = ("open", "assigned", "in_progress")

# open -> assigned -> in_progress -> resolved -> closed. Reassignment keeps a handoff
# owned; an unworked handoff may be dismissed (closed); resolved/closed may be reopened.
HANDOFF_STATES = StateMachine(
    "handoff",
    {
        "open": frozenset({"assigned", "in_progress", "closed"}),
        "assigned": frozenset({"assigned", "in_progress", "closed"}),
        "in_progress": frozenset({"assigned", "resolved"}),
        "resolved": frozenset({"closed", "open"}),
        "closed": frozenset({"open"}),
    },
)
HANDOFF_ACTIONS = {
    "assign": "assigned",
    "start": "in_progress",
    "resolve": "resolved",
    "close": "closed",
    "reopen": "open",
}

# Sent once when the pipeline itself hands a conversation to the team.
HANDOFF_NOTICE = "Thanks for your message. A member of our team will reply here shortly."


async def require_pi(
    session: AsyncSession,
    scope: WorkspaceScope,
    permission: str = "pi.read",
    feature: str | None = None,
) -> None:
    """RBAC first, then product entitlement with an explainable error code."""
    scope.require(permission)
    features = (await enabled_products(session, scope)).get("pi")
    if features is None:
        raise BusinessRuleViolation(
            "PI_NOT_ENABLED", "PI is not installed or not enabled in this environment", 403
        )
    if feature and feature not in features:
        raise BusinessRuleViolation(
            "PI_FEATURE_DISABLED", f"The PI {feature} feature is not enabled", 403
        )


class VisibleConversations(WorkspaceRepository[PiConversation]):
    """Record-level inbox scope. Members without ``pi.inbox.all`` see only conversations
    assigned to them (directly or through an active handoff). Every read, count, search
    and mutation goes through this predicate, so hidden conversations are "not found".
    System actors (the PI runtime) are bound by tenant/environment scope only."""

    def predicate(self) -> Any:
        base = super().predicate()
        if self.scope.is_system or self.scope.can("pi.inbox.all"):
            return base
        if self.scope.user_id is None:
            return base & false()
        handed_to_me = (
            select(PiHandoff.conversation_id)
            .where(
                PiHandoff.tenant_id == self.scope.tenant_id,
                PiHandoff.environment_id == self.scope.environment_id,
                PiHandoff.status.in_(ACTIVE_HANDOFF),
                PiHandoff.assigned_user_id == self.scope.user_id,
            )
            .scalar_subquery()
        )
        return base & or_(
            PiConversation.assigned_user_id == self.scope.user_id,
            PiConversation.id.in_(handed_to_me),
        )


class PiService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.conversations = VisibleConversations(session, PiConversation, scope)
        self.messages = WorkspaceRepository(session, PiMessage, scope)
        self.handoffs = WorkspaceRepository(session, PiHandoff, scope)
        self.customers = WorkspaceRepository(session, Customer, scope)

    async def require(self, permission: str = "pi.read", feature: str | None = None) -> None:
        await require_pi(self.session, self.scope, permission, feature)

    async def cancel_pending(self, conversation_id: UUID) -> None:
        """Human control invalidates outstanding customer confirmations."""
        rows = await self.session.scalars(
            WorkspaceRepository(self.session, PiPendingAction, self.scope)
            .select()
            .where(
                PiPendingAction.conversation_id == conversation_id,
                PiPendingAction.status == "pending",
            )
            .with_for_update()
        )
        for row in rows:
            row.status, row.resolved_at = "cancelled", datetime.now(UTC)

    async def view(self, conversation: PiConversation) -> ConversationView:
        customer = await self.customers.get(conversation.customer_id)
        handoff = await self.handoffs.find(
            PiHandoff.conversation_id == conversation.id,
            PiHandoff.status.in_(["open", "assigned", "in_progress"]),
        )
        last = await self.session.scalar(
            self.messages.select()
            .where(PiMessage.conversation_id == conversation.id)
            .order_by(PiMessage.created_at.desc())
            .limit(1)
        )
        fields = {
            k: getattr(conversation, k)
            for k in ConversationView.model_fields
            if hasattr(conversation, k)
        }
        return ConversationView(
            **fields,
            customer_name=customer.name,
            customer_phone=customer.phone,
            handoff_id=handoff.id if handoff else None,
            handoff_status=handoff.status if handoff else None,
            assigned_label=(handoff.assigned_label if handoff and handoff.assigned_label else None)
            or (
                await self.session.scalar(
                    select(PlatformUser.display_name).where(
                        PlatformUser.id == conversation.assigned_user_id
                    )
                )
                if conversation.assigned_user_id
                else None
            ),
            last_sender=last.sender_type if last else "customer",
            last_intent=await self.session.scalar(
                WorkspaceRepository(self.session, PiAgentRun, self.scope)
                .select()
                .with_only_columns(PiAgentRun.intent)
                .where(PiAgentRun.conversation_id == conversation.id)
                .order_by(PiAgentRun.created_at.desc())
                .limit(1)
            ),
            pending_confirmation=await WorkspaceRepository(
                self.session, PiPendingAction, self.scope
            ).find(
                PiPendingAction.conversation_id == conversation.id,
                PiPendingAction.status == "pending",
                PiPendingAction.expires_at > datetime.now(UTC),
            )
            is not None,
        )

    async def search(
        self,
        page: Pagination,
        search: str | None,
        status: str | None,
        mode: str | None,
        assignment: str | None = None,
        unread: bool | None = None,
    ) -> Page[ConversationView]:
        """Inbox list. ``search`` matches customer name, phone, WhatsApp number or any
        message text in the conversation; ``assignment`` is ``mine`` or ``unassigned``."""
        await self.require()
        query = self.conversations.select()
        if search:
            pattern = like_pattern(search)
            digits = "".join(ch for ch in search if ch.isdigit())
            customer_match = [Customer.name.ilike(pattern), Customer.email.ilike(pattern)]
            if len(digits) >= 3:
                customer_match += [
                    Customer.phone.ilike(f"%{digits}%"),
                    Customer.whatsapp_id.ilike(f"%{digits}%"),
                ]
            matching_customers = (
                self.customers.select().with_only_columns(Customer.id).where(or_(*customer_match))
            )
            matching_messages = (
                self.messages.select()
                .with_only_columns(PiMessage.conversation_id)
                .where(PiMessage.body.ilike(pattern))
            )
            clauses = [
                PiConversation.customer_id.in_(matching_customers),
                PiConversation.id.in_(matching_messages),
            ]
            if len(digits) >= 3:
                clauses.append(PiConversation.contact_wa_id.ilike(f"%{digits}%"))
            query = query.where(or_(*clauses))
        if status:
            query = query.where(PiConversation.status == status)
        if mode:
            query = query.where(PiConversation.mode == mode)
        if assignment == "mine":
            if self.scope.user_id is None:
                raise PermissionDenied
            handed_to_me = (
                self.handoffs.select()
                .with_only_columns(PiHandoff.conversation_id)
                .where(
                    PiHandoff.status.in_(ACTIVE_HANDOFF),
                    PiHandoff.assigned_user_id == self.scope.user_id,
                )
            )
            query = query.where(
                or_(
                    PiConversation.assigned_user_id == self.scope.user_id,
                    PiConversation.id.in_(handed_to_me),
                )
            )
        elif assignment == "unassigned":
            assigned_handoffs = (
                self.handoffs.select()
                .with_only_columns(PiHandoff.conversation_id)
                .where(
                    PiHandoff.status.in_(ACTIVE_HANDOFF),
                    PiHandoff.assigned_user_id.is_not(None),
                )
            )
            query = query.where(
                PiConversation.assigned_user_id.is_(None),
                PiConversation.id.not_in(assigned_handoffs),
            )
        if unread is True:
            query = query.where(PiConversation.unread_count > 0)
        elif unread is False:
            query = query.where(PiConversation.unread_count == 0)
        rows, count = await self.conversations.page(
            query.order_by(PiConversation.last_message_at.desc(), PiConversation.id.desc()), page
        )
        return Page(
            items=[await self.view(row) for row in rows],
            total=count,
            page=page.page,
            page_size=page.page_size,
        )

    async def handoff_view(self, handoff: PiHandoff) -> HandoffView:
        customer = await self.customers.get(handoff.customer_id)
        fields = {k: getattr(handoff, k) for k in HandoffView.model_fields if hasattr(handoff, k)}
        return HandoffView(**fields, customer_name=customer.name)

    async def handoff(self, conversation_id: UUID, reason: str, summary: str) -> PiHandoff:
        await self.require("pi.handoffs.manage")
        conversation = await self.conversations.get(conversation_id, for_update=True)
        conversation.mode = "human"
        conversation.followup_due_at = None
        await self.cancel_pending(conversation.id)
        existing = await self.handoffs.find(
            PiHandoff.conversation_id == conversation.id,
            PiHandoff.status.in_(ACTIVE_HANDOFF),
        )
        if existing:
            return existing
        handoff = await self.handoffs.add(
            self.handoffs.new(
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                reason=reason,
                summary=summary[:2000],
                created_by_label=self.scope.actor_label,
            )
        )
        await record(
            self.session,
            "pi.handoff_created",
            scope=self.scope,
            entity_type="pi_handoff",
            entity_id=handoff.id,
            details={"reason": reason},
        )
        await notify(
            self.session,
            self.scope,
            "pi.handoff",
            "Customer needs a team member",
            link="/pi/handoffs/open",
            permission="pi.handoffs.manage",
            dedupe_key=f"handoff:{handoff.id}",
        )
        return handoff

    async def mode(self, conversation_id: UUID, action: str) -> PiConversation:
        await self.require("pi.inbox.reply")
        conversation = await self.conversations.get(conversation_id, for_update=True)
        if action == "read":
            conversation.unread_count = 0
        elif action == "close":
            conversation.status = "closed"
            conversation.followup_due_at = None
        elif action == "takeover":
            # Durable flag: the pipeline, tools, sender and sweeper all check it.
            conversation.mode = "human"
            conversation.followup_due_at = None
            conversation.assigned_user_id = self.scope.user_id
            await self.cancel_pending(conversation.id)
        elif action == "return-to-ai":
            open_handoff = await self.handoffs.find(
                PiHandoff.conversation_id == conversation.id,
                PiHandoff.status.in_(ACTIVE_HANDOFF),
            )
            if open_handoff:
                if not self.scope.can("pi.handoffs.manage"):
                    raise BusinessRuleViolation(
                        "HANDOFF_OPEN", "Resolve the handoff before returning to AI"
                    )
                # Handing the conversation back to Pi settles the open handoff in the
                # same step (one click), recorded like any other resolution.
                open_handoff.status = "resolved"
                open_handoff.resolved_at = datetime.now(UTC)
                open_handoff.resolution_note = open_handoff.resolution_note or "Returned to Pi"
                await record(
                    self.session,
                    "pi.handoff_resolve",
                    scope=self.scope,
                    entity_type="pi_handoff",
                    entity_id=open_handoff.id,
                    details={"via": "return-to-ai"},
                )
            conversation.mode = "ai"
            conversation.assigned_user_id = None
        await self.session.flush()
        await record(
            self.session,
            f"pi.{action}",
            scope=self.scope,
            entity_type="pi_conversation",
            entity_id=conversation.id,
        )
        return conversation

    async def human_message(self, conversation_id: UUID, body: str) -> PiMessage:
        await self.require("pi.inbox.reply")
        conversation = await self.conversations.get(conversation_id, for_update=True)
        if conversation.mode != "human" or conversation.status != "open":
            raise BusinessRuleViolation(
                "TAKEOVER_REQUIRED", "Take over an open conversation before replying"
            )
        if (
            not conversation.last_inbound_at
            or (datetime.now(UTC) - conversation.last_inbound_at).total_seconds() > 86400
        ):
            raise BusinessRuleViolation(
                "MESSAGE_WINDOW_CLOSED", "The customer must message again before a free-text reply"
            )
        connection = await WorkspaceRepository(self.session, WhatsAppConnection, self.scope).find(
            WhatsAppConnection.id == conversation.connection_id
        )
        # Persisted as queued; never reported as sent. Without a verified, active number the
        # send job records a terminal "not connected" state instead of retrying.
        connected = bool(
            connection
            and connection.status == "active"
            and connection.verified_at is not None
            and (
                connection.access_token_encrypted
                or connection.integration_connection_id is not None
                or connection.provider == "kapso"  # authenticated by the project key
            )
        )
        message = await self.messages.add(
            self.messages.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="human",
                body=body,
                status="queued",
                error_code=None if connected else "WHATSAPP_NOT_CONNECTED",
                sent_by_user_id=self.scope.user_id,
                sent_by_label=self.scope.actor_label,
            )
        )
        await record(
            self.session,
            "pi.reply_queued",
            scope=self.scope,
            entity_type="pi_message",
            entity_id=message.id,
        )
        return message

    async def update_handoff(
        self, handoff_id: UUID, action: str, assignee: UUID | None, note: str
    ) -> PiHandoff:
        await self.require("pi.handoffs.manage")
        handoff = await self.handoffs.get(handoff_id, for_update=True)
        target = HANDOFF_ACTIONS.get(action)
        if target is None:
            raise BusinessRuleViolation("INVALID_TRANSITION", "This handoff action is unavailable")
        HANDOFF_STATES.ensure(handoff.status, target)
        now = datetime.now(UTC)
        if action in {"assign", "start"}:
            user_id = assignee or self.scope.user_id
            user = await self.session.scalar(
                select(PlatformUser)
                .join(Membership, Membership.user_id == PlatformUser.id)
                .where(
                    Membership.tenant_id == self.scope.tenant_id,
                    Membership.status == "active",
                    PlatformUser.status == "active",
                    PlatformUser.id == user_id,
                )
            )
            if not user:
                raise PermissionDenied
            handoff.assigned_user_id, handoff.assigned_label = user.id, user.display_name
            handoff.assigned_at = now
        if action == "start":
            handoff.started_at = now
            conversation = await self.conversations.get(handoff.conversation_id, for_update=True)
            conversation.mode = "human"
            conversation.assigned_user_id = handoff.assigned_user_id
        if action == "resolve":
            if not note.strip():
                raise BusinessRuleViolation("RESOLUTION_REQUIRED", "Describe the resolution")
            handoff.resolved_at, handoff.resolution_note = now, note
        if action == "close":
            handoff.closed_at = now
        if action == "reopen":
            conversation = await self.conversations.get(handoff.conversation_id, for_update=True)
            other = await self.handoffs.find(
                PiHandoff.conversation_id == conversation.id,
                PiHandoff.id != handoff.id,
                PiHandoff.status.in_(ACTIVE_HANDOFF),
            )
            if other:
                raise BusinessRuleViolation("HANDOFF_OPEN", "An active handoff already exists")
            conversation.mode = "human"
            handoff.resolved_at = handoff.closed_at = None
        handoff.status = target
        await self.session.flush()
        await record(
            self.session,
            f"pi.handoff_{action}",
            scope=self.scope,
            entity_type="pi_handoff",
            entity_id=handoff.id,
        )
        return handoff
