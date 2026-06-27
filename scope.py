"""Maestro data scope (per-request tenant context)."""

import contextvars
from contextlib import contextmanager

_maestro_data_username: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "maestro_data_username", default=None
)


def activate_maestro_data(maestro_username: str | None) -> None:
    if maestro_username:
        _maestro_data_username.set(maestro_username.strip().lower())
    else:
        _maestro_data_username.set(None)


def current_maestro_data() -> str | None:
    return _maestro_data_username.get()


def require_maestro_data() -> str:
    username = current_maestro_data()
    if not username:
        raise RuntimeError("Maestro data scope not active")
    return username


@contextmanager
def maestro_data_scope(maestro_username: str):
    prev = current_maestro_data()
    try:
        activate_maestro_data(maestro_username)
        yield
    finally:
        activate_maestro_data(prev)
