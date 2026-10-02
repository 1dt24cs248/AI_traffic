"""
Database connection setup.
Provides SessionLocal for dependency injection and Base for all ORM models.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, always closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
