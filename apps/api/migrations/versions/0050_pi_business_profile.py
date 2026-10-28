"""pi business profile: profiles, facts and page snapshots

Revision ID: 0050_pi_business_profile
Revises: 0049_pi_move_log

Platform spec v1.4, Part 16 (16.3 and the data sketch): `pi_business_profiles` (business_profile),
`pi_profile_facts` (profile_fact: source owner|page|photo, confirmed flag, evidence) and
`pi_page_snapshots` (page_snapshot: date, hash, short extracted fields). Written only when the
warm-up (`response_rules.brain.warmup`) is on.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050_pi_business_profile"
down_revision = "0049_pi_move_log"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _workspace_constraints(table: str) -> list[sa.schema.SchemaItem]:
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name=f"fk_{table}_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f(f"fk_{table}_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name=f"uq_{table}_scope_id"),
    ]


def _scoped_fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "environment_id", column],
        [f"{target}.tenant_id", f"{target}.environment_id", f"{target}.id"],
        name=f"fk_{table}_{column}",
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "pi_business_profiles",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(length=160), server_default="", nullable=False),
        sa.Column("owner_address_name", sa.String(length=80), server_default="", nullable=False),
        sa.Column("industry_pack_id", sa.String(length=80), nullable=True),
        sa.Column("industry_confidence", sa.Float(), nullable=True),
        sa.Column("industry_source", sa.String(length=16), nullable=True),
        sa.Column("what_they_do", sa.Text(), server_default="", nullable=False),
        sa.Column("city_area", sa.String(length=160), server_default="", nullable=False),
        sa.Column("since_year", sa.Integer(), nullable=True),
        sa.Column("size_band", sa.String(length=40), server_default="", nullable=False),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("website_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("social_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("digital_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("language", sa.String(length=16), server_default="", nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "industry_source IS NULL OR industry_source IN ('owner', 'page', 'confirmed')",
            name=op.f("ck_pi_business_profiles_industry_source"),
        ),
        _scoped_fk("pi_business_profiles", "customer_id", "customers"),
        _scoped_fk("pi_business_profiles", "business_id", "pi_businesses"),
        *_workspace_constraints("pi_business_profiles"),
    )
    op.create_index(
        "uq_pi_business_profiles_customer",
        "pi_business_profiles",
        ["tenant_id", "environment_id", "customer_id"],
        unique=True,
        postgresql_where=sa.text("business_id IS NULL"),
    )
    op.create_index(
        "uq_pi_business_profiles_business",
        "pi_business_profiles",
        ["tenant_id", "environment_id", "customer_id", "business_id"],
        unique=True,
        postgresql_where=sa.text("business_id IS NOT NULL"),
    )
    op.create_table(
        "pi_profile_facts",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("confirmed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_snippet", sa.String(length=200), server_default="", nullable=False),
        sa.Column("source_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "source IN ('owner', 'page', 'photo')", name=op.f("ck_pi_profile_facts_source")
        ),
        sa.CheckConstraint("length(btrim(key)) > 0", name=op.f("ck_pi_profile_facts_key_nonempty")),
        _scoped_fk("pi_profile_facts", "profile_id", "pi_business_profiles"),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "profile_id", "key", name="uq_pi_profile_facts_key"
        ),
        *_workspace_constraints("pi_profile_facts"),
    )
    op.create_table(
        "pi_page_snapshots",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column("extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="ok", nullable=False),
        *_base_columns(),
        _scoped_fk("pi_page_snapshots", "profile_id", "pi_business_profiles"),
        *_workspace_constraints("pi_page_snapshots"),
    )
    op.create_index(
        "ix_pi_page_snapshots_profile",
        "pi_page_snapshots",
        ["tenant_id", "environment_id", "profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_page_snapshots_profile", table_name="pi_page_snapshots")
    op.drop_table("pi_page_snapshots")
    op.drop_table("pi_profile_facts")
    op.drop_index("uq_pi_business_profiles_business", table_name="pi_business_profiles")
    op.drop_index("uq_pi_business_profiles_customer", table_name="pi_business_profiles")
    op.drop_table("pi_business_profiles")
