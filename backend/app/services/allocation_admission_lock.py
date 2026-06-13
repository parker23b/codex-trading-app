from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator

from sqlalchemy import text
from sqlmodel import Session

# Stable signed 64-bit key scoped to portfolio allocation admission.
_POSTGRES_ALLOCATION_LOCK_KEY = 4_913_166_809_274_281_114
_LOCAL_ALLOCATION_LOCK = RLock()


@contextmanager
def allocation_admission_lock(session: Session) -> Iterator[None]:
    """Serialize allocation plus durable intent admission for one risk book."""

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        with _LOCAL_ALLOCATION_LOCK:
            yield
        return

    with bind.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _POSTGRES_ALLOCATION_LOCK_KEY},
        )
        yield
