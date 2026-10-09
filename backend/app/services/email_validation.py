"""Address hygiene so verification codes are only sent to real mailboxes.

`pydantic.EmailStr` accepts anything shaped like ``user@host.tld`` — including
``user@gmail.coom``, whose domain does not exist, so the OTP silently bounces.
This module adds the checks that matter before we enqueue a send.
"""
from __future__ import annotations

import re

from ..errors import ApiException

# Free consumer providers we can validate exactly: if the user typed one of
# these domains (or a near miss) we know what they meant.
PROVIDER_DOMAINS = frozenset({
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "zoho.com",
    "gmx.com",
    "yandex.com",
    "rediffmail.com",
    "fastmail.com",
    "tutanota.com",
    "mail.com",
})

# Distinctive provider roots: a label equal to one of these on a domain we do
# not recognise means the user misspelled the domain.
PROVIDER_ROOTS = {
    "gmail": "gmail.com",
    "googlemail": "gmail.com",
    "yahoo": "yahoo.com",
    "ymail": "yahoo.com",
    "outlook": "outlook.com",
    "hotmail": "hotmail.com",
    "icloud": "icloud.com",
    "protonmail": "proton.me",
    "proton": "proton.me",
    "aol": "aol.com",
    "zoho": "zoho.com",
    "gmx": "gmx.com",
    "yandex": "yandex.com",
    "rediffmail": "rediffmail.com",
    "tutanota": "tutanota.com",
}

# Hand-picked near misses that the root heuristic cannot catch.
TYPO_DOMAINS = {
    "gmai.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmail.co": "gmail.com",
    "gmail.con": "gmail.com",
    "gmailcm.com": "gmail.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "yahhoo.com": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "hotmil.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "outloo.com": "outlook.com",
    "iclou.com": "icloud.com",
    "protonmai.com": "proton.me",
}

_LOCAL_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~](?:[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{0,62}[A-Za-z0-9!#$%&'*+/=?^_`{|}~])?$")
_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TLD_RE = re.compile(r"^[a-z]{2,24}$")


def _reject(message: str) -> str:
    raise ApiException(422, "invalid_email", message)


def ensure_deliverable_email(raw: str) -> str:
    """Normalise an address or raise a 422 with a human-readable reason."""
    value = (raw or "").strip().lower()
    if value.count("@") != 1:
        _reject("Enter a valid email address, for example you@gmail.com.")
    local, domain = value.split("@", 1)

    if not local or not _LOCAL_RE.match(local):
        _reject("The part of your email address before the @ is not valid.")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        _reject("The part of your email address before the @ is not valid.")

    labels = domain.split(".")
    if len(labels) < 2:
        _reject("Enter a complete email address, for example you@gmail.com.")
    if any(not _LABEL_RE.match(label) for label in labels):
        _reject("The domain of your email address is not valid.")
    if not _TLD_RE.match(labels[-1]):
        _reject("The domain of your email address is not valid.")

    if domain in TYPO_DOMAINS:
        _reject(f"That domain does not exist. Did you mean {TYPO_DOMAINS[domain]}?")
    if domain in PROVIDER_DOMAINS:
        return value

    if len(labels) == 2:
        suggestion = PROVIDER_ROOTS.get(labels[0])
        if suggestion and suggestion != domain:
            _reject(f"That domain does not exist. Did you mean {suggestion}?")
    return value
