import pytest
from pydantic import ValidationError

from app import models, schemas
from app.services import TicketNotFoundError, TicketService


@pytest.fixture
def service(db_session) -> TicketService:
    return TicketService(db_session)


async def test_create_and_get_ticket(service: TicketService):
    created = await service.create_ticket(
        schemas.TicketCreate(
            title="Ошибка входа",
            description="Пользователь не может войти в систему",
            employee_id=101,
        )
    )

    assert created.id is not None
    assert created.title == "Ошибка входа"
    assert created.status == models.TicketStatus.new

    stored = await service.get_ticket(created.id)
    assert stored.description == "Пользователь не может войти в систему"


async def test_list_and_update_ticket(service: TicketService):
    await service.create_ticket(
        schemas.TicketCreate(
            title="Первый тикет",
            description="Описание первого тикета",
            employee_id=1,
        )
    )
    await service.create_ticket(
        schemas.TicketCreate(
            title="Второй тикет",
            description="Описание второго тикета",
            employee_id=2,
        )
    )

    ticket_list = await service.list_tickets()
    assert len(ticket_list) == 2

    updated = await service.update_ticket(
        ticket_list[0].id,
        schemas.TicketUpdate(
            title="Обновлённый тикет",
            status=models.TicketStatus.in_progress,
        ),
    )

    assert updated.title == "Обновлённый тикет"
    assert updated.status == models.TicketStatus.in_progress


async def test_delete_ticket(service: TicketService):
    created = await service.create_ticket(
        schemas.TicketCreate(
            title="Удаляемый тикет",
            description="Этот тикет будет удалён",
            employee_id=7,
        )
    )

    deleted = await service.delete_ticket(created.id)
    assert deleted.id == created.id

    with pytest.raises(TicketNotFoundError):
        await service.get_ticket(created.id)


async def test_missing_ticket_raises_not_found(service: TicketService):
    with pytest.raises(TicketNotFoundError) as exc_info:
        await service.get_ticket(999999)
    assert exc_info.value.ticket_id == 999999

    with pytest.raises(TicketNotFoundError):
        await service.update_ticket(
            999999,
            schemas.TicketUpdate(status=models.TicketStatus.resolved),
        )

    with pytest.raises(TicketNotFoundError):
        await service.delete_ticket(999999)


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
