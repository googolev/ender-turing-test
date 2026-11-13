"""The is_superuser -> role migration must keep everyone's access as it was.

Each test runs alembic against its own throwaway database, seeded at the
revision before roles existed, the way a populated production database is.
"""

import os
import subprocess
import sys
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import URL, create_engine, make_url, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
BEFORE_ROLES = "fe56fa70289e"

# email: (is_superuser, is_active)
EXISTING_USERS = {
    "admin@example.com": (True, True),
    "disabled-admin@example.com": (True, False),
    "member@example.com": (False, True),
    "disabled-member@example.com": (False, False),
}


@pytest.fixture
def db_url() -> Generator[URL]:
    """A throwaway database on the application's server, dropped afterwards."""
    app_url = make_url(str(settings.DATABASE_URL))
    url = app_url.set(database=f"migration_test_{uuid.uuid4().hex[:12]}")
    server = create_engine(
        app_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with server.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    try:
        yield url
    finally:
        with server.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        server.dispose()


def run_alembic(url: URL, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    subprocess.run(
        ["alembic", *args], cwd=BACKEND_DIR, env=env, check=True, stdout=sys.stderr
    )


def sql(url: URL, statement: str, **params: Any) -> list[Any]:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(statement), params)
            return list(result) if result.returns_rows else []
    finally:
        engine.dispose()


def seed_users_before_roles(url: URL) -> None:
    run_alembic(url, "upgrade", BEFORE_ROLES)
    for email, (is_superuser, is_active) in EXISTING_USERS.items():
        sql(
            url,
            'INSERT INTO "user" (id, email, hashed_password, is_superuser, is_active)'
            " VALUES (:id, :email, 'x', :is_superuser, :is_active)",
            id=uuid.uuid4(),
            email=email,
            is_superuser=is_superuser,
            is_active=is_active,
        )


def user_columns(url: URL) -> set[str]:
    rows = sql(
        url,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'user'",
    )
    return {row.column_name for row in rows}


def test_upgrade_maps_superusers_to_admins_and_keeps_active_status(
    db_url: URL,
) -> None:
    seed_users_before_roles(db_url)

    run_alembic(db_url, "upgrade", "head")

    rows = sql(db_url, 'SELECT email, role, is_active FROM "user"')
    assert {row.email: (row.role, row.is_active) for row in rows} == {
        "admin@example.com": ("admin", True),
        "disabled-admin@example.com": ("admin", False),
        "member@example.com": ("member", True),
        "disabled-member@example.com": ("member", False),
    }
    assert "is_superuser" not in user_columns(db_url)


def test_role_column_defaults_to_member_and_rejects_unknown_roles(
    db_url: URL,
) -> None:
    run_alembic(db_url, "upgrade", "head")

    sql(
        db_url,
        'INSERT INTO "user" (id, email, hashed_password, is_active)'
        " VALUES (:id, 'new@example.com', 'x', true)",
        id=uuid.uuid4(),
    )
    assert sql(db_url, 'SELECT role FROM "user"')[0].role == "member"

    with pytest.raises(IntegrityError):
        sql(db_url, "UPDATE \"user\" SET role = 'root'")


def test_downgrade_grants_superuser_only_to_admins(db_url: URL) -> None:
    seed_users_before_roles(db_url)
    run_alembic(db_url, "upgrade", "head")
    sql(
        db_url,
        "UPDATE \"user\" SET role = 'manager' WHERE email = 'member@example.com'",
    )

    run_alembic(db_url, "downgrade", BEFORE_ROLES)

    rows = sql(db_url, 'SELECT email, is_superuser, is_active FROM "user"')
    assert {row.email: (row.is_superuser, row.is_active) for row in rows} == {
        "admin@example.com": (True, True),
        "disabled-admin@example.com": (True, False),
        "member@example.com": (False, True),
        "disabled-member@example.com": (False, False),
    }
    assert "role" not in user_columns(db_url)
