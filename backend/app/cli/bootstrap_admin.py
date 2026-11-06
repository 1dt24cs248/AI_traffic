"""One-time, interactive administrator account bootstrap."""

from __future__ import annotations

import getpass
import sys
import warnings

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.database import SessionLocal
from app.models.user import User, UserRole

_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_BOOTSTRAP_LOCK_KEY = 0x41544650424F4F54
_CONFIRMATION_PHRASE = "CREATE ADMIN"
_MAX_BCRYPT_PASSWORD_BYTES = 72
_MIN_PASSWORD_LENGTH = 12


class BootstrapError(Exception):
    """An expected refusal while bootstrapping the administrator account."""


class AdministratorAlreadyExistsError(BootstrapError):
    """Raised when the database already contains an administrator."""


class EmailAlreadyRegisteredError(BootstrapError):
    """Raised when the requested email belongs to an existing account."""


def _require_confirmation(confirmation: str, email: str) -> None:
    if confirmation.strip() != _CONFIRMATION_PHRASE:
        raise BootstrapError(
            f"Confirmation did not match; no account was created for {email}."
        )


def _validate_credentials(email: str, full_name: str, password: str) -> tuple[str, str]:
    try:
        normalized_email = str(_EMAIL_ADAPTER.validate_python(email.strip()))
    except (AttributeError, ValidationError) as exc:
        raise BootstrapError("Enter a valid email address.") from exc

    normalized_name = full_name.strip()
    if not 2 <= len(normalized_name) <= 255:
        raise BootstrapError("Full name must be between 2 and 255 characters.")

    if len(password) < _MIN_PASSWORD_LENGTH:
        raise BootstrapError("Password must contain at least 12 characters.")

    try:
        password_bytes = password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BootstrapError("Password contains unsupported characters.") from exc
    if len(password_bytes) > _MAX_BCRYPT_PASSWORD_BYTES:
        raise BootstrapError("Password must be at most 72 UTF-8 bytes for bcrypt.")

    return normalized_email, normalized_name


def create_admin(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
) -> User:
    """Create the initial administrator under a transaction-scoped lock."""
    normalized_email, normalized_name = _validate_credentials(email, full_name, password)
    hashed_password = hash_password(password)
    dialect = db.get_bind().dialect.name

    if dialect not in {"postgresql", "sqlite"}:
        raise BootstrapError(
            "Administrator bootstrap supports PostgreSQL and SQLite databases only."
        )
    if db.in_transaction():
        raise BootstrapError("Administrator bootstrap requires a fresh database session.")

    try:
        if dialect == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _BOOTSTRAP_LOCK_KEY},
            )
        else:
            # Acquire SQLite's write lock before checking so concurrent attempts serialize.
            db.execute(text("BEGIN IMMEDIATE"))

        if db.query(User).filter(User.role == UserRole.ADMIN).first() is not None:
            raise AdministratorAlreadyExistsError(
                "An administrator already exists; bootstrap is one-time only."
            )

        if db.query(User).filter(User.email == normalized_email).first() is not None:
            raise EmailAlreadyRegisteredError(
                "That email already belongs to an account; no administrator was created."
            )

        administrator = User(
            email=normalized_email,
            full_name=normalized_name,
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(administrator)
        db.flush()
        db.commit()
        return administrator
    except Exception:
        db.rollback()
        raise


def _read_password(prompt: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def main() -> int:
    """Prompt for credentials and create the administrator only after confirmation."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "Administrator bootstrap requires an interactive terminal.",
            file=sys.stderr,
        )
        return 1

    try:
        email = input("Administrator email: ")
        full_name = input("Administrator full name: ")
        password = _read_password("Administrator password (input hidden): ")
        password_confirmation = _read_password("Confirm administrator password: ")
        normalized_email, _ = _validate_credentials(email, full_name, password)
        if password != password_confirmation:
            raise BootstrapError("Passwords do not match.")
        confirmation = input(
            f"Type {_CONFIRMATION_PHRASE} to create the administrator "
            f"account for {normalized_email}: "
        )
        _require_confirmation(confirmation, normalized_email)
    except (EOFError, getpass.GetPassWarning):
        print(
            "Secure credential input failed or was cancelled; no account was created.",
            file=sys.stderr,
        )
        return 1
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    db: Session | None = None
    try:
        db = SessionLocal()
        administrator = create_admin(
            db,
            email=email,
            full_name=full_name,
            password=password,
        )
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Database operation failed; inspect the database before retrying.",
            file=sys.stderr,
        )
        return 1
    finally:
        if db is not None:
            db.close()

    print(f"Administrator account created for {administrator.email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
