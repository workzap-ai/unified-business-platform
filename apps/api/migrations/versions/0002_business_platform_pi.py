"""Auth, RBAC, environments, business modules, product registry, navigation, AI, PI.

Revision ID: 0002_business_platform_pi
Revises: 0001_tenant_foundation

Generated with Alembic autogenerate and reviewed. Adds pg_trgm (a trusted extension a
database owner may create). pgvector columns are optional (ADR 0005): they are added
only when the `vector` extension can be created; retrieval falls back to full-text
search otherwise. Seeds the PI row in the platform product catalog.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_business_platform_pi"
down_revision = "0001_tenant_foundation"
branch_labels = None
depends_on = None


def _optional_vector_columns() -> None:
    if op.get_context().as_sql:
        # Offline SQL scripts cannot probe privileges; apply pgvector columns manually.
        op.execute("-- optional: CREATE EXTENSION vector; embedding columns (see ADR 0005)")
        return
    bind = op.get_bind()
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    ).scalar()
    if not available:
        return
    savepoint = bind.begin_nested()
    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        for table in ("knowledge_chunks", "pi_memories"):
            # Untyped dimension: rows record embedding_model and are only compared within
            # the same model. Exact (scoped, bounded) scans; no ANN index yet.
            bind.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN embedding vector"))
        savepoint.commit()
    except Exception:
        # Insufficient privilege to create the extension: semantic retrieval stays off.
        savepoint.rollback()


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "platform_products",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="available", nullable=False),
        sa.Column(
            "features", postgresql.ARRAY(sa.String(length=60)), server_default="{}", nullable=False
        ),
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
        sa.CheckConstraint(
            "key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_platform_products_key_format")
        ),
        sa.CheckConstraint(
            "status IN ('available', 'deprecated')", name=op.f("ck_platform_products_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_products")),
        sa.UniqueConstraint("key", name=op.f("uq_platform_products_key")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=200), server_default="", nullable=False),
        sa.Column("active_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("active_environment_id", sa.Uuid(), nullable=True),
        sa.Column("active_branch_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["active_tenant_id"],
            ["tenants.id"],
            name=op.f("fk_auth_sessions_active_tenant_id_tenants"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform_users.id"],
            name=op.f("fk_auth_sessions_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index("ix_auth_sessions_expires", "auth_sessions", ["expires_at"], unique=False)
    op.create_index(
        "ix_auth_sessions_user_active", "auth_sessions", ["user_id", "revoked_at"], unique=False
    )
    op.create_table(
        "environments",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_environments_key_format")
        ),
        sa.CheckConstraint(
            "kind IN ('production', 'staging', 'development')", name=op.f("ck_environments_kind")
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name=op.f("ck_environments_status")),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_environments_name_nonempty")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_environments_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environments")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_environments_tenant_id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_environments_tenant_key"),
    )
    op.create_index(
        "uq_environments_one_default",
        "environments",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "navigation_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("section", sa.String(length=16), nullable=False),
        sa.Column("item_order", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "jsonb_typeof(item_order) = 'array'", name=op.f("ck_navigation_preferences_order_array")
        ),
        sa.CheckConstraint(
            "section IN ('main', 'admin')", name=op.f("ck_navigation_preferences_section")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_navigation_preferences_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform_users.id"],
            name=op.f("fk_navigation_preferences_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_navigation_preferences")),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "section", name="uq_navigation_preferences_entry"
        ),
    )
    op.create_table(
        "roles",
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=240), server_default="", nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_roles_key_format")),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_roles_name_nonempty")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_roles_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_key"),
    )
    op.create_table(
        "tenant_product_installations",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="installed", nullable=False),
        sa.Column("installed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('installed', 'suspended')",
            name=op.f("ck_tenant_product_installations_status"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["platform_products.id"],
            name=op.f("fk_tenant_product_installations_product_id_platform_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_product_installations_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_product_installations")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_product_installations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "product_id", name="uq_tenant_product_installations_product"
        ),
    )
    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform_users.id"],
            name=op.f("fk_user_credentials_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_credentials")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_credentials_user_id")),
    )
    op.create_table(
        "ai_usage_events",
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("alias", sa.String(length=20), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fallback", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("error_kind", sa.String(length=32), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('success', 'failed')", name=op.f("ck_ai_usage_events_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_ai_usage_events_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_usage_events_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_events")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_ai_usage_events_scope_id"
        ),
    )
    op.create_index(
        "ix_ai_usage_events_run",
        "ai_usage_events",
        ["tenant_id", "environment_id", "run_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_usage_events_scope_created",
        "ai_usage_events",
        ["tenant_id", "environment_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "audit_events",
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("environment_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_label", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=16), server_default="success", nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
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
        sa.CheckConstraint(
            "actor_type IN ('user', 'system', 'anonymous')", name=op.f("ck_audit_events_actor_type")
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'denied', 'failure')", name=op.f("ck_audit_events_outcome")
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["platform_users.id"],
            name=op.f("fk_audit_events_actor_user_id_platform_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_audit_events_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_events_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_actor_created",
        "audit_events",
        ["actor_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_tenant_created", "audit_events", ["tenant_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_audit_events_tenant_entity",
        "audit_events",
        ["tenant_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_table(
        "business_settings",
        sa.Column("default_currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=7, scale=4), server_default="0", nullable=False),
        sa.Column(
            "auto_invoice_on_order_confirm", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column("low_stock_threshold", sa.Integer(), server_default="5", nullable=False),
        sa.Column("invoice_due_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("quote_validity_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("quote_approval_threshold", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "max_discount_rate",
            sa.Numeric(precision=7, scale=4),
            server_default="0.1",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "default_currency ~ '^[A-Z]{3}$'", name=op.f("ck_business_settings_currency_format")
        ),
        sa.CheckConstraint(
            "invoice_due_days BETWEEN 0 AND 365", name=op.f("ck_business_settings_due_days_range")
        ),
        sa.CheckConstraint(
            "low_stock_threshold >= 0", name=op.f("ck_business_settings_threshold_nonnegative")
        ),
        sa.CheckConstraint(
            "max_discount_rate >= 0 AND max_discount_rate <= 1",
            name=op.f("ck_business_settings_discount_range"),
        ),
        sa.CheckConstraint(
            "quote_validity_days BETWEEN 1 AND 365",
            name=op.f("ck_business_settings_validity_range"),
        ),
        sa.CheckConstraint(
            "tax_rate >= 0 AND tax_rate <= 1", name=op.f("ck_business_settings_tax_rate_range")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_business_settings_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_business_settings_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_settings")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_business_settings_scope_id"
        ),
        sa.UniqueConstraint("tenant_id", "environment_id", name="uq_business_settings_scope"),
    )
    op.create_table(
        "catalog_categories",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), server_default="", nullable=False),
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
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_catalog_categories_slug_format")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_catalog_categories_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_catalog_categories_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_categories")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_catalog_categories_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "slug", name="uq_catalog_categories_slug"
        ),
    )
    op.create_table(
        "customers",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=16), nullable=True),
        sa.Column("whatsapp_id", sa.String(length=32), nullable=True),
        sa.Column("company", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column(
            "tags", postgresql.ARRAY(sa.String(length=40)), server_default="{}", nullable=False
        ),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "phone IS NULL OR phone ~ '^\\+[0-9]{7,15}$'", name=op.f("ck_customers_phone_e164")
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'whatsapp', 'import')", name=op.f("ck_customers_source")
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name=op.f("ck_customers_status")),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_customers_name_nonempty")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_customers_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_customers_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_customers_scope_id"),
    )
    op.create_index(
        "ix_customers_name_trgm",
        "customers",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_customers_scope_created",
        "customers",
        ["tenant_id", "environment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_customers_phone",
        "customers",
        ["tenant_id", "environment_id", "phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )
    op.create_index(
        "uq_customers_whatsapp",
        "customers",
        ["tenant_id", "environment_id", "whatsapp_id"],
        unique=True,
        postgresql_where=sa.text("whatsapp_id IS NOT NULL"),
    )
    op.create_table(
        "document_sequences",
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("next_value", sa.Integer(), server_default="1", nullable=False),
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
        sa.CheckConstraint("next_value > 0", name=op.f("ck_document_sequences_next_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_document_sequences_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_document_sequences_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sequences")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_document_sequences_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "kind", name="uq_document_sequences_kind"
        ),
    )
    op.create_table(
        "environment_product_installations",
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "disabled_features",
            postgresql.ARRAY(sa.String(length=60)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_environment_product_installations_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "installation_id"],
            ["tenant_product_installations.tenant_id", "tenant_product_installations.id"],
            name="fk_environment_product_installations_installation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_environment_product_installations_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environment_product_installations")),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "id",
            name="uq_environment_product_installations_scope_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "installation_id",
            name="uq_environment_product_installations_entry",
        ),
    )
    op.create_table(
        "expenses",
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("vendor", sa.String(length=160), server_default="", nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="recorded", nullable=False),
        sa.Column("recorded_by_label", sa.String(length=80), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "category IN ('rent', 'payroll', 'utilities', 'inventory', 'marketing', 'software', 'travel', 'taxes', 'professional_services', 'other')",
            name=op.f("ck_expenses_category"),
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_expenses_currency_format")),
        sa.CheckConstraint("status IN ('recorded', 'void')", name=op.f("ck_expenses_status")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_expenses_amount_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_expenses_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_expenses_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expenses")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_expenses_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", "number", name="uq_expenses_number"),
    )
    op.create_index(
        "ix_expenses_scope_incurred",
        "expenses",
        ["tenant_id", "environment_id", "incurred_on"],
        unique=False,
    )
    op.create_table(
        "inventory_locations",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
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
        sa.CheckConstraint(
            "code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_inventory_locations_code_format")
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name=op.f("ck_inventory_locations_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            name="fk_inventory_locations_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_inventory_locations_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_inventory_locations_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_locations")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "code", name="uq_inventory_locations_code"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_inventory_locations_scope_id"
        ),
    )
    op.create_index(
        "uq_inventory_locations_default",
        "inventory_locations",
        ["tenant_id", "environment_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "knowledge_sources",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=300), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
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
        sa.CheckConstraint(
            "kind IN ('company_info', 'faq', 'policy', 'catalog', 'approved_answer', 'file')",
            name=op.f("ck_knowledge_sources_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name=op.f("ck_knowledge_sources_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_knowledge_sources_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_knowledge_sources_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_sources")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_knowledge_sources_scope_id"
        ),
    )
    op.create_table(
        "membership_roles",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_membership_roles_membership",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_membership_roles_role",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_membership_roles_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_roles")),
        sa.UniqueConstraint(
            "tenant_id", "membership_id", "role_id", name="uq_membership_roles_entry"
        ),
    )
    op.create_index(
        "ix_membership_roles_role", "membership_roles", ["tenant_id", "role_id"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("recipient_user_id", sa.Uuid(), nullable=True),
        sa.Column("required_permission", sa.String(length=60), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.String(length=500), server_default="", nullable=False),
        sa.Column("link", sa.String(length=300), nullable=True),
        sa.Column("dedupe_key", sa.String(length=160), nullable=True),
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
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name=op.f("ck_notifications_severity")
        ),
        sa.CheckConstraint(
            "recipient_user_id IS NOT NULL OR required_permission IS NOT NULL",
            name=op.f("ck_notifications_audience"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["platform_users.id"],
            name=op.f("fk_notifications_recipient_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_notifications_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_notifications_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_notifications_scope_id"),
    )
    op.create_index(
        "ix_notifications_scope_created",
        "notifications",
        ["tenant_id", "environment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_notifications_dedupe",
        "notifications",
        ["tenant_id", "environment_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_table(
        "pi_agents",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
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
        sa.CheckConstraint(
            "key IN ('router', 'customer_memory', 'support', 'requirement', 'sales_order', 'handoff')",
            name=op.f("ck_pi_agents_key"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_agents_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_agents_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_agents")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_agents_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", "key", name="uq_pi_agents_key"),
    )
    op.create_table(
        "pi_settings",
        sa.Column("auto_reply_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("business_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("handoff_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("knowledge_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("whatsapp_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_settings_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_settings_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_settings")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_settings_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", name="uq_pi_settings_scope"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.String(length=60), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_role_permissions_role",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_role_permissions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
        sa.UniqueConstraint("tenant_id", "role_id", "permission", name="uq_role_permissions_entry"),
    )
    op.create_table(
        "whatsapp_connections",
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("phone_number_id", sa.String(length=32), nullable=False),
        sa.Column("display_phone_number", sa.String(length=32), nullable=False),
        sa.Column("business_account_id", sa.String(length=32), server_default="", nullable=False),
        sa.Column("display_name", sa.String(length=120), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "phone_number_id ~ '^[0-9]{5,32}$'",
            name=op.f("ck_whatsapp_connections_phone_number_id_format"),
        ),
        sa.CheckConstraint(
            "provider IN ('meta_cloud')", name=op.f("ck_whatsapp_connections_provider")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'disabled', 'error')",
            name=op.f("ck_whatsapp_connections_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_whatsapp_connections_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_whatsapp_connections_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_connections")),
        sa.UniqueConstraint("provider", "phone_number_id", name="uq_whatsapp_connections_number"),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_whatsapp_connections_scope_id"
        ),
    )
    op.create_table(
        "whatsapp_webhook_events",
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="received", nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("environment_id", sa.Uuid(), nullable=True),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("phone_number_id", sa.String(length=32), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "kind IN ('message', 'status', 'unknown')", name=op.f("ck_whatsapp_webhook_events_kind")
        ),
        sa.CheckConstraint(
            "status IN ('received', 'queued', 'processed', 'ignored', 'failed')",
            name=op.f("ck_whatsapp_webhook_events_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_whatsapp_webhook_events_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_whatsapp_webhook_events_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_webhook_events")),
        sa.UniqueConstraint("provider", "event_key", name="uq_whatsapp_webhook_events_key"),
    )
    op.create_index(
        "ix_whatsapp_webhook_events_scope_created",
        "whatsapp_webhook_events",
        ["tenant_id", "environment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_whatsapp_webhook_events_status",
        "whatsapp_webhook_events",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "catalog_products",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("pi_visible", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name=op.f("ck_catalog_products_status")
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name=op.f("ck_catalog_products_name_nonempty")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "category_id"],
            [
                "catalog_categories.tenant_id",
                "catalog_categories.environment_id",
                "catalog_categories.id",
            ],
            name="fk_catalog_products_category_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_catalog_products_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_catalog_products_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_products")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_catalog_products_scope_id"
        ),
    )
    op.create_index(
        "ix_catalog_products_name_trgm",
        "catalog_products",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_catalog_products_scope_status",
        "catalog_products",
        ["tenant_id", "environment_id", "status"],
        unique=False,
    )
    op.create_table(
        "customer_activities",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=240), nullable=False),
        sa.Column("ref_type", sa.String(length=32), nullable=True),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column("actor_label", sa.String(length=80), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_customer_activities_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_customer_activities_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_customer_activities_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_activities")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_customer_activities_scope_id"
        ),
    )
    op.create_index(
        "ix_customer_activities_customer",
        "customer_activities",
        ["tenant_id", "environment_id", "customer_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "customer_notes",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("author_label", sa.String(length=80), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
        sa.CheckConstraint("length(btrim(body)) > 0", name=op.f("ck_customer_notes_body_nonempty")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_customer_notes_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_customer_notes_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_customer_notes_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_notes")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_customer_notes_scope_id"),
    )
    op.create_index(
        "ix_customer_notes_customer",
        "customer_notes",
        ["tenant_id", "environment_id", "customer_id"],
        unique=False,
    )
    op.create_table(
        "employees",
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=16), nullable=True),
        sa.Column("job_title", sa.String(length=120), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("employment_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("salary", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("salary_currency", sa.String(length=3), nullable=True),
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
        sa.CheckConstraint(
            "employment_type IN ('full_time', 'part_time', 'contract', 'intern')",
            name=op.f("ck_employees_employment_type"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'on_leave', 'terminated')", name=op.f("ck_employees_status")
        ),
        sa.CheckConstraint(
            "manager_id IS NULL OR manager_id <> id", name=op.f("ck_employees_not_own_manager")
        ),
        sa.CheckConstraint(
            "salary IS NULL OR salary >= 0", name=op.f("ck_employees_salary_nonnegative")
        ),
        sa.CheckConstraint(
            "termination_date IS NULL OR termination_date >= hire_date",
            name=op.f("ck_employees_dates_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_employees_department",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "manager_id"],
            ["employees.tenant_id", "employees.environment_id", "employees.id"],
            name="fk_employees_manager_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_employees_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_employees_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_employees_scope_id"),
    )
    op.create_index(
        "ix_employees_department", "employees", ["tenant_id", "department_id"], unique=False
    )
    op.create_index(
        "ix_employees_scope_status",
        "employees",
        ["tenant_id", "environment_id", "status"],
        unique=False,
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=60), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_by_label", sa.String(length=80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name=op.f("ck_knowledge_documents_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "source_id"],
            [
                "knowledge_sources.tenant_id",
                "knowledge_sources.environment_id",
                "knowledge_sources.id",
            ],
            name="fk_knowledge_documents_source_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_knowledge_documents_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_knowledge_documents_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_knowledge_documents_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "source_id",
            "content_hash",
            name="uq_knowledge_documents_content",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_source",
        "knowledge_documents",
        ["tenant_id", "environment_id", "source_id"],
        unique=False,
    )
    op.create_table(
        "notification_reads",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name="fk_notification_reads_notification",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_notification_reads_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform_users.id"],
            name=op.f("fk_notification_reads_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_reads")),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_reads_entry"),
    )
    op.create_table(
        "pi_agent_tools",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("tool_key", sa.String(length=60), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "agent_id"],
            ["pi_agents.tenant_id", "pi_agents.environment_id", "pi_agents.id"],
            name="fk_pi_agent_tools_agent_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_agent_tools_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_agent_tools_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_agent_tools")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "agent_id", "tool_key", name="uq_pi_agent_tools_entry"
        ),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_agent_tools_scope_id"),
    )
    op.create_table(
        "pi_agent_versions",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), server_default="", nullable=False),
        sa.Column("model_alias", sa.String(length=20), nullable=False),
        sa.Column("temperature", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("note", sa.String(length=200), server_default="", nullable=False),
        sa.Column("created_by_label", sa.String(length=80), nullable=False),
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
        sa.CheckConstraint(
            "model_alias IN ('fast', 'balanced', 'reasoning')",
            name=op.f("ck_pi_agent_versions_alias"),
        ),
        sa.CheckConstraint(
            "temperature >= 0 AND temperature <= 1",
            name=op.f("ck_pi_agent_versions_temperature_range"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "agent_id"],
            ["pi_agents.tenant_id", "pi_agents.environment_id", "pi_agents.id"],
            name="fk_pi_agent_versions_agent_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_agent_versions_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_agent_versions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_agent_versions")),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "agent_id",
            "version",
            name="uq_pi_agent_versions_version",
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_agent_versions_scope_id"
        ),
    )
    op.create_table(
        "pi_conversations",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), server_default="whatsapp", nullable=False),
        sa.Column("contact_wa_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("mode", sa.String(length=16), server_default="ai", nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=200), server_default="", nullable=False),
        sa.Column("unread_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("summary_message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("clarification_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
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
        sa.CheckConstraint("mode IN ('ai', 'human')", name=op.f("ck_pi_conversations_mode")),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_pi_conversations_status")),
        sa.CheckConstraint(
            "unread_count >= 0", name=op.f("ck_pi_conversations_unread_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "connection_id"],
            [
                "whatsapp_connections.tenant_id",
                "whatsapp_connections.environment_id",
                "whatsapp_connections.id",
            ],
            name="fk_pi_conversations_connection_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_pi_conversations_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_conversations_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_conversations_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_conversations")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_conversations_scope_id"
        ),
    )
    op.create_index(
        "ix_pi_conversations_customer",
        "pi_conversations",
        ["tenant_id", "environment_id", "customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_pi_conversations_scope_last",
        "pi_conversations",
        ["tenant_id", "environment_id", "last_message_at"],
        unique=False,
    )
    op.create_index(
        "uq_pi_conversations_open_contact",
        "pi_conversations",
        ["tenant_id", "environment_id", "connection_id", "contact_wa_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "pi_memories",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "kind IN ('preference', 'requirement', 'context')", name=op.f("ck_pi_memories_kind")
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name=op.f("ck_pi_memories_status")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_pi_memories_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_memories_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_memories_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_memories")),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "customer_id",
            "content_hash",
            name="uq_pi_memories_entry",
        ),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_memories_scope_id"),
    )
    op.create_index(
        "ix_pi_memories_customer",
        "pi_memories",
        ["tenant_id", "environment_id", "customer_id", "status"],
        unique=False,
    )
    op.create_table(
        "sales_leads",
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("stage", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("estimated_value", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "missing_information",
            postgresql.ARRAY(sa.String(length=60)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_sales_leads_currency_format")),
        sa.CheckConstraint(
            "source IN ('manual', 'pi', 'website', 'referral')", name=op.f("ck_sales_leads_source")
        ),
        sa.CheckConstraint(
            "stage IN ('new', 'qualified', 'proposal', 'won', 'lost')",
            name=op.f("ck_sales_leads_stage"),
        ),
        sa.CheckConstraint(
            "estimated_value IS NULL OR estimated_value >= 0",
            name=op.f("ck_sales_leads_value_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_sales_leads_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_sales_leads_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sales_leads_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_leads")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_sales_leads_scope_id"),
    )
    op.create_index(
        "ix_sales_leads_conversation",
        "sales_leads",
        ["tenant_id", "environment_id", "conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_sales_leads_scope_stage",
        "sales_leads",
        ["tenant_id", "environment_id", "stage", "created_at"],
        unique=False,
    )
    op.create_table(
        "catalog_variants",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("track_inventory", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_catalog_variants_currency_format")
        ),
        sa.CheckConstraint(
            "sku ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'", name=op.f("ck_catalog_variants_sku_format")
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name=op.f("ck_catalog_variants_status")
        ),
        sa.CheckConstraint(
            "low_stock_threshold IS NULL OR low_stock_threshold >= 0",
            name=op.f("ck_catalog_variants_threshold"),
        ),
        sa.CheckConstraint("price >= 0", name=op.f("ck_catalog_variants_price_nonnegative")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "product_id"],
            [
                "catalog_products.tenant_id",
                "catalog_products.environment_id",
                "catalog_products.id",
            ],
            name="fk_catalog_variants_product_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_catalog_variants_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_catalog_variants_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_variants")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_catalog_variants_scope_id"
        ),
        sa.UniqueConstraint("tenant_id", "environment_id", "sku", name="uq_catalog_variants_sku"),
    )
    op.create_index(
        "ix_catalog_variants_product",
        "catalog_variants",
        ["tenant_id", "environment_id", "product_id"],
        unique=False,
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', content)", persisted=True),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "document_id"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.environment_id",
                "knowledge_documents.id",
            ],
            name="fk_knowledge_chunks_document_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "source_id"],
            [
                "knowledge_sources.tenant_id",
                "knowledge_sources.environment_id",
                "knowledge_sources.id",
            ],
            name="fk_knowledge_chunks_source_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_knowledge_chunks_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_knowledge_chunks_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "document_id",
            "ordinal",
            name="uq_knowledge_chunks_ordinal",
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_knowledge_chunks_scope_id"
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_scope",
        "knowledge_chunks",
        ["tenant_id", "environment_id", "source_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_search",
        "knowledge_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "pi_handoffs",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("priority", sa.String(length=16), server_default="normal", nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_label", sa.String(length=80), nullable=True),
        sa.Column("created_by_label", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.String(length=500), server_default="", nullable=False),
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
        sa.CheckConstraint(
            "priority IN ('normal', 'high', 'urgent')", name=op.f("ck_pi_handoffs_priority")
        ),
        sa.CheckConstraint(
            "reason IN ('customer_request', 'low_confidence', 'provider_failure', 'policy', 'tool_failure', 'complaint', 'sensitive', 'manual')",
            name=op.f("ck_pi_handoffs_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'assigned', 'in_progress', 'resolved', 'closed')",
            name=op.f("ck_pi_handoffs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "conversation_id"],
            [
                "pi_conversations.tenant_id",
                "pi_conversations.environment_id",
                "pi_conversations.id",
            ],
            name="fk_pi_handoffs_conversation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_pi_handoffs_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_handoffs_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_handoffs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_handoffs")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_handoffs_scope_id"),
    )
    op.create_index(
        "ix_pi_handoffs_scope_status",
        "pi_handoffs",
        ["tenant_id", "environment_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_pi_handoffs_one_active",
        "pi_handoffs",
        ["tenant_id", "environment_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'assigned', 'in_progress')"),
    )
    op.create_table(
        "pi_messages",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("sender_type", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=16), server_default="text", nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "media", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("provider_message_id", sa.String(length=160), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("agent_key", sa.String(length=32), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("sent_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("sent_by_label", sa.String(length=80), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')", name=op.f("ck_pi_messages_direction")
        ),
        sa.CheckConstraint(
            "message_type IN ('text', 'audio', 'image', 'interactive', 'other')",
            name=op.f("ck_pi_messages_type"),
        ),
        sa.CheckConstraint(
            "sender_type IN ('customer', 'ai', 'human', 'system')",
            name=op.f("ck_pi_messages_sender"),
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'skipped', 'failed', 'queued', 'sent', 'delivered', 'read')",
            name=op.f("ck_pi_messages_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "conversation_id"],
            [
                "pi_conversations.tenant_id",
                "pi_conversations.environment_id",
                "pi_conversations.id",
            ],
            name="fk_pi_messages_conversation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_messages_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_messages_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_messages")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_messages_scope_id"),
    )
    op.create_index(
        "ix_pi_messages_body_trgm",
        "pi_messages",
        ["body"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"body": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_pi_messages_conversation",
        "pi_messages",
        ["tenant_id", "environment_id", "conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_pi_messages_idempotency",
        "pi_messages",
        ["tenant_id", "environment_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_pi_messages_provider_id",
        "pi_messages",
        ["tenant_id", "environment_id", "provider_message_id"],
        unique=True,
        postgresql_where=sa.text("provider_message_id IS NOT NULL"),
    )
    op.create_table(
        "pi_pending_actions",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_message_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("kind IN ('confirm_order')", name=op.f("ck_pi_pending_actions_kind")),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired', 'failed')",
            name=op.f("ck_pi_pending_actions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "conversation_id"],
            [
                "pi_conversations.tenant_id",
                "pi_conversations.environment_id",
                "pi_conversations.id",
            ],
            name="fk_pi_pending_actions_conversation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_pending_actions_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_pending_actions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_pending_actions")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_pending_actions_scope_id"
        ),
    )
    op.create_index(
        "uq_pi_pending_actions_one_pending",
        "pi_pending_actions",
        ["tenant_id", "environment_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "quotes",
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_quotes_currency_format")),
        sa.CheckConstraint("source IN ('manual', 'pi')", name=op.f("ck_quotes_source")),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'sent', 'accepted', 'rejected', 'expired', 'cancelled')",
            name=op.f("ck_quotes_status"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
            name=op.f("ck_quotes_amounts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_quotes_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "lead_id"],
            ["sales_leads.tenant_id", "sales_leads.environment_id", "sales_leads.id"],
            name="fk_quotes_lead_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_quotes_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_quotes_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quotes")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_quotes_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", "number", name="uq_quotes_number"),
    )
    op.create_index(
        "ix_quotes_customer", "quotes", ["tenant_id", "environment_id", "customer_id"], unique=False
    )
    op.create_index(
        "ix_quotes_scope_status",
        "quotes",
        ["tenant_id", "environment_id", "status", "created_at"],
        unique=False,
    )
    op.create_table(
        "orders",
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_label", sa.String(length=80), nullable=False),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_orders_currency_format")),
        sa.CheckConstraint("source IN ('manual', 'pi', 'quote')", name=op.f("ck_orders_source")),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled')",
            name=op.f("ck_orders_status"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
            name=op.f("ck_orders_amounts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_orders_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "quote_id"],
            ["quotes.tenant_id", "quotes.environment_id", "quotes.id"],
            name="fk_orders_quote_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_orders_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_orders_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_orders_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", "number", name="uq_orders_number"),
    )
    op.create_index(
        "ix_orders_customer",
        "orders",
        ["tenant_id", "environment_id", "customer_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_orders_scope_status",
        "orders",
        ["tenant_id", "environment_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_orders_idempotency",
        "orders",
        ["tenant_id", "environment_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_orders_quote",
        "orders",
        ["tenant_id", "environment_id", "quote_id"],
        unique=True,
        postgresql_where=sa.text("quote_id IS NOT NULL AND status <> 'cancelled'"),
    )
    op.create_table(
        "pi_agent_runs",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "agent_path",
            postgresql.ARRAY(sa.String(length=32)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("transfers", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("response_message_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'handoff', 'skipped')",
            name=op.f("ck_pi_agent_runs_status"),
        ),
        sa.CheckConstraint(
            "transfers >= 0 AND transfers <= 3", name=op.f("ck_pi_agent_runs_transfer_limit")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "conversation_id"],
            [
                "pi_conversations.tenant_id",
                "pi_conversations.environment_id",
                "pi_conversations.id",
            ],
            name="fk_pi_agent_runs_conversation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "message_id"],
            ["pi_messages.tenant_id", "pi_messages.environment_id", "pi_messages.id"],
            name="fk_pi_agent_runs_message_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_agent_runs_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_agent_runs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_agent_runs")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_agent_runs_scope_id"),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "message_id", name="uq_pi_agent_runs_message"
        ),
    )
    op.create_index(
        "ix_pi_agent_runs_scope_created",
        "pi_agent_runs",
        ["tenant_id", "environment_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "quote_lines",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
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
        sa.CheckConstraint("quantity > 0", name=op.f("ck_quote_lines_quantity_positive")),
        sa.CheckConstraint(
            "unit_price >= 0 AND discount >= 0 AND line_total >= 0",
            name=op.f("ck_quote_lines_amounts"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "quote_id"],
            ["quotes.tenant_id", "quotes.environment_id", "quotes.id"],
            name="fk_quote_lines_quote_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "variant_id"],
            [
                "catalog_variants.tenant_id",
                "catalog_variants.environment_id",
                "catalog_variants.id",
            ],
            name="fk_quote_lines_variant_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_quote_lines_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_quote_lines_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_lines")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_quote_lines_scope_id"),
    )
    op.create_index(
        "ix_quote_lines_quote",
        "quote_lines",
        ["tenant_id", "environment_id", "quote_id", "position"],
        unique=False,
    )
    op.create_table(
        "stock_levels",
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("on_hand", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved", sa.Integer(), server_default="0", nullable=False),
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
        sa.CheckConstraint("on_hand >= 0", name=op.f("ck_stock_levels_on_hand_nonnegative")),
        sa.CheckConstraint("reserved >= 0", name=op.f("ck_stock_levels_reserved_nonnegative")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "location_id"],
            [
                "inventory_locations.tenant_id",
                "inventory_locations.environment_id",
                "inventory_locations.id",
            ],
            name="fk_stock_levels_location_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "variant_id"],
            [
                "catalog_variants.tenant_id",
                "catalog_variants.environment_id",
                "catalog_variants.id",
            ],
            name="fk_stock_levels_variant_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_stock_levels_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_stock_levels_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_levels")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_stock_levels_scope_id"),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "variant_id", "location_id", name="uq_stock_levels_item"
        ),
    )
    op.create_table(
        "stock_movements",
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=240), server_default="", nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("ref_type", sa.String(length=32), nullable=True),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("actor_label", sa.String(length=80), nullable=False),
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
        sa.CheckConstraint(
            "kind IN ('receipt', 'adjustment', 'sale', 'return', 'transfer_in', 'transfer_out')",
            name=op.f("ck_stock_movements_kind"),
        ),
        sa.CheckConstraint(
            "balance_after >= 0", name=op.f("ck_stock_movements_balance_nonnegative")
        ),
        sa.CheckConstraint("quantity <> 0", name=op.f("ck_stock_movements_quantity_nonzero")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "location_id"],
            [
                "inventory_locations.tenant_id",
                "inventory_locations.environment_id",
                "inventory_locations.id",
            ],
            name="fk_stock_movements_location_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "variant_id"],
            [
                "catalog_variants.tenant_id",
                "catalog_variants.environment_id",
                "catalog_variants.id",
            ],
            name="fk_stock_movements_variant_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_stock_movements_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_stock_movements_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_stock_movements_scope_id"
        ),
    )
    op.create_index(
        "ix_stock_movements_variant_created",
        "stock_movements",
        ["tenant_id", "environment_id", "variant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_stock_movements_idempotency",
        "stock_movements",
        ["tenant_id", "environment_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "invoices",
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "amount_paid", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_invoices_currency_format")),
        sa.CheckConstraint(
            "status IN ('draft', 'issued', 'partially_paid', 'paid', 'void')",
            name=op.f("ck_invoices_status"),
        ),
        sa.CheckConstraint(
            "amount_paid >= 0 AND amount_paid <= total", name=op.f("ck_invoices_paid_range")
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
            name=op.f("ck_invoices_amounts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_invoices_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "order_id"],
            ["orders.tenant_id", "orders.environment_id", "orders.id"],
            name="fk_invoices_order_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_invoices_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_invoices_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_invoices_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", "number", name="uq_invoices_number"),
    )
    op.create_index(
        "ix_invoices_customer",
        "invoices",
        ["tenant_id", "environment_id", "customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_invoices_scope_status",
        "invoices",
        ["tenant_id", "environment_id", "status", "due_date"],
        unique=False,
    )
    op.create_index(
        "uq_invoices_order",
        "invoices",
        ["tenant_id", "environment_id", "order_id"],
        unique=True,
        postgresql_where=sa.text("order_id IS NOT NULL AND status <> 'void'"),
    )
    op.create_table(
        "order_lines",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
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
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_lines_quantity_positive")),
        sa.CheckConstraint(
            "unit_price >= 0 AND discount >= 0 AND line_total >= 0",
            name=op.f("ck_order_lines_amounts"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "order_id"],
            ["orders.tenant_id", "orders.environment_id", "orders.id"],
            name="fk_order_lines_order_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "variant_id"],
            [
                "catalog_variants.tenant_id",
                "catalog_variants.environment_id",
                "catalog_variants.id",
            ],
            name="fk_order_lines_variant_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_order_lines_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_order_lines_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_lines")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_order_lines_scope_id"),
    )
    op.create_index(
        "ix_order_lines_order",
        "order_lines",
        ["tenant_id", "environment_id", "order_id", "position"],
        unique=False,
    )
    op.create_index(
        "ix_order_lines_variant",
        "order_lines",
        ["tenant_id", "environment_id", "variant_id"],
        unique=False,
    )
    op.create_table(
        "pi_tool_calls",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_key", sa.String(length=32), nullable=False),
        sa.Column("tool_key", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('success', 'denied', 'invalid', 'error', 'confirmation_required')",
            name=op.f("ck_pi_tool_calls_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "run_id"],
            ["pi_agent_runs.tenant_id", "pi_agent_runs.environment_id", "pi_agent_runs.id"],
            name="fk_pi_tool_calls_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_tool_calls_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_tool_calls_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_tool_calls")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_tool_calls_scope_id"),
    )
    op.create_index(
        "ix_pi_tool_calls_run",
        "pi_tool_calls",
        ["tenant_id", "environment_id", "run_id"],
        unique=False,
    )
    op.create_index(
        "ix_pi_tool_calls_scope_created",
        "pi_tool_calls",
        ["tenant_id", "environment_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "invoice_lines",
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
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
        sa.CheckConstraint("quantity > 0", name=op.f("ck_invoice_lines_quantity_positive")),
        sa.CheckConstraint(
            "unit_price >= 0 AND discount >= 0 AND line_total >= 0",
            name=op.f("ck_invoice_lines_amounts"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.environment_id", "invoices.id"],
            name="fk_invoice_lines_invoice_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "variant_id"],
            [
                "catalog_variants.tenant_id",
                "catalog_variants.environment_id",
                "catalog_variants.id",
            ],
            name="fk_invoice_lines_variant_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_invoice_lines_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_invoice_lines_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_lines")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_invoice_lines_scope_id"),
    )
    op.create_index(
        "ix_invoice_lines_invoice",
        "invoice_lines",
        ["tenant_id", "environment_id", "invoice_id", "position"],
        unique=False,
    )
    op.create_table(
        "payments",
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=120), server_default="", nullable=False),
        sa.Column("recorded_by_label", sa.String(length=80), nullable=False),
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
        sa.CheckConstraint(
            "method IN ('cash', 'bank_transfer', 'card', 'mobile_wallet', 'other')",
            name=op.f("ck_payments_method"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.environment_id", "invoices.id"],
            name="fk_payments_invoice_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_payments_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_payments_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_payments_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", "number", name="uq_payments_number"),
    )
    op.create_index(
        "ix_payments_invoice",
        "payments",
        ["tenant_id", "environment_id", "invoice_id"],
        unique=False,
    )
    op.create_index(
        "ix_payments_scope_received",
        "payments",
        ["tenant_id", "environment_id", "received_on"],
        unique=False,
    )
    # ### end Alembic commands ###
    _optional_vector_columns()
    op.execute(
        sa.text(
            "INSERT INTO platform_products (key, name, description, category, features) "
            "VALUES ('pi', 'PI', :description, 'ai', "
            "ARRAY['text','voice','vision','knowledge','orders','quotes','handoff']) "
            "ON CONFLICT (key) DO NOTHING"
        ).bindparams(
            description=(
                "AI WhatsApp customer assistant: answers questions from verified company data, "
                "checks stock, drafts orders and quotes, and hands off to your team."
            )
        )
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_payments_scope_received", table_name="payments")
    op.drop_index("ix_payments_invoice", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_invoice_lines_invoice", table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index("ix_pi_tool_calls_scope_created", table_name="pi_tool_calls")
    op.drop_index("ix_pi_tool_calls_run", table_name="pi_tool_calls")
    op.drop_table("pi_tool_calls")
    op.drop_index("ix_order_lines_variant", table_name="order_lines")
    op.drop_index("ix_order_lines_order", table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_index(
        "uq_invoices_order",
        table_name="invoices",
        postgresql_where=sa.text("order_id IS NOT NULL AND status <> 'void'"),
    )
    op.drop_index("ix_invoices_scope_status", table_name="invoices")
    op.drop_index("ix_invoices_customer", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index(
        "uq_stock_movements_idempotency",
        table_name="stock_movements",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("ix_stock_movements_variant_created", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_table("stock_levels")
    op.drop_index("ix_quote_lines_quote", table_name="quote_lines")
    op.drop_table("quote_lines")
    op.drop_index("ix_pi_agent_runs_scope_created", table_name="pi_agent_runs")
    op.drop_table("pi_agent_runs")
    op.drop_index(
        "uq_orders_quote",
        table_name="orders",
        postgresql_where=sa.text("quote_id IS NOT NULL AND status <> 'cancelled'"),
    )
    op.drop_index(
        "uq_orders_idempotency",
        table_name="orders",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("ix_orders_scope_status", table_name="orders")
    op.drop_index("ix_orders_customer", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_quotes_scope_status", table_name="quotes")
    op.drop_index("ix_quotes_customer", table_name="quotes")
    op.drop_table("quotes")
    op.drop_index(
        "uq_pi_pending_actions_one_pending",
        table_name="pi_pending_actions",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_table("pi_pending_actions")
    op.drop_index(
        "uq_pi_messages_provider_id",
        table_name="pi_messages",
        postgresql_where=sa.text("provider_message_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_pi_messages_idempotency",
        table_name="pi_messages",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("ix_pi_messages_conversation", table_name="pi_messages")
    op.drop_index(
        "ix_pi_messages_body_trgm",
        table_name="pi_messages",
        postgresql_using="gin",
        postgresql_ops={"body": "gin_trgm_ops"},
    )
    op.drop_table("pi_messages")
    op.drop_index(
        "uq_pi_handoffs_one_active",
        table_name="pi_handoffs",
        postgresql_where=sa.text("status IN ('open', 'assigned', 'in_progress')"),
    )
    op.drop_index("ix_pi_handoffs_scope_status", table_name="pi_handoffs")
    op.drop_table("pi_handoffs")
    op.drop_index(
        "ix_knowledge_chunks_search", table_name="knowledge_chunks", postgresql_using="gin"
    )
    op.drop_index("ix_knowledge_chunks_scope", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_catalog_variants_product", table_name="catalog_variants")
    op.drop_table("catalog_variants")
    op.drop_index("ix_sales_leads_scope_stage", table_name="sales_leads")
    op.drop_index("ix_sales_leads_conversation", table_name="sales_leads")
    op.drop_table("sales_leads")
    op.drop_index("ix_pi_memories_customer", table_name="pi_memories")
    op.drop_table("pi_memories")
    op.drop_index(
        "uq_pi_conversations_open_contact",
        table_name="pi_conversations",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index("ix_pi_conversations_scope_last", table_name="pi_conversations")
    op.drop_index("ix_pi_conversations_customer", table_name="pi_conversations")
    op.drop_table("pi_conversations")
    op.drop_table("pi_agent_versions")
    op.drop_table("pi_agent_tools")
    op.drop_table("notification_reads")
    op.drop_index("ix_knowledge_documents_source", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_employees_scope_status", table_name="employees")
    op.drop_index("ix_employees_department", table_name="employees")
    op.drop_table("employees")
    op.drop_index("ix_customer_notes_customer", table_name="customer_notes")
    op.drop_table("customer_notes")
    op.drop_index("ix_customer_activities_customer", table_name="customer_activities")
    op.drop_table("customer_activities")
    op.drop_index("ix_catalog_products_scope_status", table_name="catalog_products")
    op.drop_index(
        "ix_catalog_products_name_trgm",
        table_name="catalog_products",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_table("catalog_products")
    op.drop_index("ix_whatsapp_webhook_events_status", table_name="whatsapp_webhook_events")
    op.drop_index("ix_whatsapp_webhook_events_scope_created", table_name="whatsapp_webhook_events")
    op.drop_table("whatsapp_webhook_events")
    op.drop_table("whatsapp_connections")
    op.drop_table("role_permissions")
    op.drop_table("pi_settings")
    op.drop_table("pi_agents")
    op.drop_index(
        "uq_notifications_dedupe",
        table_name="notifications",
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.drop_index("ix_notifications_scope_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_membership_roles_role", table_name="membership_roles")
    op.drop_table("membership_roles")
    op.drop_table("knowledge_sources")
    op.drop_index(
        "uq_inventory_locations_default",
        table_name="inventory_locations",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_table("inventory_locations")
    op.drop_index("ix_expenses_scope_incurred", table_name="expenses")
    op.drop_table("expenses")
    op.drop_table("environment_product_installations")
    op.drop_table("document_sequences")
    op.drop_index(
        "uq_customers_whatsapp",
        table_name="customers",
        postgresql_where=sa.text("whatsapp_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_customers_phone", table_name="customers", postgresql_where=sa.text("phone IS NOT NULL")
    )
    op.drop_index("ix_customers_scope_created", table_name="customers")
    op.drop_index(
        "ix_customers_name_trgm",
        table_name="customers",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_table("customers")
    op.drop_table("catalog_categories")
    op.drop_table("business_settings")
    op.drop_index("ix_audit_events_tenant_entity", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_created", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_ai_usage_events_scope_created", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_run", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")
    op.drop_table("user_credentials")
    op.drop_table("tenant_product_installations")
    op.drop_table("roles")
    op.drop_table("navigation_preferences")
    op.drop_index(
        "uq_environments_one_default",
        table_name="environments",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_table("environments")
    op.drop_index("ix_auth_sessions_user_active", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("platform_products")
    # ### end Alembic commands ###
