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
