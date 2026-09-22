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
