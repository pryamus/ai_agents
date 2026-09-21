# Prompt
```
код проекта сохрани как готовые python файлы для скачивания, а тестирование crud как файл requests.http используя синтаксис расширения rest api для vscode

```

Создать настоящие «скачиваемые» файлы я не могу — но могу оформить всё так, что их удобно сохранить одним движением: отдельным блоком на каждый файл с указанием полного пути, плюс скрипт-генератор, который создаст всю структуру и сами файлы у тебя локально. В конце — `requests.http` для REST Client в VS Code.

## Вариант 1. Скрипт-генератор проекта

Сохрани как `scaffold.py` в пустой папке и запусти `python scaffold.py` — он создаст всю структуру и файлы.

```python
# scaffold.py
from pathlib import Path

FILES: dict[str, str] = {}

FILES["requirements.txt"] = """fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
"""

FILES["app/__init__.py"] = ""

FILES["app/database.py"] = '''import os

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
'''

FILES["app/models.py"] = '''import enum

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
'''

FILES["app/schemas.py"] = '''from datetime import datetime

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
'''

FILES["app/crud.py"] = '''from sqlalchemy.orm import Session

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
'''

FILES["app/routers/__init__.py"] = ""

FILES["app/routers/tickets.py"] = '''from fastapi import APIRouter, Depends, HTTPException, Query, status
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
'''

FILES["app/main.py"] = '''from fastapi import FastAPI

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
'''

FILES["requests.http"] = r'''### Переменные окружения
@host = http://127.0.0.1:8000
@ticketId = 1

### Health check
GET {{host}}/health
Accept: application/json

### Создать заявку (полный набор полей)
# @name createTicket
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Не включается ноутбук",
  "description": "При нажатии кнопки питания нет реакции",
  "employee_id": 123
}

### Создать заявку со статусом in_progress
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Не работает корпоративная почта",
  "description": "Ошибка авторизации в Outlook",
  "status": "in_progress",
  "employee_id": 456
}

### Создать заявку с невалидным статусом (ожидаем 422)
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Тест невалидного статуса",
  "description": "Проверка валидации enum",
  "status": "unknown",
  "employee_id": 1
}

### Создать заявку без обязательного поля (ожидаем 422)
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Заявка без описания",
  "employee_id": 1
}

### Получить список заявок
GET {{host}}/tickets
Accept: application/json

### Получить список с пагинацией
GET {{host}}/tickets?skip=0&limit=10
Accept: application/json

### Получить список с некорректным limit (ожидаем 422)
GET {{host}}/tickets?limit=100000
Accept: application/json

### Получить одну заявку по ID
GET {{host}}/tickets/{{ticketId}}
Accept: application/json

### Получить несуществующую заявку (ожидаем 404)
GET {{host}}/tickets/999999
Accept: application/json

### Обновить заголовок и описание
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "title": "Ноутбук не включается (обновлено)",
  "description": "Проверены блок питания и батарея"
}

### Обновить только статус
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "in_progress"
}

### Перевести заявку в resolved
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "resolved"
}

### Закрыть заявку
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "closed"
}

### Обновить с невалидным статусом (ожидаем 422)
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "done"
}

### Обновить несуществующую заявку (ожидаем 404)
PATCH {{host}}/tickets/999999
Content-Type: application/json

{
  "status": "closed"
}

### Удалить заявку (ожидаем 204)
DELETE {{host}}/tickets/{{ticketId}}

### Удалить несуществующую заявку (ожидаем 404)
DELETE {{host}}/tickets/999999

### Проверить, что заявка удалена (ожидаем 404)
GET {{host}}/tickets/{{ticketId}}
Accept: application/json
'''


def main() -> None:
    for rel_path, content in FILES.items():
        path = Path(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"created: {rel_path}")


if __name__ == "__main__":
    main()
```

## Вариант 2. Файлы по отдельности

Если предпочитаешь сохранить вручную — вот те же файлы:

### `requirements.txt`

```txt
fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
```

### `app/__init__.py`

```python
```

### `app/database.py`

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

### `app/models.py`

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

### `app/schemas.py`

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

### `app/crud.py`

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

### `app/routers/__init__.py`

```python
```

### `app/routers/tickets.py`

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

### `app/main.py`

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

## `requests.http` (REST Client для VS Code)

Положи файл в корень проекта. Установи расширение **REST Client** (humao.rest-client). Над каждым запросом появится `Send Request`. Переменная `@ticketId` меняется вручную под реальный ID созданной заявки.

```http
### Переменные окружения
@host = http://127.0.0.1:8000
@ticketId = 1

### Health check
GET {{host}}/health
Accept: application/json

### Создать заявку (полный набор полей)
# @name createTicket
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Не включается ноутбук",
  "description": "При нажатии кнопки питания нет реакции",
  "employee_id": 123
}

### Создать заявку со статусом in_progress
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Не работает корпоративная почта",
  "description": "Ошибка авторизации в Outlook",
  "status": "in_progress",
  "employee_id": 456
}

### Создать заявку с невалидным статусом (ожидаем 422)
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Тест невалидного статуса",
  "description": "Проверка валидации enum",
  "status": "unknown",
  "employee_id": 1
}

### Создать заявку без обязательного поля (ожидаем 422)
POST {{host}}/tickets
Content-Type: application/json

{
  "title": "Заявка без описания",
  "employee_id": 1
}

### Получить список заявок
GET {{host}}/tickets
Accept: application/json

### Получить список с пагинацией
GET {{host}}/tickets?skip=0&limit=10
Accept: application/json

### Получить список с некорректным limit (ожидаем 422)
GET {{host}}/tickets?limit=100000
Accept: application/json

### Получить одну заявку по ID
GET {{host}}/tickets/{{ticketId}}
Accept: application/json

### Получить несуществующую заявку (ожидаем 404)
GET {{host}}/tickets/999999
Accept: application/json

### Обновить заголовок и описание
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "title": "Ноутбук не включается (обновлено)",
  "description": "Проверены блок питания и батарея"
}

### Обновить только статус
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "in_progress"
}

### Перевести заявку в resolved
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "resolved"
}

### Закрыть заявку
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "closed"
}

### Обновить с невалидным статусом (ожидаем 422)
PATCH {{host}}/tickets/{{ticketId}}
Content-Type: application/json

{
  "status": "done"
}

### Обновить несуществующую заявку (ожидаем 404)
PATCH {{host}}/tickets/999999
Content-Type: application/json

{
  "status": "closed"
}

### Удалить заявку (ожидаем 204)
DELETE {{host}}/tickets/{{ticketId}}

### Удалить несуществующую заявку (ожидаем 404)
DELETE {{host}}/tickets/999999

### Проверить, что заявка удалена (ожидаем 404)
GET {{host}}/tickets/{{ticketId}}
Accept: application/json
```

## Порядок запуска

```bash
# 1. Распаковать/создать файлы (например, через scaffold.py)
python scaffold.py

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Указать подключение к PostgreSQL
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/support_db"

# 4. Запустить сервер
uvicorn app.main:app --reload
```

Дальше в VS Code открываешь `requests.http`, нажимаешь **Send Request** над нужным блоком. Значение `@ticketId` подставляй из ответа на запрос `createTicket`.