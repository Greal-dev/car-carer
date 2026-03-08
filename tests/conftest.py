"""Shared test fixtures — in-memory SQLite database."""

import os
import sys

# Set dummy API keys before any imports
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["OPENROUTER_API_KEY"] = "test-key"
os.environ["DATABASE_URL"] = "sqlite://"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
# Import all models so Base.metadata knows about them
from app.models import (  # noqa: F401
    User, Vehicle, ShareLink, Document,
    MaintenanceEvent, MaintenanceItem,
    CTReport, CTDefect, Conversation, Message,
    FuelEntry, Warranty,
)
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(client):
    """Client with an authenticated user."""
    res = client.post("/api/auth/register", json={"email": "test@test.com", "password": "test123"})
    assert res.status_code == 200, f"Register failed: {res.json()}"
    return client
