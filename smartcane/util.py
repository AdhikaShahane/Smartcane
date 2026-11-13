"""Small shared helpers: logging, rate limiting, safe shutdown."""
from __future__ import annotations

import logging
import sys
import threading
import time

_LOG_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)-14s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    _LOG_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class RateLimiter:
    """Allow at most `n` events per rolling `window` seconds."""

    def __init__(self, n: int = 1, window: float = 1.0) -> None:
        self.n = n
        self.window = window
        self._times: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._times = [t for t in self._times if now - t < self.window]
            if len(self._times) >= self.n:
                return False
            self._times.append(now)
            return True


class StoppableThread(threading.Thread):
    """Thread with a cooperative stop flag and exception capture."""

    def __init__(self, name: str, daemon: bool = True) -> None:
        super().__init__(name=name, daemon=daemon)
        self._stop = threading.Event()
        self.error: BaseException | None = None

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def sleep(self, seconds: float) -> None:
        self._stop.wait(seconds)

    def run(self) -> None:                              # pragma: no cover
        try:
            self._run()
        except BaseException as exc:                    # noqa: BLE001
            self.error = exc
            get_logger(self.name).exception("thread crashed: %s", exc)

    def _run(self) -> None:
        raise NotImplementedError


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
