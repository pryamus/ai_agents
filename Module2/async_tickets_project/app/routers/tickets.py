from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .. import schemas
from ..database import get_db
from ..main import limiter
from ..services import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])


def get_ticket_service(db: AsyncSession = Depends(get_db)) -> TicketService:
    return TicketService(db)


@router.post(
    "",
    response_model=schemas.TicketRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def create_ticket(
    request: Request,
    response: Response,
    ticket: schemas.TicketCreate,
    service: TicketService = Depends(get_ticket_service),
):
    return await service.create_ticket(ticket)


@router.get("", response_model=list[schemas.TicketRead])
@limiter.limit("60/minute")
async def list_tickets(
    request: Request,
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service: TicketService = Depends(get_ticket_service),
):
    return await service.list_tickets(skip=skip, limit=limit)


@router.get("/{ticket_id}", response_model=schemas.TicketRead)
@limiter.limit("60/minute")
async def get_ticket(
    request: Request,
    response: Response,
    ticket_id: int,
    service: TicketService = Depends(get_ticket_service),
):
    return await service.get_ticket(ticket_id)


@router.patch("/{ticket_id}", response_model=schemas.TicketRead)
@limiter.limit("60/minute")
async def update_ticket(
    request: Request,
    response: Response,
    ticket_id: int,
    ticket: schemas.TicketUpdate,
    service: TicketService = Depends(get_ticket_service),
):
    return await service.update_ticket(ticket_id, ticket)


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def delete_ticket(
    request: Request,
    response: Response,
    ticket_id: int,
    service: TicketService = Depends(get_ticket_service),
):
    await service.delete_ticket(ticket_id)
    return None
