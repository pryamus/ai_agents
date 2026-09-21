Ниже — минимальная рабочая реализация CRUD для сущности `Ticket` на FastAPI + SQLAlchemy + PostgreSQL.

## Структура проекта

```text
app/
├── __init__.py
├── database.py
├── models.py
├── schemas.py
├── crud.py
├── main.py
└── routers/
    ├── __init__.py
    └── tickets.py
requirements.txt
```

## `requirements.txt`

```txt
fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
```

## `app/database.py`

```python
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/support_db",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## `app/models.py`

```python
import enum

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text, text
from sqlalchemy.sql import func

from .database import Base


class TicketStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(255), nullable=False)

    description = Column(Text, nullable=False)

    status = Column(
        Enum(TicketStatus, name="ticket_status"),
        nullable=False,
        default=TicketStatus.new,
        server_default=text("'new'"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    employee_id = Column(Integer, nullable=False, index=True)
```

Если в системе уже есть таблица `employees`, можно добавить внешний ключ:

```python
# employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
```

## `app/schemas.py`

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import TicketStatus


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    status: TicketStatus = TicketStatus.new
    employee_id: int


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    status: TicketStatus | None = None
    employee_id: int | None = None


class TicketRead(BaseModel):
    id: int
    title: str
    description: str
    status: TicketStatus
    created_at: datetime
    employee_id: int

    model_config = ConfigDict(from_attributes=True)
```

## `app/crud.py`

```python
from sqlalchemy.orm import Session

from . import models, schemas


def create_ticket(db: Session, data: schemas.TicketCreate) -> models.Ticket:
    ticket = models.Ticket(**data.model_dump())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def get_tickets(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Ticket]:
    return (
        db.query(models.Ticket)
        .order_by(models.Ticket.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_ticket(db: Session, ticket_id: int) -> models.Ticket | None:
    return (
        db.query(models.Ticket)
        .filter(models.Ticket.id == ticket_id)
        .first()
    )


def update_ticket(
    db: Session,
    ticket_id: int,
    data: schemas.TicketUpdate,
) -> models.Ticket | None:
    ticket = get_ticket(db, ticket_id)

    if ticket is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(ticket, field, value)

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket_id: int) -> models.Ticket | None:
    ticket = get_ticket(db, ticket_id)

    if ticket is None:
        return None

    db.delete(ticket)
    db.commit()
    return ticket
```

## `app/routers/tickets.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post(
    "",
    response_model=schemas.TicketRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(
    ticket: schemas.TicketCreate,
    db: Session = Depends(get_db),
):
    return crud.create_ticket(db, ticket)


@router.get("", response_model=list[schemas.TicketRead])
def list_tickets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return crud.get_tickets(db, skip=skip, limit=limit)


@router.get("/{ticket_id}", response_model=schemas.TicketRead)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    ticket = crud.get_ticket(db, ticket_id)

    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return ticket


@router.patch("/{ticket_id}", response_model=schemas.TicketRead)
def update_ticket(
    ticket_id: int,
    ticket: schemas.TicketUpdate,
    db: Session = Depends(get_db),
):
    updated_ticket = crud.update_ticket(db, ticket_id, ticket)

    if updated_ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return updated_ticket


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    deleted_ticket = crud.delete_ticket(db, ticket_id)

    if deleted_ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return None
```

## `app/main.py`

```python
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
```

## Запуск

```bash
pip install -r requirements.txt

export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/support_db"

uvicorn app.main:app --reload
```

Документация Swagger будет доступна по адресу:

```text
http://127.0.0.1:8000/docs
```

## Примеры запросов

### Создать заявку

```http
POST /tickets
Content-Type: application/json
```

```json
{
  "title": "Не включается ноутбук",
  "description": "При нажатии кнопки питания нет реакции",
  "employee_id": 123
}
```

Статус по умолчанию будет `new`.

### Получить список заявок

```http
GET /tickets?skip=0&limit=10
```

### Получить заявку по ID

```http
GET /tickets/1
```

### Изменить заявку

```http
PATCH /tickets/1
Content-Type: application/json
```

```json
{
  "status": "in_progress"
}
```

### Удалить заявку

```http
DELETE /tickets/1
```

Статусы заявки ограничены значениями:

```text
new
in_progress
resolved
closed
```