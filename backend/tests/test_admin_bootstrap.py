from uuid import uuid4
from unittest.mock import MagicMock
import warnings

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth_routes import register
from app.auth.dependencies import require_admin
from app.auth.security import verify_password
from app.cli.bootstrap_admin import (
    AdministratorAlreadyExistsError,
    BootstrapError,
    EmailAlreadyRegisteredError,
    _require_confirmation,
    create_admin,
)
from app.models.user import User, UserRole
from app.schemas.auth import UserRegister


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _user(*, email: str, role: UserRole) -> User:
    return User(
        id=uuid4(),
        email=email,
        full_name="Existing Account",
        hashed_password="not-used-in-this-test",
        role=role,
        is_active=True,
    )


def test_bootstrap_creates_hashed_admin_and_authorization_is_role_gated(db_session):
    password = "a-secure-admin-passphrase"

    administrator = create_admin(
        db_session,
        email=" Admin@Example.com ",
        full_name="  Initial Administrator  ",
        password=password,
    )

    assert administrator.email == "Admin@example.com"
    assert administrator.full_name == "Initial Administrator"
    assert administrator.role is UserRole.ADMIN
    assert administrator.is_active is True
    assert administrator.hashed_password != password
    assert verify_password(password, administrator.hashed_password)
    assert require_admin(administrator) is administrator

    with pytest.raises(HTTPException) as exc_info:
        require_admin(_user(email="user@example.test", role=UserRole.USER))
    assert exc_info.value.status_code == 403


def test_bootstrap_refuses_when_any_admin_already_exists(db_session):
    existing_admin = _user(email="disabled-admin@example.com", role=UserRole.ADMIN)
    existing_admin.is_active = False
    db_session.add(existing_admin)
    db_session.commit()

    with pytest.raises(AdministratorAlreadyExistsError):
        create_admin(
            db_session,
            email="second-admin@example.com",
            full_name="Second Administrator",
            password="another-secure-passphrase",
        )

    assert db_session.query(User).filter(User.role == UserRole.ADMIN).count() == 1


def test_bootstrap_does_not_promote_an_existing_user_email(db_session):
    db_session.add(_user(email="user@example.com", role=UserRole.USER))
    db_session.commit()

    with pytest.raises(EmailAlreadyRegisteredError):
        create_admin(
            db_session,
            email="user@example.com",
            full_name="Would Be Administrator",
            password="another-secure-passphrase",
        )

    assert db_session.query(User).filter(User.role == UserRole.ADMIN).count() == 0
    assert db_session.query(User).filter(User.email == "user@example.com").one().role is UserRole.USER


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "é" * 37,
    ],
)
def test_bootstrap_rejects_passwords_incompatible_with_security_policy(
    db_session,
    password,
):
    with pytest.raises(BootstrapError):
        create_admin(
            db_session,
            email="admin@example.com",
            full_name="Initial Administrator",
            password=password,
        )

    assert db_session.query(User).count() == 0


def test_bootstrap_rolls_back_database_failure_without_creating_admin(
    db_session,
    monkeypatch,
):
    def fail_commit():
        raise SQLAlchemyError("simulated commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(SQLAlchemyError, match="simulated commit failure"):
        create_admin(
            db_session,
            email="admin@example.com",
            full_name="Initial Administrator",
            password="a-secure-admin-passphrase",
        )

    assert db_session.query(User).count() == 0


def test_public_registration_cannot_assign_admin_role(db_session):
    payload = UserRegister.model_validate(
        {
            "email": "public@example.com",
            "full_name": "Public User",
            "password": "ordinary-user-password",
            "role": UserRole.ADMIN.value,
        }
    )

    registered_user = register(payload, db_session)

    assert registered_user.role is UserRole.USER


def test_bootstrap_requires_an_unopened_database_session(db_session):
    db_session.query(User).count()

    with pytest.raises(BootstrapError, match="fresh database session"):
        create_admin(
            db_session,
            email="admin@example.com",
            full_name="Initial Administrator",
            password="a-secure-admin-passphrase",
        )

    assert db_session.query(User).count() == 0


@pytest.mark.parametrize("confirmation", ["", "CREATE", "create admin"])
def test_bootstrap_rejects_missing_or_inexact_confirmation(confirmation):
    with pytest.raises(BootstrapError, match="no account was created"):
        _require_confirmation(confirmation, "admin@example.com")


def test_postgres_bootstrap_acquires_transaction_scoped_advisory_lock(monkeypatch):
    from app.cli import bootstrap_admin

    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.in_transaction.return_value = False
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(bootstrap_admin, "hash_password", lambda _password: "hashed")

    create_admin(
        db,
        email="admin@example.com",
        full_name="Initial Administrator",
        password="a-secure-admin-passphrase",
    )

    db.execute.assert_called_once()
    assert "pg_advisory_xact_lock" in str(db.execute.call_args.args[0])
    db.commit.assert_called_once()


def test_password_prompt_fails_closed_if_input_cannot_be_hidden(monkeypatch):
    from app.cli import bootstrap_admin

    def warn_that_input_is_visible(_prompt):
        warnings.warn("terminal cannot hide input", bootstrap_admin.getpass.GetPassWarning)
        return "password"

    monkeypatch.setattr(bootstrap_admin.getpass, "getpass", warn_that_input_is_visible)

    with pytest.raises(bootstrap_admin.getpass.GetPassWarning):
        bootstrap_admin._read_password("Password: ")
