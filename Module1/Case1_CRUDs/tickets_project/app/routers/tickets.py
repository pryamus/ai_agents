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
