import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from . import models  # noqa: F401  (важно: импорт регистрирует модели в Base.metadata)
from .database import Base, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")


class FallbackLimiter(Limiter):
    """
    Limiter с resilient-поведением: если Redis недоступен, swallow_errors
    логирует ошибку и пропускает запрос без лимита. Дополнительно гарантирует
    наличие request.state.view_rate_limit, иначе _inject_headers падает
    с AttributeError после «проглоченной» ошибки storage.
    """

    def _check_request_limit(self, request, endpoint_func, in_middleware=True):
        super()._check_request_limit(request, endpoint_func, in_middleware)
        if not hasattr(request.state, "view_rate_limit"):
            request.state.view_rate_limit = None


# Redis — бэкенд для счётчиков лимитов.
# swallow_errors=True — fallback: при недоступности Redis ошибка
# логируется (logger "slowapi"), запросы пропускаются без rate limit,
# приложение не падает.
limiter = FallbackLimiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
    storage_uri=REDIS_URL,
    swallow_errors=True,
    headers_enabled=True,
)

# Импорт роутера ПОСЛЕ создания limiter:
# routers/tickets импортирует limiter из этого модуля.
from .routers import tickets  # noqa: E402


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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(tickets.router)


@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request, response: Response):
    return {"status": "ok"}
