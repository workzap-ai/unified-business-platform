from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.dependency_timeout_seconds,
        connect_args={
            "timeout": settings.dependency_timeout_seconds,
            "command_timeout": 10,
            "server_settings": {"statement_timeout": "10000"},
        },
        hide_parameters=True,
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # Services explicitly own commits; closing an uncommitted session rolls back.
    async with request.app.state.sessions() as session:
        yield session
