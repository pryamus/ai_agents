from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import models  # noqa: F401  (важно: импорт регистрирует модели в Base.metadata)
from .database import Base, engine
from .routers import tickets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all для async-engine: выполняем через run_sync.
    # Только для разработки. В production — Alembic-миграции.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()


app = FastAPI(
    title="Technical Support Tickets API",
    lifespan=lifespan,
)

app.include_router(tickets.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
