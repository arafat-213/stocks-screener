import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/stock_ai"
)
engine = create_engine(
    DATABASE_URL,
    pool_size=10,  # Base connections kept alive
    max_overflow=20,  # Extra connections under burst load (backtest + pipeline concurrent)
    pool_pre_ping=True,  # CRITICAL: validates connection before use; prevents "server closed connection" errors
    pool_recycle=3600,  # Recycle connections every hour to avoid stale TCP state
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
