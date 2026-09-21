import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# Драйвер: psycopg 3 (async-режим включается автоматически
# при использовании create_async_engine).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./example.db"
    # "postgresql+psycopg://userdb:userdb@192.168.1.88:5432/exampledb",
)

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

# expire_on_commit=False обязателен для async:
# иначе обращение к атрибутам после commit вызовет ленивую
# загрузку и MissingGreenlet.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
