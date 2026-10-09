"""FastAPI auth dependencies: bearer auth and role-based access control."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..models import User
from ..models.enums import Role
from .tokens import TokenError, decode_access_token

_bearer = HTTPBearer(auto_error=False)


def _user_from_credentials(db: Session, credentials: HTTPAuthorizationCredentials | None) -> User | None:
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError:
        return None
    user = db.scalar(select(User).where(User.id == int(payload.get("sub", 0))))
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    user = _user_from_credentials(db, credentials)
    if user is None:
        raise ApiException(401, "unauthorized", "A valid authentication token is required.")
    request.state.user = user
    return user


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    user = _user_from_credentials(db, credentials)
    request.state.user = user
    return user


def require_role(*roles: Role | str) -> Callable:
    allowed = {r.value if isinstance(r, Role) else r for r in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise ApiException(403, "forbidden", "You do not have permission to perform this action.")
        return user

    return dependency


require_admin = require_role(Role.ADMIN)
require_staff = require_role(Role.STAFF, Role.ADMIN)