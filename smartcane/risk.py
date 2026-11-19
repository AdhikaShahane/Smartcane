"""Three-level risk classification.

Identifying an object is not the same as understanding whether it is dangerous.
A car is not critical because it is a car; it is critical when it is close,
closing on the user, and inside the walking corridor. A chair is not harmless
because it is furniture; it is critical when it sits 50 cm ahead in the path.

Every decision here is driven by evidence, and every rule states why it fired
so the spoken warning can explain itself. When the evidence is missing we say
so instead of inventing a distance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from . import config
from .vision import Scene, TrackedObject


class RiskLevel(IntEnum):
    NONE = 0
    LOW = 1        # informational: tell them what is there
    MEDIUM = 2     # caution: warn and suggest a direction
    CRITICAL = 3   # stop now, and say why

    @property
    def word(self) -> str:
        return {0: "none", 1: "low", 2: "medium", 3: "critical"}[int(self)]


@dataclass
class Risk:
    level: RiskLevel
    label: str
    dist_m: float | None
    zone: str
    in_path: bool = False
    overlap: float = 0.0
    closing_speed: float | None = None
    ttc: float | None = None
    confidence: float = 0.0
    size_ratio: float = 0.0
    uncertain: bool = False
    reason: str = ""
    source: str = "vision"

    @property
    def is_moving(self) -> bool:
        return (self.closing_speed is not None
                and abs(self.closing_speed) > config.CLOSING_MIN_SPEED)


@dataclass
class RiskReport:
    level: RiskLevel = RiskLevel.NONE
    primary: Risk | None = None
    objects: list[Risk] = field(default_factory=list)

    def of_level(self, level: RiskLevel) -> list[Risk]:
        return [r for r in self.objects if r.level == level]

    @property
    def critical(self) -> list[Risk]:
        return self.of_level(RiskLevel.CRITICAL)

    @property
    def medium(self) -> list[Risk]:
        return self.of_level(RiskLevel.MEDIUM)

    @property
    def low(self) -> list[Risk]:
        return self.of_level(RiskLevel.LOW)


def _corridor_overlap(obj: TrackedObject, frame_width: int) -> float:
    """Fraction of the object's width that falls inside the walking corridor."""
    if frame_width <= 0:
        return 0.0
    c_left = frame_width * config.CORRIDOR_LEFT
    c_right = frame_width * config.CORRIDOR_RIGHT
    x1 = obj.x - obj.box_w / 2.0
    x2 = obj.x + obj.box_w / 2.0
    width = max(1.0, x2 - x1)
    covered = max(0.0, min(x2, c_right) - max(x1, c_left))
    return covered / width


def assess_object(obj: TrackedObject, scene: Scene,
                  sensor_dist_m: float | None = None) -> Risk:
    """Classify one tracked object. Returns the reason for the level chosen."""
    frame_w = max(1, scene.frame_width)
    frame_h = max(1, scene.frame_height)

    overlap = _corridor_overlap(obj, frame_w)
    in_path = obj.zone == "center" or overlap >= config.RISK_PATH_OVERLAP
    size_ratio = obj.box_h / float(frame_h)
    confidence = obj.best_conf
    uncertain = confidence < config.RISK_MIN_CONFIDENCE

    # The ultrasonic measures the corridor directly and is more reliable than a
    # monocular estimate. When the object is the thing the sensor is seeing, use
    # the sensor's number.
    dist = obj.dist_m
    source = "vision"
    if (sensor_dist_m is not None and in_path
            and (dist is None or abs(dist - sensor_dist_m) < 1.5)):
        dist = sensor_dist_m
        source = "ultrasonic"

    closing = obj.closing_speed
    ttc = obj.time_to_collision

    # spoken_label collapses an unstable or off-profile label to "obstacle",
    # so a flickering class never gets announced as fact.
    risk = Risk(level=RiskLevel.LOW, label=obj.spoken_label, dist_m=dist,
                zone=obj.zone, in_path=in_path, overlap=overlap,
                closing_speed=closing, ttc=ttc, confidence=confidence,
                size_ratio=size_ratio, uncertain=uncertain, source=source)

    # ---------------------------------------------------------------- CRITICAL
    # Motion-based escalation is only allowed on a trustworthy detection: a
    # 30%-confidence blob 4 m away must not trigger a stop command.
    if ttc is not None and ttc <= config.TTC_CRITICAL_SEC and not uncertain:
        risk.level = RiskLevel.CRITICAL
        risk.reason = "collision in under %.1f seconds" % ttc
        return risk

    if dist is not None and dist <= config.STOP_METERS:
        risk.level = RiskLevel.CRITICAL
        risk.reason = "obstacle within %.1f metres" % dist
        return risk

    if in_path and dist is not None and dist <= config.URGENT_METERS:
        risk.level = RiskLevel.CRITICAL
        risk.reason = "blocking the path at %.1f metres" % dist
        return risk

    # Frame-filling is only used when there is NO distance to judge by: a
    # person 2 m away legitimately fills half the frame, and turning that into
    # a stop command makes the cane unusable. A weak detection is not trusted
    # to escalate on size alone either.
    if (in_path and dist is None and not uncertain
            and size_ratio >= config.RISK_BLOCKING_SIZE):
        risk.level = RiskLevel.CRITICAL
        risk.reason = "filling the view ahead"
        return risk

    # ------------------------------------------------------------------ MEDIUM
    if ttc is not None and ttc <= config.TTC_MEDIUM_SEC:
        risk.level = RiskLevel.MEDIUM
        risk.reason = "approaching, about %.1f seconds away" % ttc
        return risk

    if in_path and dist is not None and dist <= config.ADVISORY_METERS:
        risk.level = RiskLevel.MEDIUM
        risk.reason = "in the walking path at %.1f metres" % dist
        return risk

    if (closing is not None and closing > config.CLOSING_MIN_SPEED
            and dist is not None and dist <= config.WATCH_METERS):
        risk.level = RiskLevel.MEDIUM
        risk.reason = "moving toward you at %.1f metres" % dist
        return risk

    if in_path and dist is None and size_ratio >= config.RISK_BLOCKING_SIZE * 0.6:
        risk.level = RiskLevel.MEDIUM
        risk.reason = "partly blocking the view ahead"
        return risk

    # --------------------------------------------------------------------- LOW
    if dist is None:
        risk.reason = "visible, distance unknown"
    else:
        risk.reason = "not in your path at %.1f metres" % dist
    risk.level = RiskLevel.LOW
    return risk


