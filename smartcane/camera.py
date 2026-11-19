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

import concurrent.futures
import socket
import threading
import time
from dataclasses import dataclass

import numpy as np

from . import config
from .util import StoppableThread, get_logger

log = get_logger("camera")


def discover_ip_webcams(port: int = config.CAMERA_SCAN_PORT,
                        timeout: float = config.CAMERA_SCAN_TIMEOUT
                        ) -> list[str]:
    """Find phones running an IP-webcam server on the local network.

    The phone's address comes from DHCP, so it changes after a reboot and the
    old URL silently stops working. Rather than make the user hunt for it in
    the app, scan the /24 we are on for anything listening on the webcam port.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))          # no packets are actually sent
        local_ip = sock.getsockname()[0]
        sock.close()
    except Exception as exc:                            # noqa: BLE001
        log.warning("cannot determine local IP for camera scan: %s", exc)
        return []

    if local_ip.startswith("127."):
        return []

    prefix = local_ip.rsplit(".", 1)[0]
    hosts = [f"{prefix}.{i}" for i in range(1, 255)]

    def probe(host: str) -> str | None:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return host
        except Exception:                               # noqa: BLE001
            return None

    found: list[str] = []
    log.info("scanning %s.0/24 for a camera on port %d ...", prefix, port)
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        for host in pool.map(probe, hosts):
            if host:
                found.append(f"http://{host}:{port}/video")
    log.info("camera scan found %d candidate(s)", len(found))
    return found

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
        self._grab_failures = 0
        self._last_reconnect = 0.0
        self._ever_had_frames = False

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
    def _remember(self, url: str) -> None:
        try:
            config.CAMERA_CACHE.write_text(url.strip() + "\n", encoding="utf-8")
        except Exception:                               # noqa: BLE001
            pass

    def _load_cached(self) -> str | None:
        try:
            url = config.CAMERA_CACHE.read_text(encoding="utf-8").strip()
            return url or None
        except Exception:                               # noqa: BLE001
            return None

    def _open_real(self) -> bool:
        if not _HAVE_CV2:
            log.error("opencv not installed: pip install opencv-python-headless")
            return False

        source = self.source

        if source == "picamera2":
            return self._try_picamera2()
        if source.isdigit():
            return self._try_cv2(int(source))

        if source not in ("auto", "scan"):
            # an explicit URL or device path was given
            if self._try_cv2(source):
                self._remember(source)
                return True
            log.warning("camera %s did not open - falling back to discovery",
                        source)

        if source != "scan":
            # 1. the phone webcam we used last time. Its IP may have changed,
            #    but when it has not this connects in under a second instead of
            #    spending ~10 s probing local cameras first.
            cached = self._load_cached()
            if cached and self._try_cv2(cached):
                log.info("using remembered camera URL %s", cached)
                return True
            # 2. the CSI camera, if this Pi has one
            if self._try_picamera2():
                return True
            # 3. a USB webcam
            for idx in (0, 1, 2):
                if self._try_cv2(idx):
                    return True

        # 4. scan the local network for a webcam server
        for url in discover_ip_webcams():
            if self._try_cv2(url):
                self._remember(url)
                log.info("discovered camera at %s", url)
                return True

        return False

    def _try_cv2(self, source) -> bool:
        try:
            # Set open/read timeouts BEFORE opening. Without these, a stale
            # network URL (the phone changed IP) can block for 30+ seconds,
            # which is what made reconnecting feel chaotic.
            cap = cv2.VideoCapture()
            try:
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
            except Exception:                           # noqa: BLE001
                pass
            if not cap.open(source):
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
            if ok and frame is not None:
                self._grab_failures = 0
                self._ever_had_frames = True
                return frame
            self._note_grab_failure()
            return None
        return None

    @property
    def lost(self) -> bool:
        """True when a real camera was working and has now stopped."""
        return self._ever_had_frames and self._grab_failures > 0

    def _note_grab_failure(self) -> None:
        """Reopen a camera that has gone away.

        Phones sleep, WiFi drops, IP Webcam gets killed by the OS. Without this
        the cane keeps running against a dead capture handle and the user gets
        no indication at all.
        """
        self._grab_failures += 1
        if self._grab_failures < config.CAM_RECONNECT_AFTER:
            return
        now = time.monotonic()
        if now - self._last_reconnect < config.CAM_RECONNECT_INTERVAL_SEC:
            return
        self._last_reconnect = now
        log.warning("camera lost (%d dead frames) - reconnecting",
                    self._grab_failures)
        self._reconnect()

    @property
    def needs_open(self) -> bool:
        """True when no capture handle exists yet - the camera never opened."""
        return (self._cap is None and self._picam is None
                and self.backend not in ("mock",))

    def retry_open(self) -> None:
        """Keep trying to acquire a camera that was never found.

        At boot the WiFi usually comes up after the program does. Without this
        the camera is looked for once, not found, and never looked for again -
        so an unattended boot with a slow hotspot runs blind forever.
        """
        now = time.monotonic()
        if now - self._last_reconnect < config.CAM_RECONNECT_INTERVAL_SEC:
            return
        self._last_reconnect = now
        log.info("looking for a camera again ...")
        if self._open_real():
            log.info("camera acquired: %s", self.backend)
        else:
            log.info("still no camera - will keep trying")

    def _reconnect(self) -> None:
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:                               # noqa: BLE001
            pass
        self._cap = None
        self._grab_failures = 0
        if self._open_real():
            log.info("camera reconnected: %s", self.backend)
        else:
            log.warning("camera still unreachable")

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
            if image is None and self.cam.needs_open:
                # Never opened at all - typical when the Pi boots faster than
                # the hotspot. Keep trying instead of giving up for good.
                self.cam.retry_open()
            if image is None:
                if self.cam.lost and not config.CAM_SYNTHETIC_ON_LOSS:
                    # A real camera dropped mid-run. Publishing a synthetic
                    # picture here would feed the detector a fake moving block
                    # and turn it into a reported obstacle. Say nothing and
                    # keep trying to reconnect instead.
                    self.sleep(period)
                    continue
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
