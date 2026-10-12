from __future__ import annotations

from collections.abc import Hashable
from time import time
from typing import Any


class InMemoryCacheStore:
    """A lightweight TTL cache for market snapshots and derived values."""

    def __init__(self) -> None:
        self._store: dict[Hashable, tuple[Any, float | None]] = {}

    def set(
        self,
        key: Hashable,
        value: Any,
        *,
        ttl_seconds: float | None = None,
        ttl: float | None = None,
    ) -> None:
        effective_ttl = ttl_seconds if ttl_seconds is not None else ttl
        expires_at = None if effective_ttl is None else time() + float(effective_ttl)
        self._store[key] = (value, expires_at)

    def get(self, key: Hashable) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def delete(self, key: Hashable) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
