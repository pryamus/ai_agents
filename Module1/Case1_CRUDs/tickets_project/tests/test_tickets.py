import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models, schemas
from app.database import Base
from app.main import health
from app.routers import tickets


@pytest.fixture
def db_session(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_health_endpoint():
    assert health() == {"status": "ok"}


def test_create_and_get_ticket(db_session):
    data = schemas.TicketCreate(
        title="Ошибка входа",
        description="Пользователь не может войти в систему",
        employee_id=101,
    )

    ticket = crud.create_ticket(db_session, data)

    assert ticket.id is not None
    assert ticket.title == "Ошибка входа"
    assert ticket.status == models.TicketStatus.new

    stored = crud.get_ticket(db_session, ticket.id)
    assert stored is not None
    assert stored.description == "Пользователь не может войти в систему"


def test_list_and_update_ticket(db_session):
    crud.create_ticket(
        db_session,
        schemas.TicketCreate(
            title="Первый тикет",
            description="Описание первого тикета",
            employee_id=1,
        ),
    )
    crud.create_ticket(
        db_session,
        schemas.TicketCreate(
            title="Второй тикет",
            description="Описание второго тикета",
            employee_id=2,
        ),
    )

    ticket_list = crud.get_tickets(db_session)
    assert len(ticket_list) == 2

    updated = crud.update_ticket(
        db_session,
        ticket_list[0].id,
        schemas.TicketUpdate(
            title="Обновлённый тикет",
            status=models.TicketStatus.in_progress,
        ),
    )

    assert updated is not None
    assert updated.title == "Обновлённый тикет"
    assert updated.status == models.TicketStatus.in_progress


def test_delete_ticket(db_session):
    ticket = crud.create_ticket(
        db_session,
        schemas.TicketCreate(
            title="Удаляемый тикет",
            description="Этот тикет будет удалён",
            employee_id=7,
        ),
    )

    deleted = crud.delete_ticket(db_session, ticket.id)

    assert deleted is not None
    assert deleted.id == ticket.id
    assert crud.get_ticket(db_session, ticket.id) is None


def test_ticket_router_logic(db_session):
    created = tickets.create_ticket(
        schemas.TicketCreate(
            title="API ticket",
            description="Created via direct router call",
            employee_id=42,
        ),
        db=db_session,
    )

    assert created.title == "API ticket"
    assert created.status == models.TicketStatus.new

    ticket_list = tickets.list_tickets(skip=0, limit=100, db=db_session)
    assert len(ticket_list) == 1

    fetched = tickets.get_ticket(created.id, db=db_session)
    assert fetched is not None and fetched.title == "API ticket"

    updated = tickets.update_ticket(
        created.id,
        schemas.TicketUpdate(
            status=models.TicketStatus.in_progress,
            employee_id=99,
        ),
        db=db_session,
    )
    assert updated is not None
    assert updated.status == models.TicketStatus.in_progress
    assert updated.employee_id == 99

    deleted = tickets.delete_ticket(created.id, db=db_session)
    assert deleted is None

    with pytest.raises(HTTPException) as exc_info:
        tickets.get_ticket(created.id, db=db_session)

    assert exc_info.value.status_code == 404


def test_invalid_ticket_data_raises_validation_error():
    with pytest.raises(ValidationError):
        schemas.TicketCreate(
            title="",
            description="Некорректное описание",
            employee_id=1,
        )

    with pytest.raises(ValidationError):
        schemas.TicketCreate(
            title="Корректный заголовок",
            description="",
            employee_id=1,
        )

    with pytest.raises(ValidationError):
        schemas.TicketUpdate(title="")


def test_missing_ticket_raises_404(db_session):
    with pytest.raises(HTTPException) as exc_info:
        tickets.get_ticket(999999, db=db_session)
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        tickets.update_ticket(
            999999,
            schemas.TicketUpdate(status=models.TicketStatus.resolved),
            db=db_session,
        )
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        tickets.delete_ticket(999999, db=db_session)
    assert exc_info.value.status_code == 404
