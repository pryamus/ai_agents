from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models, schemas


class TicketNotFoundError(Exception):
    """Бизнес-ошибка: тикет не найден. HTTP-слой мапит её в 404."""

    def __init__(self, ticket_id: int) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} not found")


class TicketService:
    """
    Сервисный слой: бизнес-логика и границы транзакций поверх CRUD.
    Роутеры не обращаются к crud напрямую — только через этот сервис.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_ticket(self, data: schemas.TicketCreate) -> models.Ticket:
        return await crud.create_ticket(self.db, data)

    async def list_tickets(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[models.Ticket]:
        return await crud.get_tickets(self.db, skip=skip, limit=limit)

    async def get_ticket(self, ticket_id: int) -> models.Ticket:
        ticket = await crud.get_ticket(self.db, ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    async def update_ticket(
        self,
        ticket_id: int,
        data: schemas.TicketUpdate,
    ) -> models.Ticket:
        ticket = await crud.update_ticket(self.db, ticket_id, data)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    async def delete_ticket(self, ticket_id: int) -> models.Ticket:
        ticket = await crud.delete_ticket(self.db, ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket
