from __future__ import annotations

import re


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str = "user") -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return slug or fallback


def email_local_part(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[0]
