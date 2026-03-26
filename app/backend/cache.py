"""
backend/cache.py
Simple in-memory TTL cache.  No external dependencies required.

Usage:
    cache = TTLCache()
    cache.set("regime", data, ttl_seconds=900)
    data = cache.get("regime")          # None if expired or missing
    cache.invalidate("regime")
"""

from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Optional


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, datetime]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if datetime.utcnow() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int = 900) -> None:
        with self._lock:
            self._store[key] = (value, datetime.utcnow() + timedelta(seconds=ttl_seconds))

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            now = datetime.utcnow()
            alive = sum(1 for _, (_, exp) in self._store.items() if now <= exp)
            return {"total_keys": len(self._store), "alive_keys": alive}