def _sensor_level(dist_m: float) -> RiskLevel:
    if dist_m <= config.STOP_METERS:
        return RiskLevel.CRITICAL
    if dist_m <= config.URGENT_METERS:
        return RiskLevel.CRITICAL
    if dist_m <= config.ADVISORY_METERS:
        return RiskLevel.MEDIUM
    if dist_m <= config.WATCH_METERS:
        return RiskLevel.LOW
    return RiskLevel.NONE


def assess_scene(scene: Scene | None, sensor_dist_m: float | None = None
                 ) -> RiskReport:
    """Classify every visible object, plus the ultrasonic on its own.

    The ultrasonic matters because it sees walls, doors and steps that COCO
    cannot name. If it reports something close and the camera has no matching
    object, that is still a real hazard, just an unnamed one.
    """
    report = RiskReport()

    if scene is not None:
        for obj in scene.objects:
            if not obj.confirmed:
                continue
            report.objects.append(assess_object(obj, scene, sensor_dist_m))

    if sensor_dist_m is not None:
        level = _sensor_level(sensor_dist_m)
        if level != RiskLevel.NONE:
            # Only add it if no visible object already accounts for this
            # reading; otherwise the same obstacle gets reported twice.
            explained = any(
                r.in_path and r.dist_m is not None
                and r.dist_m <= sensor_dist_m + 1.0
                for r in report.objects)
            if not explained:
                report.objects.append(Risk(
                    level=level, label="obstacle", dist_m=sensor_dist_m,
                    zone="center", in_path=True, source="ultrasonic",
                    confidence=1.0,
                    reason="something is %.1f metres ahead" % sensor_dist_m))

    # Measured free space. This is the one signal that does not depend on
    # recognising anything: if the walkable surface ahead is gone, something is
    # there whether or not the model can name it.
    free = getattr(scene, "free_space", None) if scene is not None else None
    if free is not None and getattr(free, "valid", False) and free.center_blocked:
        explained = any(r.in_path and r.level >= RiskLevel.MEDIUM
                        for r in report.objects)
        if not explained:
            report.objects.append(Risk(
                level=RiskLevel.MEDIUM, label="obstacle", dist_m=None,
                zone="center", in_path=True, source="segmentation",
                confidence=1.0,
                reason="the walking surface ahead is blocked (%.0f%% walkable)"
                       % (free.center * 100.0)))

    if report.objects:
        ranked = sorted(
            report.objects,
            key=lambda r: (int(r.level),
                           -(r.ttc if r.ttc is not None else 99.0),
                           -(r.dist_m if r.dist_m is not None else 0.0)),
            reverse=True)
        report.primary = ranked[0]
        report.level = report.primary.level
    return report
