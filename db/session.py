from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import config
from db.models import Base

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {},
    echo=config.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Get a database session (for direct usage outside FastAPI)"""
    return SessionLocal()
