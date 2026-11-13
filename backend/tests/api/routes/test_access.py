"""Access rules for the three roles, checked through the API.

Roles and permissions are written as the strings the API exposes, so these
tests pin the contract the frontend relies on.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models import Item, ItemCreate, User, UserCreate
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string

API = settings.API_V1_STR
ROLES = ["admin", "manager", "member"]
ALL_PERMISSIONS = [
    "items:all",
    "metrics:read",
    "system:manage",
    "users:manage",
    "users:read",
]
PERMISSIONS = {
    "admin": ALL_PERMISSIONS,
    "manager": ["metrics:read", "users:read"],
    "member": [],
}

Headers = dict[str, str]


def create_user(db: Session, role: str = "member") -> tuple[User, str]:
    password = random_lower_string()
    user_create = UserCreate.model_validate(
        {"email": random_email(), "password": password, "role": role}
    )
    user = crud.create_user(session=db, user_create=user_create)
    return user, password


def login(client: TestClient, user: User, password: str) -> Headers:
    return user_authentication_headers(
        client=client, email=user.email, password=password
    )


@pytest.fixture
def make_session(
    client: TestClient, db: Session
) -> Callable[[str], tuple[User, Headers]]:
    """Create a user with the given role and return it with a fresh token."""

    def make(role: str) -> tuple[User, Headers]:
        user, password = create_user(db, role)
        return user, login(client, user, password)

    return make


def create_item(db: Session, owner: User) -> Item:
    return crud.create_item(
        session=db,
        item_in=ItemCreate(title=random_lower_string()),
        owner_id=owner.id,
    )


def expected(admin: int, manager: int, member: int) -> list[Any]:
    return [
        pytest.param("admin", admin, id="admin"),
        pytest.param("manager", manager, id="manager"),
        pytest.param("member", member, id="member"),
    ]


# --- what each role is told it can do -------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_me_returns_role_and_permissions(
    client: TestClient, make_session: Callable[[str], tuple[User, Headers]], role: str
) -> None:
    _, headers = make_session(role)
    r = client.get(f"{API}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["role"] == role
    assert r.json()["permissions"] == PERMISSIONS[role]


# --- users -------------------------------------------------------------------


@pytest.mark.parametrize(("role", "status"), expected(200, 200, 403))
def test_list_users(
    client: TestClient,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    _, headers = make_session(role)
    assert client.get(f"{API}/users/", headers=headers).status_code == status


@pytest.mark.parametrize(("role", "status"), expected(200, 200, 403))
def test_read_other_user(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    other, _ = create_user(db)
    _, headers = make_session(role)
    assert client.get(f"{API}/users/{other.id}", headers=headers).status_code == status


@pytest.mark.parametrize("role", ROLES)
def test_read_own_user(
    client: TestClient, make_session: Callable[[str], tuple[User, Headers]], role: str
) -> None:
    me, headers = make_session(role)
    assert client.get(f"{API}/users/{me.id}", headers=headers).status_code == 200


@pytest.mark.parametrize(("role", "status"), expected(200, 403, 403))
def test_create_user(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    _, headers = make_session(role)
    email = random_email()
    r = client.post(
        f"{API}/users/",
        headers=headers,
        json={"email": email, "password": random_lower_string()},
    )
    assert r.status_code == status
    assert (crud.get_user_by_email(session=db, email=email) is not None) == (
        status == 200
    )


@pytest.mark.parametrize(("role", "status"), expected(200, 403, 403))
@pytest.mark.parametrize(
    "change",
    [{"full_name": "Changed Name"}, {"role": "manager"}, {"is_active": False}],
    ids=["name", "role", "is_active"],
)
def test_update_other_user(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
    change: dict[str, Any],
) -> None:
    other, _ = create_user(db)
    _, headers = make_session(role)
    r = client.patch(f"{API}/users/{other.id}", headers=headers, json=change)
    assert r.status_code == status
    db.refresh(other)
    field, value = next(iter(change.items()))
    assert (getattr(other, field) == value) == (status == 200)


@pytest.mark.parametrize(("role", "status"), expected(200, 403, 403))
def test_delete_other_user(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    other, _ = create_user(db)
    other_id = other.id
    _, headers = make_session(role)
    r = client.delete(f"{API}/users/{other_id}", headers=headers)
    assert r.status_code == status
    db.expire_all()
    assert (db.get(User, other_id) is None) == (status == 200)


@pytest.mark.parametrize(("role", "status"), expected(200, 403, 403))
def test_password_recovery_html_content(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    # The response embeds a password reset link for the target account.
    other, _ = create_user(db)
    _, headers = make_session(role)
    r = client.post(
        f"{API}/password-recovery-html-content/{other.email}", headers=headers
    )
    assert r.status_code == status


@pytest.mark.parametrize(("role", "status"), expected(201, 403, 403))
def test_send_test_email(
    client: TestClient,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    _, headers = make_session(role)
    with patch("app.api.routes.utils.send_email") as send_email:
        r = client.post(
            f"{API}/utils/test-email/",
            headers=headers,
            params={"email_to": random_email()},
        )
    assert r.status_code == status
    assert send_email.called == (status == 201)


# --- metrics -----------------------------------------------------------------


@pytest.mark.parametrize(("role", "status"), expected(200, 200, 403))
def test_metrics(
    client: TestClient,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    _, headers = make_session(role)
    r = client.get(f"{API}/metrics/", headers=headers)
    assert r.status_code == status
    if status == 200:
        metrics = r.json()
        assert set(metrics["users_by_role"]) == set(ROLES)
        assert sum(metrics["users_by_role"].values()) == metrics["users_total"]
        assert metrics["users_active"] <= metrics["users_total"]
        assert metrics["items_total"] >= 0


# --- items: everyone works with their own, only admin with everyone's ---------


@pytest.mark.parametrize("role", ROLES)
def test_list_items_shows_own_items_and_others_only_to_admin(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
) -> None:
    me, headers = make_session(role)
    own = create_item(db, me)
    other_owner, _ = create_user(db)
    others = create_item(db, other_owner)

    r = client.get(f"{API}/items/", headers=headers, params={"limit": 1000})
    assert r.status_code == 200
    items = r.json()["data"]
    ids = {item["id"] for item in items}
    assert str(own.id) in ids
    assert (str(others.id) in ids) == (role == "admin")
    if role != "admin":
        assert {item["owner_id"] for item in items} == {str(me.id)}


@pytest.mark.parametrize("role", ROLES)
def test_read_update_delete_own_item(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
) -> None:
    me, headers = make_session(role)
    item_id = create_item(db, me).id
    url = f"{API}/items/{item_id}"

    assert client.get(url, headers=headers).status_code == 200
    r = client.put(url, headers=headers, json={"title": "Renamed by owner"})
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed by owner"
    assert client.delete(url, headers=headers).status_code == 200
    db.expire_all()
    assert db.get(Item, item_id) is None


@pytest.mark.parametrize(("role", "status"), expected(200, 403, 403))
def test_read_others_item(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    other_owner, _ = create_user(db)
    item = create_item(db, other_owner)
    _, headers = make_session(role)
    assert client.get(f"{API}/items/{item.id}", headers=headers).status_code == status


@pytest.mark.parametrize(("role", "status"), expected(200, 403, 403))
def test_update_others_item(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    other_owner, _ = create_user(db)
    item = create_item(db, other_owner)
    original_title = item.title
    _, headers = make_session(role)
    r = client.put(
        f"{API}/items/{item.id}", headers=headers, json={"title": "Renamed by other"}
    )
    assert r.status_code == status
    db.refresh(item)
    assert item.title == ("Renamed by other" if status == 200 else original_title)


@pytest.mark.parametrize(("role", "status"), expected(200, 403, 403))
def test_delete_others_item(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
    status: int,
) -> None:
    other_owner, _ = create_user(db)
    item = create_item(db, other_owner)
    item_id = item.id
    _, headers = make_session(role)
    assert client.delete(f"{API}/items/{item_id}", headers=headers).status_code == (
        status
    )
    db.expire_all()
    assert (db.get(Item, item_id) is None) == (status == 200)


# --- access changes reach sessions that already hold a token ----------------


def test_role_change_applies_to_existing_token(
    client: TestClient,
    make_session: Callable[[str], tuple[User, Headers]],
) -> None:
    _, admin_headers = make_session("admin")
    user, headers = make_session("manager")

    def me() -> dict[str, Any]:
        r = client.get(f"{API}/users/me", headers=headers)
        assert r.status_code == 200
        data: dict[str, Any] = r.json()
        return data

    def set_role(role: str) -> None:
        r = client.patch(
            f"{API}/users/{user.id}", headers=admin_headers, json={"role": role}
        )
        assert r.status_code == 200

    assert client.get(f"{API}/users/", headers=headers).status_code == 200
    assert me()["permissions"] == PERMISSIONS["manager"]

    set_role("member")
    assert client.get(f"{API}/users/", headers=headers).status_code == 403
    assert client.get(f"{API}/metrics/", headers=headers).status_code == 403
    assert (me()["role"], me()["permissions"]) == ("member", PERMISSIONS["member"])

    set_role("admin")
    assert client.get(f"{API}/users/", headers=headers).status_code == 200
    assert (me()["role"], me()["permissions"]) == ("admin", PERMISSIONS["admin"])


# --- nobody can raise their own access --------------------------------------


def test_signup_cannot_choose_a_role(client: TestClient) -> None:
    r = client.post(
        f"{API}/users/signup",
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "role": "admin",
        },
    )
    assert r.status_code == 200
    assert r.json()["role"] == "member"


@pytest.mark.parametrize("role", ["manager", "member"])
def test_update_me_cannot_change_own_role(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    role: str,
) -> None:
    me, headers = make_session(role)
    client.patch(f"{API}/users/me", headers=headers, json={"role": "admin"})
    db.refresh(me)
    assert me.role == role
    assert client.get(f"{API}/users/me", headers=headers).json()["role"] == role


# --- an admin cannot lock themselves out ------------------------------------


@pytest.mark.parametrize(
    "change", [{"role": "member"}, {"is_active": False}], ids=["role", "is_active"]
)
def test_admin_cannot_change_own_access(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
    change: dict[str, Any],
) -> None:
    admin, headers = make_session("admin")
    r = client.patch(f"{API}/users/{admin.id}", headers=headers, json=change)
    assert r.status_code == 403
    db.refresh(admin)
    assert (admin.role, admin.is_active) == ("admin", True)


def test_admin_can_edit_own_profile_through_admin_form(
    client: TestClient,
    db: Session,
    make_session: Callable[[str], tuple[User, Headers]],
) -> None:
    # The admin edit form always sends role and is_active; unchanged values
    # must not be treated as an attempt to change access.
    admin, headers = make_session("admin")
    r = client.patch(
        f"{API}/users/{admin.id}",
        headers=headers,
        json={"full_name": "New Name", "role": "admin", "is_active": True},
    )
    assert r.status_code == 200
    db.refresh(admin)
    assert admin.full_name == "New Name"
