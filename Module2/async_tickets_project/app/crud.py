from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models, schemas


async def create_ticket(
    db: AsyncSession,
    data: schemas.TicketCreate,
) -> models.Ticket:
    ticket = models.Ticket(**data.model_dump())
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def get_tickets(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Ticket]:
    stmt = (
        select(models.Ticket)
        .order_by(models.Ticket.id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_ticket(
    db: AsyncSession,
    ticket_id: int,
) -> models.Ticket | None:
    stmt = select(models.Ticket).where(models.Ticket.id == ticket_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_ticket(
    db: AsyncSession,
    ticket_id: int,
    data: schemas.TicketUpdate,
) -> models.Ticket | None:
    ticket = await get_ticket(db, ticket_id)

    if ticket is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(ticket, field, value)

    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def delete_ticket(
    db: AsyncSession,
    ticket_id: int,
) -> models.Ticket | None:
    ticket = await get_ticket(db, ticket_id)

    if ticket is None:
        return None

    await db.delete(ticket)
    await db.commit()
    return ticket
