"""Create the *_test database next to the app database and migrate it to head.

Prints the test DATABASE_URL. scripts/test.sh exports it before running pytest,
so the test session, which deletes all users and items, never touches app data.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import URL, create_engine, make_url, text

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def get_test_database_url() -> URL:
    url = make_url(str(settings.DATABASE_URL))
    name = url.database or ""
    return url if name.endswith("_test") else url.set(database=f"{name}_test")


def create_database(url: URL) -> None:
    name = url.database
    if not name:
        raise ValueError("DATABASE_URL must include a database name")
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        ).scalar()
        if not exists:
            quoted = conn.dialect.identifier_preparer.quote(name)
            conn.execute(text(f"CREATE DATABASE {quoted}"))
    server.dispose()


def migrate(url: URL, revision: str = "head") -> None:
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    subprocess.run(
        ["alembic", "upgrade", revision],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        stdout=sys.stderr,
    )


def main() -> None:
    url = get_test_database_url()
    create_database(url)
    migrate(url)
    sys.stdout.write(url.render_as_string(hide_password=False) + "\n")


if __name__ == "__main__":
    main()
