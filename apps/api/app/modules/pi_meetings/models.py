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
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
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
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

MEETING_SOURCES = ("upload", "browser", "native", "zoom", "meet")
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
    failure_reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


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
        CheckConstraint(_in("role", PARTICIPANT_ROLES), name="role"),
    )
    meeting_id: Mapped[UUID] = mapped_column(Uuid)
    # "Speaker 1": a label the transcript produced, never a guessed name
    label: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(10), default="unknown", server_default="unknown")
    # set by a person, only when the speaker has been mapped to the customer
    mapped_customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    mapped_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


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
