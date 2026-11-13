"""Create the *_test database next to the app database and migrate it to head.

Prints the test DATABASE_URL. scripts/test.sh exports it before running pytest,
so the test session, which deletes all users and items, never touches app data.
The helpers are also used by the migration tests to manage throwaway databases.
"""

import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import URL, Connection, create_engine, make_url, text

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def get_test_database_url() -> URL:
    url = make_url(str(settings.DATABASE_URL))
    name = url.database or ""
    return url if name.endswith("_test") else url.set(database=f"{name}_test")


@contextmanager
def _server_connection(url: URL) -> Generator[tuple[Connection, str]]:
    """Connect to the server's maintenance database to manage url's database.

    Yields the connection and the quoted name of url's database.
    """
    if not url.database:
        raise ValueError("DATABASE_URL must include a database name")
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            yield conn, conn.dialect.identifier_preparer.quote(url.database)
    finally:
        server.dispose()


def create_database(url: URL) -> None:
    with _server_connection(url) as (conn, name):
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        ).scalar()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {name}"))


def drop_database(url: URL) -> None:
    with _server_connection(url) as (conn, name):
        conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


def run_alembic(url: URL, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    subprocess.run(
        ["alembic", *args], cwd=BACKEND_DIR, env=env, check=True, stdout=sys.stderr
    )


def main() -> None:
    url = get_test_database_url()
    create_database(url)
    run_alembic(url, "upgrade", "head")
    sys.stdout.write(url.render_as_string(hide_password=False) + "\n")


if __name__ == "__main__":
    main()
