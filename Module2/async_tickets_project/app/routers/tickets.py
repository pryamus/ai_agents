from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
    status,
)
from fastapi_cache.decorator import cache
from sqlalchemy.ext.asyncio import AsyncSession

from .. import schemas
from ..database import get_db
from ..main import limiter
from ..services import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])

# TTL кэша списка тикетов, сек. Явно задаётся в @cache; см. также init в main.py.
TICKETS_LIST_CACHE_TTL = 30


def get_ticket_service(db: AsyncSession = Depends(get_db)) -> TicketService:
    return TicketService(db)


def tickets_list_cache_key(
    func,
    namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args=(),
    kwargs=None,
) -> str:
    """Ключ кэша GET /tickets — только из пагинации skip/limit.

    В kwargs приходят и request-параметры, и разрешённый Depends(service):
    service нестабилен между запросами, поэтому в ключ не входит.
    namespace на входе = "tickets:" (prefix fastapi-cache2), итоговый ключ:
    tickets:list:skip={skip}:limit={limit} — по нему работает инвалидация
    FastAPICache.clear("list") -> KEYS tickets:list:*.
    """
    kwargs = kwargs or {}
    skip = kwargs.get("skip", 0)
    limit = kwargs.get("limit", 100)
    return f"{namespace}list:skip={skip}:limit={limit}"


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
@cache(expire=TICKETS_LIST_CACHE_TTL, key_builder=tickets_list_cache_key)
async def list_tickets(
    request: Request,
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service: TicketService = Depends(get_ticket_service),
):
    # Возвращаем JSON-ready dict'ы: JsonCoder (по умолчанию у fastapi-cache2)
    # кодирует ответ через json.dumps — ORM-объекты он сериализовать не умеет.
    # response_model на маршруте при этом валидирует dict'ы в TicketRead.
    tickets = await service.list_tickets(skip=skip, limit=limit)
    return [
        schemas.TicketRead.model_validate(t, from_attributes=True).model_dump(
            mode="json"
        )
        for t in tickets
    ]


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
