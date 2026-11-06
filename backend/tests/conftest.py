"""
Backend test configuration.

Sets required environment variables before any module is imported so
that `python -m pytest` works from the `backend/` directory without
manually prefixing DATABASE_URL and JWT_SECRET_KEY.

The DATABASE_URL here is a dummy value — routing tests mock DB access;
the real Postgres connection is only required for integration tests.
"""
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://test:test@localhost:5432/test_traffic_db",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production")
