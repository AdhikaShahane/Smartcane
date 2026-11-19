"""ADE20K semantic segmentation: scene understanding for a walking cane.

Why segmentation instead of detection
-------------------------------------
COCO detection answers "what objects are in this picture". A blind pedestrian
needs a different question answered: **where can I put my foot next?** ADE20K
labels every pixel, including floor, sidewalk, path, road, door, wall, railing,
column, stairs and step - none of which exist in COCO.

Two things come out of the mask:

1. **Free space per zone.** Count walkable pixels in the left, centre and right
   thirds of the near field. That is a *measured* clearance, replacing the
   previous guess of "nothing was detected, so it is probably fine".

2. **Obstacle regions as boxes.** Connected groups of non-walkable pixels are
   turned into bounding boxes, so the existing tracker, risk engine and
   guidance keep working unchanged.

Nothing here imports vision.py - that would be a circular import - so the
output type is a plain `SegObject` that vision converts.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config
from .util import get_logger

log = get_logger("segmentation")


@dataclass
class SegObject:
    """One connected obstacle region, in frame pixel coordinates."""
    label: str
    class_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    fill: float           # component area / bbox area: how solid the region is

    @property
    def box_h(self) -> float:
        return self.y2 - self.y1

    @property
    def box_w(self) -> float:
        return self.x2 - self.x1


@dataclass
class FreeSpace:
    """Walkable fraction in each third of the near field, 0.0 - 1.0."""
    left: float = 0.0
    center: float = 0.0
    right: float = 0.0
    valid: bool = False

    @property
    def center_blocked(self) -> bool:
        return self.valid and self.center < (1.0 - config.ZONE_BLOCKED_FRACTION)

    def usable(self, side: str) -> bool:
        if not self.valid:
            return False
        value = {"left": self.left, "right": self.right}.get(side, 0.0)
        return value >= config.ZONE_USABLE_FRACTION

    @property
    def best_side(self) -> str | None:
        """Which side is walkable, if either. Never guesses."""
        if not self.valid:
            return None
        if self.left >= config.ZONE_USABLE_FRACTION and self.left >= self.right:
            return "left"
        if self.right >= config.ZONE_USABLE_FRACTION:
            return "right"
        return None

    def describe(self) -> str:
        if not self.valid:
            return "free space unknown"
        return (f"L {self.left:.0%} C {self.center:.0%} R {self.right:.0%}")


# ---------------------------------------------------------------------------
# Mask -> information
# ---------------------------------------------------------------------------
def obstacle_mask(mask: np.ndarray) -> np.ndarray:
    """True where a pixel is something you must not walk through."""
    walkable = np.isin(mask, list(config.WALKABLE_IDS))
    ignore = np.isin(mask, list(config.IGNORE_IDS))
    return ~walkable & ~ignore


def free_space_from_mask(mask: np.ndarray) -> FreeSpace:
    """Measure walkable fraction per zone from the near field.

    Only the bottom half of the grid is used: that is the ground a step away,
    which is what "can I walk forward" actually depends on. The upper half is
    mostly wall, sky and distant scene.
    """
    if mask is None or mask.size == 0:
        return FreeSpace(valid=False)

    walk = np.isin(mask, list(config.WALKABLE_IDS)).astype(np.float32)
    h, w = walk.shape

    # Coarse occupancy grid: cheap, and robust to mask speckle.
    # The block size must be computed so the grid is exactly GRID_H x GRID_W.
    # Letting reshape infer one dimension produced 16 columns while the zone
    # split assumed 15, which silently skewed the right-hand zone.
    cell_h = max(1, h // config.GRID_H)
    cell_w = max(1, w // config.GRID_W)
    rows = cell_h * config.GRID_H
    cols = cell_w * config.GRID_W
    block = walk[:rows, :cols]
    grid = block.reshape(config.GRID_H, cell_h,
                         config.GRID_W, cell_w).mean(axis=(1, 3))

    near = grid[config.GRID_H // 2:, :]          # bottom half of the frame
    c1 = config.GRID_W // 3
    c2 = (2 * config.GRID_W) // 3
    left = float(near[:, :c1].mean())
    center = float(near[:, c1:c2].mean())
    right = float(near[:, c2:].mean())
    return FreeSpace(left=left, center=center, right=right, valid=True)


def _label_component(comp: np.ndarray, mask: np.ndarray) -> tuple[str, int]:
    """Dominant ADE20K class inside a component."""
    values = mask[comp]
    if values.size == 0:
        return "obstacle", -1
    ids, counts = np.unique(values, return_counts=True)
    # Ignore walkable pixels that leaked into the component.
    keep = [(c, i) for c, i in zip(counts, ids)
            if i not in config.WALKABLE_IDS]
    if not keep:
        return "obstacle", -1
    best_count, best_id = max(keep)
    return config.ADE20K_NAMES.get(int(best_id), "obstacle"), int(best_id)


def _components(binary: np.ndarray) -> list[np.ndarray]:
    """Connected components as boolean masks. Falls back to a coarse grid."""
    try:
        import cv2
        n, labels = cv2.connectedComponents(binary.astype(np.uint8))
        return [labels == i for i in range(1, n)]
    except Exception:                                   # noqa: BLE001
        pass
    try:
        from scipy import ndimage
        labels, n = ndimage.label(binary)
        return [labels == i for i in range(1, n + 1)]
    except Exception:                                   # noqa: BLE001
        pass
    # Last resort: treat the whole mask as one region. Crude, but it keeps the
    # pipeline alive rather than silently returning nothing.
    return [binary] if binary.any() else []


def mask_to_objects(mask: np.ndarray, min_area_frac: float = 0.004
                    ) -> list[SegObject]:
    """Turn a class mask into bounding boxes for the existing tracker."""
    if mask is None or mask.size == 0:
        return []
    h, w = mask.shape
    obstacle = obstacle_mask(mask)
    if not obstacle.any():
        return []

    min_area = max(16, int(h * w * min_area_frac))
    objects: list[SegObject] = []
    ys, xs = np.nonzero(obstacle)

    for comp in _components(obstacle):
        area = int(comp.sum())
        if area < min_area:
            continue
        rows = np.nonzero(comp.any(axis=1))[0]
        cols = np.nonzero(comp.any(axis=0))[0]
        if rows.size == 0 or cols.size == 0:
            continue
        y1, y2 = float(rows[0]), float(rows[-1])
        x1, x2 = float(cols[0]), float(cols[-1])
        box_area = max(1.0, (y2 - y1) * (x2 - x1))
        label, class_id = _label_component(comp, mask)
        objects.append(SegObject(
            label=label, class_id=class_id, x1=x1, y1=y1, x2=x2, y2=y2,
            fill=min(1.0, area / box_area)))
    return objects


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------
class SegDetector:
    """Wraps whichever ADE20K semantic model is available.

    The Ultralytics semantic-segmentation output attribute has changed between
    releases, so several are tried. If none work, `load()` returns False and
    the vision layer falls back to the legacy detector rather than dying.
    """

    def __init__(self) -> None:
        self.model = None
        self.backend = "none"
        self.path = None

    def load(self) -> bool:
        path = None
        for candidate in config.SEG_MODEL_CANDIDATES:
            if candidate.exists():
                path = candidate
                break
        if path is None:
            log.warning("no ADE20K segmentation model in %s "
                        "(run tools/fetch_model.py)", config.MODEL_DIR)
            return False
        try:
            from ultralytics import YOLO
        except ImportError:
            log.error("ultralytics not installed: pip install ultralytics")
            return False
        try:
            self.model = YOLO(str(path), task="segment")
            self.backend = "yolo-sem"
            self.path = path
            log.info("segmentation model: %s", path.name)
            return True
        except Exception as exc:                        # noqa: BLE001
            log.error("could not load %s: %s", path.name, exc)
            self.model = None
            return False

    def infer(self, image) -> np.ndarray | None:
        """Return an HxW array of ADE20K class ids, or None."""
        if self.model is None:
            return None
        try:
            results = self.model.predict(image, imgsz=config.SEG_IMGSZ,
                                         verbose=False)
        except Exception as exc:                        # noqa: BLE001
            log.warning("segmentation inference failed: %s", exc)
            return None
        if not results:
            return None
        result = results[0]

        mask = self._extract_mask(result)
        if mask is None:
            return None
        return mask

    @staticmethod
    def _extract_mask(result) -> np.ndarray | None:
        sem = getattr(result, "semantic_mask", None)
        if sem is not None:
            data = getattr(sem, "data", sem)
            try:
                arr = data.cpu().numpy() if hasattr(data, "cpu") else np.asarray(data)
            except Exception:                           # noqa: BLE001
                return None
            arr = np.squeeze(arr)
            if arr.ndim == 3:                           # (C,H,W) one-hot
                arr = arr.argmax(axis=0)
            if arr.ndim == 2:
                return arr.astype(np.int32)
        # Some versions expose per-instance masks instead; derive a class map.
        masks = getattr(result, "masks", None)
        if masks is not None:
            data = getattr(masks, "data", None)
            cls = getattr(masks, "cls", None)
            if data is not None and cls is not None:
                try:
                    arrs = data.cpu().numpy()
                    ids = cls.cpu().numpy().astype(np.int32)
                except Exception:                       # noqa: BLE001
                    return None
                h, w = arrs.shape[-2:]
                out = np.zeros((h, w), dtype=np.int32)
                for arr, cid in zip(arrs, ids):
                    out[arr > 0.5] = cid
                return out
        return None


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------
def synthetic_mask(width: int = 160, height: int = 120,
                   blocked: str | None = None) -> np.ndarray:
    """Build a predictable ground/obstacle mask so the pipeline is testable.

    blocked: None for a clear path, or "left" / "center" / "right" / "all".
    """
    mask = np.full((height, width), 4, dtype=np.int32)      # floor
    mask[:height // 3] = 3                                  # sky
    third = width // 3
    spans = {
        "left": (0, third),
        "center": (third, 2 * third),
        "right": (2 * third, width),
    }
    targets = ["left", "center", "right"] if blocked == "all" else \
              ([blocked] if blocked else [])
    for name in targets:
        x1, x2 = spans[name]
        mask[height // 2:, x1:x2] = 20                      # chair blocks it
    return mask
