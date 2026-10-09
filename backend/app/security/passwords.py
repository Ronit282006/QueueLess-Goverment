"""Password hashing.

We call bcrypt directly rather than through passlib: the installed passlib
release is incompatible with bcrypt 5.x and would fail at runtime.
"""
from __future__ import annotations

import bcrypt

MAX_BYTES = 72


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:MAX_BYTES], password_hash.encode("utf-8"))
    except ValueError:
        return False