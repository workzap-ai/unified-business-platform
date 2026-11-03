"""The Business Profile on tables (platform spec v1.4, 16.3 and the Part 16 data sketch).

`pi_business_profiles` (spec `business_profile`) is one row per business an owner talks about:
a summary built from the facts. `pi_profile_facts` (spec `profile_fact`) holds each fact with its
source (owner, page or photo), whether the owner confirmed it, and when. `pi_page_snapshots` (spec
`page_snapshot`) is the audit trail of a quick look: date, hash and the short fields read, never
the page text. Only confirmed facts count as grounded for the idea filter (G2).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

FACT_SOURCES = ("owner", "page", "photo")


class PiBusinessProfile(WorkspaceRow):
    __tablename__ = "pi_business_profiles"
    __table_args__ = workspace_args(
        "pi_business_profiles",
        scoped_fk("pi_business_profiles", "customer_id", "customers"),
        scoped_fk("pi_business_profiles", "business_id", "pi_businesses"),
        Index(
            "uq_pi_business_profiles_customer",
            "tenant_id",
            "environment_id",
            "customer_id",
            unique=True,
            postgresql_where=text("business_id IS NULL"),
        ),
        Index(
            "uq_pi_business_profiles_business",
            "tenant_id",
            "environment_id",
            "customer_id",
            "business_id",
            unique=True,
            postgresql_where=text("business_id IS NOT NULL"),
        ),
        CheckConstraint(
            "industry_source IS NULL OR industry_source IN ('owner', 'page', 'confirmed')",
            name="industry_source",
        ),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    business_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    display_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    owner_address_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    industry_pack_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    industry_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    what_they_do: Mapped[str] = mapped_column(Text, default="", server_default="")
    city_area: Mapped[str] = mapped_column(String(160), default="", server_default="")
    since_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_band: Mapped[str] = mapped_column(String(40), default="", server_default="")
    channels: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    website_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    social_urls: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    digital_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    language: Mapped[str] = mapped_column(String(16), default="", server_default="")


class PiProfileFact(WorkspaceRow):
    __tablename__ = "pi_profile_facts"
    __table_args__ = workspace_args(
        "pi_profile_facts",
        scoped_fk("pi_profile_facts", "profile_id", "pi_business_profiles"),
        UniqueConstraint(
            "tenant_id", "environment_id", "profile_id", "key", name="uq_pi_profile_facts_key"
        ),
        CheckConstraint("source IN ('owner', 'page', 'photo')", name="source"),
        CheckConstraint("length(btrim(key)) > 0", name="key_nonempty"),
    )
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    key: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(8))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_snippet: Mapped[str] = mapped_column(String(200), default="", server_default="")
    source_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiPageSnapshot(WorkspaceRow):
    __tablename__ = "pi_page_snapshots"
    __table_args__ = workspace_args(
        "pi_page_snapshots",
        scoped_fk("pi_page_snapshots", "profile_id", "pi_business_profiles"),
        Index("ix_pi_page_snapshots_profile", "tenant_id", "environment_id", "profile_id"),
    )
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    url: Mapped[str] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    extracted: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="ok", server_default="ok")
