from collections.abc import Callable, Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.core.permissions import Permission, has_permission
from app.models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def _unauthorized(detail: str) -> HTTPException:
    # 401 means "this session is no longer valid": the frontend logs out on it.
    # Missing permissions are 403 and must not end the session.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        raise _unauthorized("Could not validate credentials")
    # The user is re-read on every request, so deactivation and deletion
    # take effect for sessions that already hold a token.
    user = session.get(User, token_data.sub)
    if not user:
        raise _unauthorized("User not found")
    if not user.is_active:
        raise _unauthorized("Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def forbidden() -> HTTPException:
    return HTTPException(
        status_code=403, detail="The user doesn't have enough privileges"
    )


def require_permission(permission: Permission) -> Callable[[User], User]:
    """Dependency that lets the request through only if the user's role grants
    the permission: `dependencies=[Depends(require_permission(...))]`."""

    def check(current_user: CurrentUser) -> User:
        if not has_permission(current_user.role, permission):
            raise forbidden()
        return current_user

    return check
