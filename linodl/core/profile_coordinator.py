"""Process-local coordination for persistent browser profile directories."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator


class ProfileLeaseCancelled(RuntimeError):
    """Raised when a task is cancelled while waiting for a browser profile."""


class BrowserProfileCoordinator:
    """Allow only one active browser context per normalized profile path."""

    def __init__(self, poll_interval: float = 0.1):
        self._poll_interval = poll_interval
        self._condition = threading.Condition()
        self._active_paths: set[str] = set()

    @staticmethod
    def _key(profile_path: str) -> str:
        resolved = Path(os.path.expanduser(profile_path)).resolve()
        return os.path.normcase(str(resolved))

    @contextmanager
    def acquire(
        self,
        profile_path: str,
        cancel_event: threading.Event | None = None,
        wait_callback: Callable[[str], None] | None = None,
    ) -> Iterator[None]:
        key = self._key(profile_path)
        reported_wait = False

        with self._condition:
            while key in self._active_paths:
                if cancel_event is not None and cancel_event.is_set():
                    raise ProfileLeaseCancelled("浏览档案等待已取消")
                if not reported_wait and wait_callback is not None:
                    wait_callback("等待浏览档案…")
                    reported_wait = True
                self._condition.wait(self._poll_interval)
            if cancel_event is not None and cancel_event.is_set():
                raise ProfileLeaseCancelled("浏览档案等待已取消")
            self._active_paths.add(key)

        try:
            yield
        finally:
            with self._condition:
                self._active_paths.discard(key)
                self._condition.notify_all()


profile_coordinator = BrowserProfileCoordinator()
