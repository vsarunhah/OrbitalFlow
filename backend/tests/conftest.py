import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

# Set a test encryption key before anything imports the encryption module
settings.app_encryption_key = Fernet.generate_key().decode()

from app.database import Base, get_db  # noqa: E402
from app.encryption import reset_fernet  # noqa: E402
from app.main import app  # noqa: E402

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(autouse=True)
def setup_db():
    reset_fernet()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_header(client):
    """Register a user and return an Authorization header dict."""
    r = client.post("/auth/register", json={
        "tenant_name": "TestCo",
        "email": "test@test.com",
        "password": "testpass",
    })
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
