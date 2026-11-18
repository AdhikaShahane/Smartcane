"""Object detection, zone classification and tracking.

The zone/hysteresis and movement-analysis logic is ported from
`detect_webcam.py` (Ishwari's engine) because it was the strongest part of the
original code: a deadband around the corridor boundaries stops an object from
flickering between "left" and "right" on consecutive frames, which would
otherwise produce a different sentence every frame.

Everything here runs on a worker thread and publishes an immutable snapshot.
Nothing in this module blocks or speaks.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from . import config
from .util import StoppableThread, clamp, get_logger

log = get_logger("vision")

try:
    import numpy as np
    _HAVE_NUMPY = True
except ImportError:                                     # pragma: no cover
    np = None                                           # type: ignore
    _HAVE_NUMPY = False


@dataclass
class Detection:
    label: str
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def h(self) -> float:
        return self.y2 - self.y1

    @property
    def w(self) -> float:
        return self.x2 - self.x1


@dataclass
class TrackedObject:
    tid: int
    label: str
    x: float
    y: float
    box_h: float
    box_w: float
    zone: str
    hits: int
    last_seen: float
    dist_m: float | None
    movement: str = "stationary"
    best_conf: float = 0.0
    history: deque = field(default_factory=lambda: deque(maxlen=8))

    @property
    def confirmed(self) -> bool:
        # Two frames of evidence, OR one very confident frame. Waiting for a
        # second frame costs ~330 ms at 3 detections/sec, which is exactly the
        # delay that matters when a person steps into the path.
        return (self.hits >= config.TRACK_MIN_HITS
                or self.best_conf >= config.FAST_CONFIRM_CONF)


@dataclass
class Scene:
    objects: list[TrackedObject] = field(default_factory=list)
    frame_width: int = config.CAM_WIDTH
    frame_height: int = config.CAM_HEIGHT
    at: float = 0.0
    infer_ms: float = 0.0
    backend: str = "none"

    @property
    def age(self) -> float:
        return time.monotonic() - self.at if self.at else 1e9

    def corridor(self, hazard_only: bool = False) -> list[TrackedObject]:
        """Objects in the walking corridor.

        hazard_only=True keeps just the classes worth warning about, so a cup
        on a table does not stop the user in the street.
        """
        pool = [o for o in self.objects if o.zone == "center" and o.confirmed]
        if hazard_only:
            pool = [o for o in pool if o.label in config.HAZARD_CLASSES]
        return pool

    def nearest(self, zone: str | None = None,
                hazard_only: bool = False) -> TrackedObject | None:
        pool = [o for o in self.objects
                if o.confirmed and (zone is None or o.zone == zone)]
        if hazard_only:
            pool = [o for o in pool if o.label in config.HAZARD_CLASSES]
        if not pool:
            return None
        return min(pool, key=lambda o: (o.dist_m if o.dist_m else 99.0))

    def described(self, limit: int = 3) -> list[TrackedObject]:
        """Everything worth naming, nearest first."""
        pool = [o for o in self.objects if o.confirmed]
        pool.sort(key=lambda o: (o.dist_m if o.dist_m else 99.0))
        return pool[:limit]


def estimate_distance(label: str, box_h: float,
                      frame_width: int = config.CAM_WIDTH) -> float | None:
    """Monocular pinhole estimate: dist = real_height * f_px / box_height_px.

    FOCAL_PX is calibrated for a 640-wide frame. A phone webcam often streams
    at 1280 or 1920 wide, and the focal length *in pixels* scales with the
    frame width. Without this correction every distance is wrong by that
    ratio -- a person 2 m away reads as 1 m at 1280 wide.
    """
    real_h = config.OBJ_HEIGHTS.get(label)
    if real_h is None or box_h <= 4:
        return None
    f_px = config.FOCAL_PX * (max(1, frame_width) / float(config.CAM_WIDTH))
    raw = (real_h * f_px) / box_h
    return clamp(raw, 0.4, 20.0)


def zone_of(cx: float, width: int, previous: str | None = None) -> str:
    """Left/centre/right with a hysteresis deadband (ported from detect_webcam)."""
    left = width * config.CORRIDOR_LEFT
    right = width * config.CORRIDOR_RIGHT
    margin = width * config.ZONE_HYSTERESIS

    if previous == "left":
        if cx < left + margin:
            return "left"
        return "right" if cx > right else "center"
    if previous == "center":
        if cx < left - margin:
            return "left"
        if cx > right + margin:
            return "right"
        return "center"
    if previous == "right":
        if cx > right - margin:
            return "right"
        return "left" if cx < left else "center"
    if cx < left:
        return "left"
    return "right" if cx > right else "center"


class Detector:
    """Wraps whichever model artifact exists, and degrades to None if none do."""

    def __init__(self) -> None:
        self.model = None
        self.backend = "none"
        self.names: dict[int, str] = {}

    def load(self) -> bool:
        path = None
        for candidate in config.YOLO_CANDIDATES:
            if candidate.exists():
                path = candidate
                break
        if path is None:
            log.warning("no YOLO model found in %s - vision disabled",
                        config.MODEL_DIR)
            return False
        try:
            from ultralytics import YOLO
        except ImportError:
            log.error("ultralytics not installed: pip install ultralytics")
            return False

        try:
            if path.name.endswith("_ncnn_model"):
                import torch  # noqa: F401  (ncnn path still needs the pkg)
                self.model = YOLO(str(path), task="detect")
                self.backend = "ncnn"
            elif path.suffix == ".onnx":
                self.model = YOLO(str(path), task="detect")
                self.backend = "onnx"
            else:
                import torch
                torch.set_num_threads(2)   # leave cores for ASR and audio
                self.model = YOLO(str(path))
                self.backend = "pytorch"
            self.names = dict(self.model.names)
            log.info("detector: %s (%s)", path.name, self.backend)
            return True
        except Exception as exc:                        # noqa: BLE001
            log.error("detector load failed (%s): %s", path.name, exc)
            self.model = None
            return False

    def detect(self, image) -> list[Detection]:
        if self.model is None:
            return []
        try:
            results = self.model.predict(
                image, imgsz=config.YOLO_IMGSZ, conf=config.YOLO_CONF,
                iou=config.YOLO_IOU, verbose=False)
        except Exception as exc:                        # noqa: BLE001
            log.warning("inference failed: %s", exc)
            return []
        out: list[Detection] = []
        for res in results:
            boxes = getattr(res, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                try:
                    cls_id = int(box.cls[0])
                    label = self.names.get(cls_id, str(cls_id))
                    if label not in config.OBSTACLE_CLASSES:
                        continue
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    out.append(Detection(label, x1, y1, x2, y2,
                                         float(box.conf[0])))
                except Exception:                       # noqa: BLE001
                    continue
        return out


class Vision:
    def __init__(self, camera, mock: bool = False) -> None:
        self.camera = camera
        self.mock = mock
        self.detector = Detector()
        self.enabled = False
        self._scene = Scene()
        self._lock = threading.Lock()
        self._thread: StoppableThread | None = None
        self._tracks: dict[int, TrackedObject] = {}
        self._next_id = 1

    def start(self) -> None:
        self.enabled = self.detector.load() and not self.mock
        if not self.enabled:
            log.warning("vision disabled - ultrasonic-only mode")
        self._thread = _VisionLoop(self)
        self._thread.start()

    def stop(self) -> None:
        if self._thread:
            self._thread.stop()

    def scene(self) -> Scene:
        with self._lock:
            return self._scene

    # -- internals ---------------------------------------------------------
    def process(self, image) -> Scene:
        started = time.monotonic()
        h, w = image.shape[:2]
        detections = self.detector.detect(image) if self.enabled else []
        now = time.monotonic()
        self._update_tracks(detections, now, w)

        objects = []
        for tid, trk in self._tracks.items():
            if now - trk.last_seen > config.TRACK_MAX_AGE:
                continue
            objects.append(trk)

        scene = Scene(objects=objects, frame_width=w, frame_height=h,
                      at=now, infer_ms=(now - started) * 1000.0,
                      backend=self.detector.backend)
        with self._lock:
            self._scene = scene
        return scene

    def _update_tracks(self, detections: list[Detection], now: float,
                       width: int) -> None:
        matched: set[int] = set()

        for det in detections:
            best_id, best_dist = None, float("inf")
            for tid, trk in self._tracks.items():
                if tid in matched or trk.label != det.label:
                    continue
                if now - trk.last_seen > config.TRACK_MAX_AGE:
                    continue
                d = math.hypot(det.cx - trk.x, det.cy - trk.y)
                if d < best_dist:
                    best_dist, best_id = d, tid

            if best_id is not None and best_dist <= config.TRACK_MAX_DIST:
                trk = self._tracks[best_id]
                trk.history.append((det.cx, det.cy, det.h, now))
                trk.x, trk.y = det.cx, det.cy
                trk.box_h, trk.box_w = det.h, det.w
                trk.dist_m = estimate_distance(det.label, det.h, width)
                trk.zone = zone_of(det.cx, width, trk.zone)
                trk.hits += 1
                trk.best_conf = max(trk.best_conf, det.conf)
                trk.last_seen = now
                trk.movement = _movement(trk)
                matched.add(best_id)
            else:
                tid = self._next_id
                self._next_id += 1
                self._tracks[tid] = TrackedObject(
                    tid=tid, label=det.label, x=det.cx, y=det.cy,
                    box_h=det.h, box_w=det.w,
                    zone=zone_of(det.cx, width), hits=1, last_seen=now,
                    dist_m=estimate_distance(det.label, det.h, width),
                    best_conf=det.conf,
                    history=deque([(det.cx, det.cy, det.h, now)], maxlen=8))
                matched.add(tid)

        for tid in [t for t, o in self._tracks.items()
                    if now - o.last_seen > config.TRACK_MAX_AGE]:
            del self._tracks[tid]


def _movement(trk: TrackedObject) -> str:
    """Ported from detect_webcam.get_movement()."""
    hist = trk.history
    if len(hist) < 4:
        return "stationary"
    x0, y0, h0, _ = hist[0]
    x1, y1, h1, _ = hist[-1]
    dx, dy = x1 - x0, y1 - y0

    if abs(dx) >= 35:
        return "left_to_right" if dx > 0 else "right_to_left"
    if h0 > 0:
        growth = (h1 - h0) / h0
        if growth >= 0.18:
            return "toward"
        if growth <= -0.18:
            return "away"
    if abs(dy) >= 25:
        return "toward" if dy > 0 else "away"
    return "stationary"


class _VisionLoop(StoppableThread):
    def __init__(self, vision: Vision) -> None:
        super().__init__("vision")
        self.vision = vision

    def _run(self) -> None:
        period = 1.0 / config.DETECT_FPS
        while not self.stopped:
            started = time.monotonic()
            frame = self.vision.camera.latest()
            if frame is not None and frame.age < 0.5:
                try:
                    self.vision.process(frame.image)
                except Exception as exc:                # noqa: BLE001
                    log.warning("vision loop error: %s", exc)
            self.sleep(max(0.01, period - (time.monotonic() - started)))
