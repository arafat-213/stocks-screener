import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_db, SessionLocal
from app.db import session as db_session_module
from app.db.models import Base

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Patch the session module's SessionLocal and engine
    # This ensures background tasks and other direct imports use the test DB
    old_session_local = db_session_module.SessionLocal
    old_engine = db_session_module.engine
    
    db_session_module.SessionLocal = TestingSessionLocal
    db_session_module.engine = engine
    
    # Create tables once per session
    Base.metadata.create_all(bind=engine)
    
    yield
    
    Base.metadata.drop_all(bind=engine)
    
    # Restore
    db_session_module.SessionLocal = old_session_local
    db_session_module.engine = old_engine

@pytest.fixture
def db():
    """Provides an isolated database session for a single test."""
    connection = engine.connect()
    # Begin a non-ORM transaction
    transaction = connection.begin()
    # Bind a new session to the connection
    session = TestingSessionLocal(bind=connection)
    
    # Run the test
    yield session

    # Roll back everything after the test
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db):
    """Provides a TestClient with the get_db dependency overridden to use the test database."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
