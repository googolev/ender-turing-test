"""Fill the local database with demo users and items.

Idempotent: existing users are skipped (their role and status are never
changed), and items are only added to users that have none yet.

Run inside the backend container:
    docker compose exec backend python -m app.seed_data
"""

import logging
from typing import Any

from sqlmodel import Session, func, select

from app import crud
from app.core.config import settings
from app.core.db import engine
from app.models import Item, ItemCreate, User, UserCreate, UserRole

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_PASSWORD = "password123"

USERS: list[dict[str, Any]] = [
    {
        "email": "manager@example.com",
        "full_name": "Maria Manager",
        "role": UserRole.MANAGER,
    },
    {"email": "alice@example.com", "full_name": "Alice Anderson"},
    {"email": "bob@example.com", "full_name": "Bob Brown"},
    {"email": "carol@example.com", "full_name": "Carol Clark"},
    {"email": "dave@example.com", "full_name": "Dave Davis"},
    {"email": "inactive@example.com", "full_name": "Ivan Inactive", "is_active": False},
]

ITEMS: dict[str, list[tuple[str, str | None]]] = {
    settings.FIRST_SUPERUSER: [
        ("Quarterly roadmap", "Plan for Q1: auth, roles, audit log"),
        ("Infrastructure budget", "Cloud costs review for the next year"),
    ],
    "manager@example.com": [
        ("Team onboarding checklist", "Accounts, laptops, access to repos"),
        ("Hiring pipeline", "Three open positions, two in final round"),
    ],
    "alice@example.com": [
        ("Fix login redirect", "After login the user lands on a blank page"),
        ("Dark mode polish", "Contrast issues in the sidebar"),
        ("Write API docs", None),
    ],
    "bob@example.com": [
        ("Customer call notes", "Asked for CSV export of items"),
        ("Invoice #1042", "Waiting for payment confirmation"),
    ],
    "carol@example.com": [
        ("Database backup check", "Verify nightly backups restore cleanly"),
        ("Upgrade PostgreSQL", "Move from 17 to 18 on staging first"),
        ("Rotate secrets", "SECRET_KEY and SMTP password"),
        ("Load test", "Target 500 rps on /items"),
    ],
    "dave@example.com": [
        ("Marketing landing copy", "Draft headline and three feature blocks"),
    ],
    "inactive@example.com": [
        ("Old draft", "Left over from a former employee"),
    ],
}


def seed(session: Session) -> None:
    for data in USERS:
        if crud.get_user_by_email(session=session, email=data["email"]):
            logger.info("User %s exists, skipping", data["email"])
            continue
        crud.create_user(
            session=session,
            user_create=UserCreate(password=DEMO_PASSWORD, **data),
        )
        logger.info("Created user %s", data["email"])

    for email, items in ITEMS.items():
        user = crud.get_user_by_email(session=session, email=email)
        if user is None:
            continue
        count = session.exec(
            select(func.count()).select_from(Item).where(Item.owner_id == user.id)
        ).one()
        if count:
            logger.info("User %s already has %d items, skipping", email, count)
            continue
        for title, description in items:
            crud.create_item(
                session=session,
                item_in=ItemCreate(title=title, description=description),
                owner_id=user.id,
            )
        logger.info("Created %d items for %s", len(items), email)

    users = session.exec(select(func.count()).select_from(User)).one()
    total_items = session.exec(select(func.count()).select_from(Item)).one()
    logger.info("Done: %d users, %d items in database", users, total_items)


def main() -> None:
    with Session(engine) as session:
        seed(session)


if __name__ == "__main__":
    main()
