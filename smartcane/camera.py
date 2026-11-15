"""Camera abstraction.

On Raspberry Pi OS Bookworm the CSI camera is NOT exposed as /dev/video0 by
default, so `cv2.VideoCapture(0)` silently fails on a Pi Camera Module. This
module tries every plausible backend in order and reports which one worked:

  1. OpenCV VideoCapture  (USB webcam, IP-webcam URL, or legacy CSI stack)
  2. picamera2            (the supported CSI path on Bookworm)
  3. synthetic frames     (last resort, so the rest of the system still runs)

The active backend is logged at startup, and surfaced in the HUD, so a
remote-debugging session starts from a known state instead of a guess.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from . import config
from .util import StoppableThread, get_logger

log = get_logger("camera")

try:
    import cv2
    _HAVE_CV2 = True
except ImportError:                                     # pragma: no cover
    cv2 = None                                          # type: ignore
    _HAVE_CV2 = False


@dataclass
class Frame:
    image: np.ndarray
    index: int
    captured_at: float

    @property
    def age(self) -> float:
        return time.monotonic() - self.captured_at

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        return int(self.image.shape[1])


class Camera:
    def __init__(self, source: str | None = None, mock: bool = False) -> None:
        self.source = source if source is not None else config.CAMERA_SOURCE
        self.mock = mock
        self.backend = "none"
        self._frame: Frame | None = None
        self._lock = threading.Lock()
        self._thread: StoppableThread | None = None
        self._index = 0
        self._cap = None
        self._picam = None

    # -- public ------------------------------------------------------------
    def start(self) -> bool:
        if self.mock:
            self.backend = "mock"
        elif not self._open_real():
            log.warning("no camera available - using synthetic frames")
            self.backend = "mock"
        self._thread = _CaptureLoop(self)
        self._thread.start()
        log.info("camera backend: %s", self.backend)
        return self.backend != "none"

    def stop(self) -> None:
        if self._thread:
            self._thread.stop()
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:                           # noqa: BLE001
                pass
        if self._picam is not None:
            try:
                self._picam.stop()
            except Exception:                           # noqa: BLE001
                pass

    def latest(self) -> Frame | None:
        with self._lock:
            return self._frame

    def read(self) -> np.ndarray | None:
        frame = self.latest()
        return None if frame is None else frame.image

    # -- backends ----------------------------------------------------------
    def _open_real(self) -> bool:
        if not _HAVE_CV2:
            log.error("opencv not installed: pip install opencv-python-headless")
            return False

        source = self.source
        if source == "auto":
            # try picamera2 first on a Pi: it is the supported Bookworm path
            if self._try_picamera2():
                return True
            for idx in (0, 1, 2):
                if self._try_cv2(idx):
                    return True
            return False
        if source == "picamera2":
            return self._try_picamera2()
        if source.isdigit():
            return self._try_cv2(int(source))
        return self._try_cv2(source)

    def _try_cv2(self, source) -> bool:
        try:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                return False
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, config.CAM_FPS)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, frame = cap.read()
            if not ok or frame is None:
                cap.release()
                return False
            self._cap = cap
            self.backend = f"cv2:{source}"
            return True
        except Exception as exc:                        # noqa: BLE001
            log.debug("cv2 source %r failed: %s", source, exc)
            return False

    def _try_picamera2(self) -> bool:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            # This is the #1 reason a working CSI camera shows up as "mock".
            # Log loudly: `rpicam-hello` working does NOT mean Python can see it.
            log.warning("picamera2 not importable (%s). "
                        "Fix: sudo apt install -y python3-picamera2, then make "
                        "sure the venv can see /usr/lib/python3/dist-packages",
                        exc)
            return False
        try:
            picam = Picamera2()
            cfg = picam.create_preview_configuration(
                main={"size": (config.CAM_WIDTH, config.CAM_HEIGHT),
                      "format": "RGB888"})
            picam.configure(cfg)
            picam.start()
            time.sleep(0.4)                             # let AE settle
            self._picam = picam
            self.backend = "picamera2"
            return True
        except Exception as exc:                        # noqa: BLE001
            log.warning("picamera2 failed to start: %s", exc)
            return False

    def _grab(self) -> np.ndarray | None:
        if self._picam is not None:
            arr = self._picam.capture_array()
            if arr is None:
                return None
            if arr.ndim == 3 and arr.shape[2] == 4:
                arr = arr[:, :, :3]
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        if self._cap is not None:
            ok, frame = self._cap.read()
            return frame if ok else None
        return None

    def _publish(self, image: np.ndarray) -> None:
        self._index += 1
        frame = Frame(image=image, index=self._index,
                      captured_at=time.monotonic())
        with self._lock:
            self._frame = frame


class _CaptureLoop(StoppableThread):
    def __init__(self, cam: Camera) -> None:
        super().__init__("camera")
        self.cam = cam
        self._synth_t = 0.0

    def _run(self) -> None:
        period = 1.0 / config.CAM_FPS
        while not self.stopped:
            start = time.monotonic()
            image = None
            if self.cam.backend != "mock":
                image = self.cam._grab()
            if image is None:
                image = self._synthetic()
            self.cam._publish(image)
            elapsed = time.monotonic() - start
            self.sleep(max(0.0, period - elapsed))

    def _synthetic(self) -> np.ndarray:
        """A moving block on a gradient, so the vision path has something to do.

        Deliberately numpy-only: opencv may not be installed, and the mock path
        must never be the thing that crashes a demo.
        """
        self._synth_t += 0.05
        img = np.zeros((config.CAM_HEIGHT, config.CAM_WIDTH, 3), np.uint8)
        img[:, :, 1] = np.linspace(0, 60, config.CAM_WIDTH, dtype=np.uint8)
        cx = int(config.CAM_WIDTH * (0.5 + 0.35 * np.sin(self._synth_t)))
        x1 = max(0, cx - 40)
        x2 = min(config.CAM_WIDTH, cx + 40)
        y1 = max(0, config.CAM_HEIGHT - 220)
        img[y1:y1 + 160, x1:x2] = (40, 40, 200)
        return img
