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
