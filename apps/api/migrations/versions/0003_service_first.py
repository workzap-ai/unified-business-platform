"""Service offerings and environment business capabilities; preserve existing stock."""

import sqlalchemy as sa
from alembic import op

revision = "0003_service_first"
down_revision = "0002_business_platform_pi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_products",
        sa.Column("offering_type", sa.String(16), nullable=False, server_default="product"),
    )
    op.execute("""UPDATE catalog_products p SET offering_type = 'service'
        WHERE EXISTS (SELECT 1 FROM catalog_variants v WHERE v.product_id = p.id)
        AND NOT EXISTS (SELECT 1 FROM catalog_variants v WHERE v.product_id = p.id AND v.track_inventory)""")
    op.alter_column("catalog_products", "offering_type", server_default="service")
    op.create_check_constraint(
        "offering_type",
        "catalog_products",
        "offering_type IN ('service', 'product', 'hybrid', 'package')",
    )
    op.alter_column("catalog_variants", "track_inventory", server_default=sa.false())
    op.add_column(
        "business_settings",
        sa.Column(
            "business_type", sa.String(24), nullable=False, server_default="service_business"
        ),
    )
    op.execute("""INSERT INTO business_settings (id, tenant_id, environment_id, business_type)
        SELECT gen_random_uuid(), e.tenant_id, e.id, 'hybrid_business' FROM environments e
        WHERE EXISTS (SELECT 1 FROM catalog_variants v WHERE v.tenant_id=e.tenant_id AND v.environment_id=e.id AND v.track_inventory)
        OR EXISTS (SELECT 1 FROM inventory_locations l WHERE l.tenant_id=e.tenant_id AND l.environment_id=e.id)
        ON CONFLICT (tenant_id, environment_id) DO UPDATE SET business_type='hybrid_business'""")
    op.create_check_constraint(
        "business_type",
        "business_settings",
        "business_type IN ('service_business', 'product_business', 'hybrid_business')",
    )
    op.add_column(
        "orders",
        sa.Column("fulfillment_type", sa.String(16), nullable=False, server_default="product"),
    )
    op.execute("""UPDATE orders o SET fulfillment_type = CASE
        WHEN NOT EXISTS (SELECT 1 FROM order_lines l JOIN catalog_variants v ON v.id=l.variant_id WHERE l.order_id=o.id AND v.track_inventory) THEN 'service'
        WHEN EXISTS (SELECT 1 FROM order_lines l LEFT JOIN catalog_variants v ON v.id=l.variant_id WHERE l.order_id=o.id AND (v.id IS NULL OR NOT v.track_inventory)) THEN 'hybrid'
        ELSE 'product' END""")
    op.alter_column("orders", "fulfillment_type", server_default="service")
    op.create_check_constraint(
        "fulfillment_type", "orders", "fulfillment_type IN ('service', 'product', 'hybrid')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_orders_fulfillment_type"), "orders", type_="check")
    op.drop_column("orders", "fulfillment_type")
    op.drop_constraint(
        op.f("ck_business_settings_business_type"), "business_settings", type_="check"
    )
    op.drop_column("business_settings", "business_type")
    op.drop_constraint(op.f("ck_catalog_products_offering_type"), "catalog_products", type_="check")
    op.drop_column("catalog_products", "offering_type")
    op.alter_column("catalog_variants", "track_inventory", server_default=sa.true())
