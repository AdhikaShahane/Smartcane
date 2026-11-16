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


def resolve_audio_device(device, kind: str):
    """Pick an audio device, and never leave the system with no audio at all.

    `SMARTCANE_MIC=Jabra` is convenient until the headset is unplugged or the
    name differs slightly -- then the old code raised "No input device matching"
    and disabled the microphone entirely, which looks like a broken build.

    The important case is a USB headset that is plugged in but is NOT the
    system default. ALSA's default input is often -1 (no default), so
    sounddevice refuses to open anything even though a perfectly good
    microphone exists. In that case we scan for the first device that actually
    has capture channels and use it.

    kind: "in" or "out"
    """
    log = get_logger("audio")
    try:
        import sounddevice as sd
    except Exception:                                   # noqa: BLE001
        return device

    def usable(info, direction):
        return (info["max_input_channels"] > 0 if direction == "in"
                else info["max_output_channels"] > 0)

    try:
        devices = sd.query_devices()
    except Exception:                                   # noqa: BLE001
        return device

    # 1. explicit device requested
    if device is not None:
        if isinstance(device, int):
            return device
        want = str(device).lower()
        for index, info in enumerate(devices):
            if usable(info, kind) and want in str(info["name"]).lower():
                return index
        log.warning("no %s device matching %r - auto-selecting instead",
                    "input" if kind == "in" else "output", device)

    # 2. is the system default usable?
    try:
        default = sd.default.device[0 if kind == "in" else 1]
        if default is not None and default >= 0:
            if usable(devices[default], kind):
                return None                             # default is fine
    except Exception:                                   # noqa: BLE001
        pass

    # 3. fall back to the first device that can actually do the job
    for index, info in enumerate(devices):
        if usable(info, kind):
            log.warning("system default %s was unusable - using device %d: %s",
                        "input" if kind == "in" else "output", index,
                        info["name"])
            return index

    log.error("no %s device exists on this system",
              "capture" if kind == "in" else "playback")
    return None
