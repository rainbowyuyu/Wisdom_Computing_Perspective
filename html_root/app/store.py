"""Bounded in-process stores, with server-side expiry (one application worker)."""
from collections.abc import MutableMapping
import threading
import time


class ExpiringStore(MutableMapping):
    def __init__(self, ttl, maximum):
        self.ttl, self.maximum = ttl, maximum
        self._items = {}
        self._lock = threading.RLock()

    def _purge(self):
        now = time.monotonic()
        for key, (_, expires) in list(self._items.items()):
            if expires <= now:
                self._items.pop(key, None)

    def __getitem__(self, key):
        with self._lock:
            value, expires = self._items[key]
            if expires <= time.monotonic():
                del self._items[key]
                raise KeyError(key)
            return value

    def __setitem__(self, key, value):
        with self._lock:
            self._purge()
            if key not in self._items and len(self._items) >= self.maximum:
                del self._items[next(iter(self._items))]
            self._items[key] = (value, time.monotonic() + self.ttl)

    def __delitem__(self, key):
        with self._lock:
            del self._items[key]

    def pop(self, key, default=None):
        with self._lock:
            try:
                value = self[key]
            except KeyError:
                return default
            del self._items[key]
            return value

    def __iter__(self):
        with self._lock:
            self._purge()
            return iter(list(self._items))

    def __len__(self):
        with self._lock:
            self._purge()
            return len(self._items)


CAPTCHA_STORE = ExpiringStore(300, 1000)
SESSION_STORE = ExpiringStore(86400, 10000)
