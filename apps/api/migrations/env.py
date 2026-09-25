import asyncio
from typing import Any

from alembic import context
from sqlalchemy.engine import Connection

from app import models  # noqa: F401 -- register every mapped model for autogeneration
from app.core.config import get_settings
from app.core.database import Base, create_engine, resolve_database
from app.modules.integrations import models as integration_models  # noqa: F401

target_metadata = Base.metadata

# Optional pgvector columns are created by migration only when the extension exists
# (ADR 0005). They are intentionally unmapped, so autogenerate must not drop them.
OPTIONAL_COLUMNS = {("knowledge_chunks", "embedding"), ("pi_memories", "embedding")}


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    if type_ == "column" and reflected and compare_to is None:
        table = getattr(getattr(obj, "table", None), "name", None)
        return (table, name) not in OPTIONAL_COLUMNS
    if (
        type_ == "index"
        and reflected
        and compare_to is None
        and name
        and name.endswith("_embedding")
    ):
        return False
    return True


def migration_url() -> str:
    """Neon: migrations run on the direct endpoint, not the PgBouncer pooler."""
    settings = get_settings()
    direct = settings.migration_database_url
    if direct is not None and direct.get_secret_value():
        return direct.get_secret_value()
    return settings.database_url.get_secret_value()


def offline() -> None:
    settings = get_settings()
    context.configure(
        url=resolve_database(settings, migration_url()).url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    engine = create_engine(get_settings(), migration_url())

    def run(connection: Connection) -> None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()

    try:
        async with engine.connect() as connection:
            await connection.run_sync(run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    offline()
else:
    asyncio.run(online())
