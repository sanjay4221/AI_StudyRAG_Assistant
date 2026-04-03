"""
tests/conftest.py
-----------------
Shared pytest fixtures used across all test files.

Key concepts:
  fixture     → a reusable setup/teardown function
                decorated with @pytest.fixture
                pytest injects it automatically into test functions

  scope       → how long the fixture lives:
                "function" = recreated for every test  (default)
                "session"  = created once for all tests

  yield       → everything before yield = setup
                everything after yield  = teardown

What we create here:
  db_session   → fresh in-memory SQLite DB per test (no real DB touched)
  client       → FastAPI TestClient with the test DB wired in
  test_user    → a registered user (used by most tests)
  auth_headers → JWT headers for that user (used by protected routes)
  sample_pdf   → a tiny real PDF file for upload tests
"""

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use in-memory SQLite for tests — fast, isolated, never touches real studyrag.db
TEST_DB_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once for the entire test session."""
    from db.models import Base
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """
    Fresh DB session per test — rolls back after each test.
    This means every test starts with a clean slate.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """
    FastAPI TestClient with the test DB injected.
    Overrides get_db() dependency so routes use our test session.
    """
    from main import app
    from db.database import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    """
    Create a test user in the DB and return their data.
    Used by tests that need an existing registered user.
    """
    from db.crud import create_user
    from core.security import hash_password

    user = create_user(
        db=db_session,
        email="student@test.com",
        hashed_password=hash_password("testpass123"),
        full_name="Test Student",
    )
    return user


@pytest.fixture
def admin_user(db_session):
    """Create a test admin user."""
    from db.crud import create_user, set_admin
    from core.security import hash_password

    user = create_user(
        db=db_session,
        email="admin@test.com",
        hashed_password=hash_password("adminpass123"),
        full_name="Test Admin",
    )
    return set_admin(db_session, user, True)


@pytest.fixture
def auth_headers(test_user):
    """JWT Authorization headers for the test user."""
    from core.security import create_access_token
    token = create_access_token(test_user.id, test_user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user):
    """JWT Authorization headers for the admin user."""
    from core.security import create_access_token
    token = create_access_token(admin_user.id, admin_user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_pdf(tmp_path):
    """
    Create a minimal but real PDF file for upload tests.
    Uses reportlab if available, otherwise creates a raw PDF manually.
    Returns the file path as a string.
    """
    pdf_path = tmp_path / "test_document.pdf"

    # Minimal valid PDF — no external library needed
    # This is the smallest possible valid PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test document content for RAG testing.) Tj ET
endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000370 00000 n

trailer
<< /Size 6 /Root 1 0 R >>
startxref
441
%%EOF"""

    pdf_path.write_bytes(pdf_content)
    return str(pdf_path)
