from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Applied at connect time to every app connection; Alembic uses its own engine without it.
_APP_CONNECT_ARGS = {
    'options': f'-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}',
    # Fail fast when the DB host is unreachable instead of waiting on the OS TCP timeout.
    'connect_timeout': 3,
}

sync_engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
    connect_args=_APP_CONNECT_ARGS,
)
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

worker_engine = create_engine(
    settings.DATABASE_URL,
    pool_size=2,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
    connect_args=_APP_CONNECT_ARGS,
)
WorkerSessionLocal = sessionmaker(
    bind=worker_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=3,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=_APP_CONNECT_ARGS,
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
