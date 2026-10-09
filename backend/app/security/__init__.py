"""Security primitives: password hashing, JWT, RBAC dependencies."""
from .deps import get_current_user, get_optional_user, require_admin, require_role, require_staff
from .passwords import hash_password, verify_password
from .tokens import TokenError, create_access_token, decode_access_token

__all__ = [
    "TokenError",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "get_optional_user",
    "hash_password",
    "require_admin",
    "require_role",
    "require_staff",
    "verify_password",
]