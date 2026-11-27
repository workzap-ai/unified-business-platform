"""PI Meeting Brain tables (docs/pi-saas/pi-meeting-brain.md).

A meeting is a recording (or an imported one) of a conversation with a customer. It is turned
into a transcript (segments with timestamps), then into reviewable insights, and only an approved
insight is written to the shared brain (Problem Map, memory ledger, staff requests) through the
existing writers. No second memory system lives here.

Every row is workspace scoped (tenant, environment) with composite foreign keys, so a row can
never point across a tenant. Text is redacted before it is stored (`safety.redact_pii`). An insight
always carries its `basis` (stated, inferred, estimate, recommendation): an AI conclusion is never
stored as a stated fact.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

MEETING_SOURCES = ("upload", "browser", "native", "zoom", "meet", "teams")
BOT_STATUSES = (
    "requested",
    "joining",
    "waiting",
    "in_call",
    "recording",
    "denied",
    "ended",
    "done",
    "failed",
)
ROOM_STATES = ("created", "live", "ended", "failed")
TRANSCRIPT_STATES = ("none", "pending", "done", "failed")
BOT_ACTIVE = ("requested", "joining", "waiting", "in_call", "recording")
DOCUMENT_KINDS = ("summary_pdf", "deck_pptx")
DOCUMENT_STATUSES = ("draft", "approved")
MAX_DOCUMENT_BYTES = 4_000_000
MEETING_STATUSES = (
    "created",
    "uploaded",
    "transcribing",
    "analysing",
    "review",
    "approved",
    "failed",
)
PARTICIPANT_ROLES = ("customer", "staff", "other", "unknown")
PI_MODES = ("off", "listen", "speak")  # what pi does in a meeting: nothing, suggest, or talk
MEDIA_KINDS = ("audio", "video")
INSIGHT_KINDS = (
    "summary",
    "problem",
    "requirement_explicit",
    "requirement_implicit",
    "root_cause",
    "impact",
    "decision",
    "commitment",
    "action",
    "question",
    "risk",
    "next_step",
)
INSIGHT_BASES = ("stated", "inferred", "estimate", "recommendation")
REVIEW_STATUSES = ("pending", "approved", "rejected", "edited")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiMeeting(WorkspaceRow):
    __tablename__ = "pi_meetings"
    __table_args__ = workspace_args(
        "pi_meetings",
        scoped_fk("pi_meetings", "customer_id", "customers"),
        # the same external meeting (a Zoom id, a Meet record) is imported once per workspace
        Index(
            "uq_pi_meetings_external",
            "tenant_id",
            "environment_id",
            "source",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
        Index("ix_pi_meetings_status", "tenant_id", "environment_id", "status"),
        Index(
            "ix_pi_meetings_customer", "tenant_id", "environment_id", "customer_id", "created_at"
        ),
        CheckConstraint(_in("source", MEETING_SOURCES), name="source"),
        CheckConstraint(_in("status", MEETING_STATUSES), name="status"),
        CheckConstraint("attempts >= 0", name="attempts"),
        CheckConstraint(_in("pi_mode", PI_MODES), name="pi_mode"),
    )
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="", server_default="")
    source: Mapped[str] = mapped_column(String(10), default="upload", server_default="upload")
    status: Mapped[str] = mapped_column(String(12), default="created", server_default="created")
    language: Mapped[str] = mapped_column(String(12), default="", server_default="")
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # consent to record: nothing is stored or sent to a speech-to-text provider without it
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    consent_note: Mapped[str] = mapped_column(String(300), default="", server_default="")
    # consent to SAVE the audio/video (a separate choice from consent to record): no part is stored
    # until the person who runs the meeting has said yes, and the server remembers who and when
    media_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    media_consent_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # when the recording began: every line's time (the host's and each guest's) is measured from
    # here, so lines from several microphones sort in the order they were spoken
    recording_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recording_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    recording_mime: Mapped[str] = mapped_column(String(60), default="", server_default="")
    recording_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # which parts of the transcript the analysis has already read (analyse.py `run`), so a long
    # meeting on a rate-limited provider is finished over several calls, not lost on the first
    analysis_progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    pi_mode: Mapped[str] = mapped_column(String(8), default="off", server_default="off")
    failure_reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # the agent chosen for this meeting: a built-in key ("sales_coach") or a custom agent's id;
    # None means pi's own personality (agents.py)
    agent_key: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PiMeetingBot(WorkspaceRow):
    """pi's bot in someone else's Zoom, Meet or Teams call. The provider (Recall.ai) runs the bot;
    this row is our record of it: which meeting it belongs to, the provider's id, and where it is
    (joining, waiting to be let in, recording, done). The meeting link itself is NOT stored (it may
    carry a passcode): only its host and a hash that stops the same call being joined twice."""

    __tablename__ = "pi_meeting_bots"
    __table_args__ = workspace_args(
        "pi_meeting_bots",
        scoped_fk("pi_meeting_bots", "meeting_id", "pi_meetings"),
        Index("uq_pi_meeting_bots_external", "provider", "external_id", unique=True),
        Index("ix_pi_meeting_bots_meeting", "tenant_id", "environment_id", "meeting_id"),
        Index("ix_pi_meeting_bots_url", "tenant_id", "environment_id", "url_hash", "status"),
        CheckConstraint(_in("status", BOT_STATUSES), name="status"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="requested", server_default="requested")
    sub_code: Mapped[str] = mapped_column(String(80), default="", server_default="")
    url_hash: Mapped[str] = mapped_column(String(64))
    host: Mapped[str] = mapped_column(String(80), default="", server_default="")
    bot_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiMeetingRoom(WorkspaceRow):
    """pi's own video room (Stream Video) for a meeting we host: staff and customers join it from
    the browser. One room per meeting. The provider's call id is a random token, never the
    meeting's id, so a call id says nothing about the workspace. The words come back from the
    provider after the call (a signed callback), never from a browser."""

    __tablename__ = "pi_meeting_rooms"
    __table_args__ = workspace_args(
        "pi_meeting_rooms",
        scoped_fk("pi_meeting_rooms", "meeting_id", "pi_meetings"),
        Index(
            "uq_pi_meeting_rooms_meeting", "tenant_id", "environment_id", "meeting_id", unique=True
        ),
        Index("uq_pi_meeting_rooms_call", "provider", "call_id", unique=True),
        CheckConstraint(_in("state", ROOM_STATES), name="state"),
        CheckConstraint(_in("transcript_state", TRANSCRIPT_STATES), name="transcript_state"),
        CheckConstraint(_in("pi_mode", ("off", "speak")), name="pi_mode"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    provider: Mapped[str] = mapped_column(String(20), default="stream", server_default="stream")
    call_id: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(10), default="created", server_default="created")
    transcript_state: Mapped[str] = mapped_column(String(10), default="none", server_default="none")
    lines: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # each person's voice is recorded on its own for a short while, only to write the transcript
    # with our own speech-to-text (the provider's captions are poor in Urdu); the recording is
    # deleted at the provider as soon as the transcript is made
    audio: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    stt_tries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # pi speaking in the room (the room agent). The host sets mode, mute and intake; the agent
    # process that holds the room (one per call) renews `agent_beat_at` every few seconds.
    pi_mode: Mapped[str] = mapped_column(String(8), default="off", server_default="off")
    pi_muted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    pi_intake: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    agent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    agent_beat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # what pi has already done in this call, so a restarted agent does not introduce itself again
    # or start the speech cap afresh (an emergency stays stopped)
    pi_spoken: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pi_disclosed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    pi_halted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    pi_last_spoke_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # pi's notes of this call (short redacted facts, the language asked for, the last lines), so a
    # restarted agent does not ask everything again (see room_recall.py)
    pi_notes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class PiMeetingDocument(WorkspaceRow):
    """A designed document drawn from a meeting's approved insights: the summary PDF or the deck.
    A draft can be downloaded by the team; only an approved one may be sent to a customer. The
    bytes are kept here (they are small and made from text the team already approved), apart from
    the columns a list reads (`data` is deferred), and go with the meeting or the customer."""

    __tablename__ = "pi_meeting_documents"
    __table_args__ = workspace_args(
        "pi_meeting_documents",
        scoped_fk("pi_meeting_documents", "meeting_id", "pi_meetings"),
        Index(
            "ix_pi_meeting_documents_meeting",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "created_at",
        ),
        CheckConstraint(_in("kind", DOCUMENT_KINDS), name="kind"),
        CheckConstraint(_in("status", DOCUMENT_STATUSES), name="status"),
        CheckConstraint(f"size_bytes BETWEEN 1 AND {MAX_DOCUMENT_BYTES}", name="size"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft")
    title: Mapped[str] = mapped_column(String(200), default="", server_default="")
    language: Mapped[str] = mapped_column(String(4), default="en", server_default="en")
    size_bytes: Mapped[int] = mapped_column(Integer)
    # a hash of what the document was drawn from: the same approved content gives the same draft
    source_hash: Mapped[str] = mapped_column(String(64))
    insight_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    dropped_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class PiMeetingParticipant(WorkspaceRow):
    __tablename__ = "pi_meeting_participants"
    __table_args__ = workspace_args(
        "pi_meeting_participants",
        scoped_fk("pi_meeting_participants", "meeting_id", "pi_meetings"),
        scoped_fk("pi_meeting_participants", "mapped_customer_id", "customers"),
        Index(
            "uq_pi_meeting_participants_label",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "label",
            unique=True,
        ),
        Index(
            "uq_pi_meeting_participants_stream",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "stream_user_id",
            unique=True,
            postgresql_where=text("stream_user_id IS NOT NULL"),
        ),
        CheckConstraint(_in("role", PARTICIPANT_ROLES), name="role"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    # "Speaker 1": a label the transcript produced, never a guessed name
    label: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(10), default="unknown", server_default="unknown")
    # set by a person, only when the speaker has been mapped to the customer
    mapped_customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    mapped_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # who the video room says spoke: "s_<user id>" for staff, "g_<guest id>" for a guest
    stream_user_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # set when staff removed this person from a live room: they cannot get a new room token
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiMeetingSegment(WorkspaceRow):
    __tablename__ = "pi_meeting_segments"
    __table_args__ = workspace_args(
        "pi_meeting_segments",
        scoped_fk("pi_meeting_segments", "meeting_id", "pi_meetings"),
        scoped_fk("pi_meeting_segments", "participant_id", "pi_meeting_participants"),
        # re-running the transcript stage replaces a segment, it never duplicates it
        Index(
            "uq_pi_meeting_segments_ordinal",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "ordinal",
            unique=True,
        ),
        Index("ix_pi_meeting_segments_search", "tsv", postgresql_using="gin"),
        CheckConstraint("ordinal >= 0", name="ordinal"),
        CheckConstraint("start_ms >= 0 AND end_ms >= start_ms", name="span"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    participant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")  # redacted
    text_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    # 'simple' config: Urdu and Roman Urdu have no stemmer, so words are matched as written
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True), nullable=True
    )


class PiMeetingInsight(WorkspaceRow):
    __tablename__ = "pi_meeting_insights"
    __table_args__ = workspace_args(
        "pi_meeting_insights",
        scoped_fk("pi_meeting_insights", "meeting_id", "pi_meetings"),
        scoped_fk("pi_meeting_insights", "participant_id", "pi_meeting_participants"),
        Index(
            "ix_pi_meeting_insights_meeting",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "review_status",
        ),
        CheckConstraint(_in("kind", INSIGHT_KINDS), name="kind"),
        CheckConstraint(_in("basis", INSIGHT_BASES), name="basis"),
        CheckConstraint(_in("review_status", REVIEW_STATUSES), name="review_status"),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence"),
        # an inferred, estimated or recommended item can never claim to be stated
        CheckConstraint(
            "(basis = 'stated') OR (owner_label = '' AND due_text = '')", name="stated_only"
        ),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(24))
    basis: Mapped[str] = mapped_column(String(14))
    text: Mapped[str] = mapped_column(Text, default="", server_default="")  # redacted
    edited_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    confidence: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    # the segment ordinals this came from, so every insight can be traced to the transcript
    segment_refs: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default="{}"
    )
    participant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # who and by when: only filled when it was stated in the meeting
    owner_label: Mapped[str] = mapped_column(String(60), default="", server_default="")
    due_text: Mapped[str] = mapped_column(String(80), default="", server_default="")
    review_status: Mapped[str] = mapped_column(
        String(10), default="pending", server_default="pending"
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # set once the approved insight has been written to the brain: a second approval is a no-op
    brain_ref: Mapped[str] = mapped_column(String(60), default="", server_default="")
    written_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiMeetingMedia(WorkspaceRow):
    """One stored part of a meeting's recording. The bytes are in the workspace's own object
    storage (its S3 connection); this row keeps the key, the size, where the part sits in the
    meeting and the date until which it is kept."""

    __tablename__ = "pi_meeting_media"
    __table_args__ = workspace_args(
        "pi_meeting_media",
        scoped_fk("pi_meeting_media", "meeting_id", "pi_meetings"),
        # a part is stored once: sending it again replaces the same row and the same object
        Index(
            "uq_pi_meeting_media_part",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "kind",
            "ordinal",
            unique=True,
        ),
        CheckConstraint(_in("kind", MEDIA_KINDS), name="kind"),
        CheckConstraint(
            "ordinal >= 0 AND bytes >= 0 AND offset_ms >= 0 AND duration_ms >= 0", name="ranges"
        ),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(5))
    ordinal: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(60), default="", server_default="")
    bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    offset_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiMeetingMediaData(WorkspaceRow):
    """The bytes of a saved part when the workspace has no storage bucket (audio only, capped per
    meeting). Apart from `pi_meeting_media` so listing parts never reads audio."""

    __tablename__ = "pi_meeting_media_data"
    __table_args__ = workspace_args(
        "pi_meeting_media_data",
        scoped_fk("pi_meeting_media_data", "media_id", "pi_meeting_media"),
        Index(
            "uq_pi_meeting_media_data_media", "tenant_id", "environment_id", "media_id", unique=True
        ),
    )
    media_id: Mapped[UUID] = mapped_column(Uuid)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class PiMeetingInvite(WorkspaceRow):
    """The link staff copy so other people can add their own microphone to a meeting (PMB-4). Only
    a hash of the token is stored: the token itself is shown once, when the link is made."""

    __tablename__ = "pi_meeting_invites"
    __table_args__ = workspace_args(
        "pi_meeting_invites",
        scoped_fk("pi_meeting_invites", "meeting_id", "pi_meetings"),
        Index("uq_pi_meeting_invites_token", "token_hash", unique=True),
        Index("ix_pi_meeting_invites_meeting", "tenant_id", "environment_id", "meeting_id"),
        CheckConstraint("max_guests BETWEEN 1 AND 20", name="max_guests"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_guests: Mapped[int] = mapped_column(SmallInteger, default=20, server_default="20")
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiMeetingGuest(WorkspaceRow):
    """Someone who opened an invite, agreed, and records their own microphone into the meeting. They
    can send audio parts for this meeting and nothing else: no guest token reads anything."""

    __tablename__ = "pi_meeting_guests"
    __table_args__ = workspace_args(
        "pi_meeting_guests",
        scoped_fk("pi_meeting_guests", "meeting_id", "pi_meetings"),
        scoped_fk("pi_meeting_guests", "invite_id", "pi_meeting_invites"),
        scoped_fk("pi_meeting_guests", "participant_id", "pi_meeting_participants"),
        Index("uq_pi_meeting_guests_token", "token_hash", unique=True),
        Index(
            "uq_pi_meeting_guests_slot",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "slot",
            unique=True,
        ),
        CheckConstraint("slot BETWEEN 1 AND 20", name="slot"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    invite_id: Mapped[UUID] = mapped_column(Uuid)
    participant_id: Mapped[UUID] = mapped_column(Uuid)
    slot: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(60), default="", server_default="")  # redacted
    token_hash: Mapped[str] = mapped_column(String(64))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # where this guest's first part sits on the meeting's clock; later parts follow at one minute
    # each by their number, so a retry replaces the same lines and two parts never collide
    first_offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seq: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    last_part_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


CHAT_ROLES = ("user", "assistant")


class PiMeetingAgent(WorkspaceRow):
    """An agent a workspace wrote itself: a name, a look and a few lines of focus and tone. It is
    archived, never deleted, so a meeting or chat that used it keeps working."""

    __tablename__ = "pi_meeting_agents"
    __table_args__ = workspace_args(
        "pi_meeting_agents",
        Index(
            "uq_pi_meeting_agents_name",
            "tenant_id",
            "environment_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )
    name: Mapped[str] = mapped_column(String(40))
    tagline: Mapped[str] = mapped_column(String(80), default="", server_default="")
    icon: Mapped[str] = mapped_column(String(20), default="sparkles", server_default="sparkles")
    color: Mapped[str] = mapped_column(String(12), default="green", server_default="green")
    instructions: Mapped[str] = mapped_column(Text)  # redacted, checked by agents.py
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiMeetingChat(WorkspaceRow):
    """One chat with a meeting ("Ask AI"): its agent and its messages. It goes with the meeting."""

    __tablename__ = "pi_meeting_chats"
    __table_args__ = workspace_args(
        "pi_meeting_chats",
        scoped_fk("pi_meeting_chats", "meeting_id", "pi_meetings"),
        Index(
            "ix_pi_meeting_chats_meeting",
            "tenant_id",
            "environment_id",
            "meeting_id",
            "updated_at",
        ),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    agent_key: Mapped[str] = mapped_column(String(40), default="pi", server_default="pi")
    title: Mapped[str] = mapped_column(String(80), default="", server_default="")
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiMeetingChatMessage(WorkspaceRow):
    __tablename__ = "pi_meeting_chat_messages"
    __table_args__ = workspace_args(
        "pi_meeting_chat_messages",
        scoped_fk("pi_meeting_chat_messages", "chat_id", "pi_meeting_chats"),
        Index(
            "ix_pi_meeting_chat_messages_chat",
            "tenant_id",
            "environment_id",
            "chat_id",
            "created_at",
        ),
        CheckConstraint(_in("role", CHAT_ROLES), name="role"),
    )
    chat_id: Mapped[UUID] = mapped_column(Uuid)
    role: Mapped[str] = mapped_column(String(9))
    found: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    partial: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # declared last: a column called `text` hides sqlalchemy's text() for the rest of the class body
    text: Mapped[str] = mapped_column(Text, default="", server_default="")  # redacted
