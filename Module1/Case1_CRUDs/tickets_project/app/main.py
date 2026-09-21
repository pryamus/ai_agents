from fastapi import FastAPI

from . import models  # noqa: F401
from .database import Base, engine
from .routers import tickets

# Только для разработки.
# В production лучше использовать Alembic-миграции.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Technical Support Tickets API")

app.include_router(tickets.router)


@app.get("/health")
def health():
    return {"status": "ok"}
