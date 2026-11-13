from datetime import timedelta

from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.security import create_access_token
from app.models import User, UserCreate, UserUpdate
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string

ME_URL = f"{settings.API_V1_STR}/users/me"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_unauthorized(r: Response, detail: str) -> None:
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.json() == {"detail": detail}


def create_user_with_session(
    client: TestClient, db: Session
) -> tuple[User, dict[str, str]]:
    email, password = random_email(), random_lower_string()
    user = crud.create_user(
        session=db, user_create=UserCreate(email=email, password=password)
    )
    headers = user_authentication_headers(client=client, email=email, password=password)
    return user, headers


def test_garbage_token_is_unauthorized(client: TestClient) -> None:
    r = client.get(ME_URL, headers=bearer("garbage"))
    assert_unauthorized(r, "Could not validate credentials")


def test_expired_token_is_unauthorized(client: TestClient, db: Session) -> None:
    user, _ = create_user_with_session(client, db)
    token = create_access_token(user.id, expires_delta=timedelta(minutes=-1))
    r = client.get(ME_URL, headers=bearer(token))
    assert_unauthorized(r, "Could not validate credentials")


def test_session_of_deleted_user_is_unauthorized(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_session(client, db)
    db.delete(user)
    db.commit()
    r = client.get(ME_URL, headers=headers)
    assert_unauthorized(r, "User not found")


def test_deactivation_ends_existing_session(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_session(client, db)
    assert client.get(ME_URL, headers=headers).status_code == 200

    crud.update_user(session=db, db_user=user, user_in=UserUpdate(is_active=False))
    r = client.get(ME_URL, headers=headers)
    assert_unauthorized(r, "Inactive user")

    crud.update_user(session=db, db_user=user, user_in=UserUpdate(is_active=True))
    assert client.get(ME_URL, headers=headers).status_code == 200


def test_inactive_user_login_is_a_form_error(client: TestClient, db: Session) -> None:
    email, password = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, password=password, is_active=False),
    )
    r = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": email, "password": password},
    )
    assert r.status_code == 400
    assert r.json() == {"detail": "Inactive user"}
