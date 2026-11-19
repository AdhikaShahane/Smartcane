#!/usr/bin/env python3
"""Scenario tests for the risk engine and navigation planner.

These are the twelve scenarios from the specification. Each one builds a
synthetic scene, runs the real decision code, and prints what it actually
said - so the result is recorded, not assumed.

    python tests/scenarios.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                                   # noqa: E402
from smartcane.guidance import Guidance                        # noqa: E402
from smartcane.risk import RiskLevel, assess_object, assess_scene  # noqa: E402
from smartcane.vision import Scene, TrackedObject              # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))


class Sensor:
    def __init__(self, metres: float | None) -> None:
        self.dist_cm = None if metres is None else metres * 100.0
        self.updated_at = float("inf")
        self.valid = metres is not None

    @property
    def dist_m(self) -> float | None:
        return None if self.dist_cm is None else self.dist_cm / 100.0


def make_object(label: str, zone: str, dist: float, conf: float = 0.9,
                approach_from: float | None = None,
                approach_seconds: float = 1.0,
                frame_h: int = 480) -> TrackedObject:
    """Build a tracked object, optionally with a motion history.

    The horizontal position must match the zone, otherwise the corridor
    overlap says "in the path" for an object that is plainly off to the side.
    """
    cx = {"center": 320.0, "left": 100.0, "right": 540.0}.get(zone, 320.0)
    real_h = config.ADE20K_HEIGHTS.get(label, 1.0)
    box_h = real_h * config.FOCAL_PX / max(0.3, dist)
    obj = TrackedObject(tid=1, label=label, x=cx, y=240, box_h=box_h,
                        box_w=box_h * 0.6, zone=zone, hits=5,
                        last_seen=approach_seconds, dist_m=dist,
                        best_conf=conf, label_stable=True,
                        label_votes={label: 5})
    start = approach_from if approach_from is not None else dist
    steps = 5
    for i in range(steps):
        frac = i / (steps - 1)
        t = frac * approach_seconds
        d = start + (dist - start) * frac
        h = real_h * config.FOCAL_PX / max(0.3, d)
        obj.history.append((cx, 240, h, d, t))
    obj.dist_m = dist
    return obj


def scene_with(*objects: TrackedObject, frame_h: int = 480) -> Scene:
    scene = Scene(at=1.0, frame_width=640, frame_height=frame_h)
    scene.objects.extend(objects)
    return scene


def show(text: str) -> None:
    print(f'        -> "{text}"')


# ---------------------------------------------------------------------------
def s1_chair_safe() -> None:
    print("\n[1] Chair at a safe distance (3 m, to the right)")
    g = Guidance(step_len=0.65)
    scene = scene_with(make_object("chair", "right", 3.0))
    risk = assess_object(scene.objects[0], scene)
    text = g.describe(Sensor(None), scene)
    show(text)
    check("identifies the chair", "chair" in text.lower(), text)
    check("gives a distance", "metre" in text.lower(), text)
    check("classed LOW, not a hazard", risk.level == RiskLevel.LOW,
          risk.level.word)


def s2_chair_blocking() -> None:
    print("\n[2] Chair blocking the walking path (1.2 m, centre)")
    g = Guidance(step_len=0.65)
    scene = scene_with(make_object("chair", "center", 1.2),
                       make_object("table", "right", 1.4))
    scene.objects[1].tid = 2
    risk = assess_object(scene.objects[0], scene)
    answer = g.bypass(Sensor(1.2), scene)
    show(answer)
    check("chair in path is at least MEDIUM",
          risk.level >= RiskLevel.MEDIUM, risk.level.word)
    check("suggests going around", "around" in answer.lower(), answer)
    check("names a direction", ("left" in answer.lower()
                                or "right" in answer.lower()), answer)


def s3_car_approaching() -> None:
    print("\n[3] Moving car approaching (5 m -> 3 m in 0.8 s)")
    g = Guidance(step_len=0.65)
    obj = make_object("car", "center", 3.0, approach_from=5.0,
                      approach_seconds=0.8)
    scene = scene_with(obj)
    risk = assess_object(obj, scene)
    print(f"        closing={obj.closing_speed:.2f} m/s  "
          f"ttc={obj.time_to_collision:.2f} s")
    sit = g.assess(Sensor(None), scene)
    ann = g.announce(sit, now=100.0, scene=scene)
    show(ann.text if ann else "(silent)")
    check("escalates to CRITICAL", risk.level == RiskLevel.CRITICAL,
          risk.level.word)
    check("time-to-collision under 1.5 s",
          obj.time_to_collision is not None
          and obj.time_to_collision <= config.TTC_CRITICAL_SEC,
          f"{obj.time_to_collision}")
    check("speaks a stop with the object named",
          ann is not None and "car" in ann.text.lower()
          and ann.text.startswith("Stop!"), ann.text if ann else "silent")


def s4_person_from_left() -> None:
    print("\n[4] Person approaching from the left (2.5 m -> 1.8 m)")
    g = Guidance(step_len=0.65)
    obj = make_object("person", "left", 1.8, approach_from=2.5,
                      approach_seconds=1.0)
    scene = scene_with(obj)
    risk = assess_object(obj, scene)
    text = g.describe(Sensor(None), scene)
    show(text)
    check("identifies the person", "person" in text.lower(), text)
    check("identifies the side", "left" in text.lower(), text)
    check("risk is at least LOW", risk.level >= RiskLevel.LOW,
          risk.level.word)


def s5_obstacle_ahead() -> None:
    print("\n[5] Obstacle directly ahead (0.9 m then 0.7 m, centre)")
    g = Guidance(step_len=0.65)

    scene = scene_with(make_object("person", "center", 0.9))
    sit = g.assess(Sensor(0.9), scene)
    ann = g.announce(sit, now=200.0, scene=scene)
    show(ann.text if ann else "(silent)")
    check("0.9 m gives an immediate, actionable instruction",
          ann is not None
          and ("turn" in ann.text.lower() or "stop" in ann.text.lower()),
          ann.text if ann else "silent")

    closer = scene_with(make_object("person", "center", 0.7))
    sit2 = g.assess(Sensor(0.7), closer)
    ann2 = g.announce(sit2, now=400.0, scene=closer)
    show(ann2.text if ann2 else "(silent)")
    check("0.7 m is a stop condition", sit2.state in ("stop", "urgent"),
          sit2.state)
    check("stop explains itself",
          ann2 is not None and len(ann2.text) > 25,
          ann2.text if ann2 else "silent")


def s6_clear_path() -> None:
    print("\n[6] Clear path")
    g = Guidance(step_len=0.65)
    scene = scene_with()
    text = g.steps_to_walk(Sensor(None), scene)
    show(text)
    check("guides forward", "straight" in text.lower() or
          "clear" in text.lower(), text)
    check("does not invent an obstacle",
          "blocked" not in text.lower(), text)


def s7_multiple_obstacles() -> None:
    print("\n[7] Multiple obstacles (person centre, chair right, table left)")
    g = Guidance(step_len=0.65)
    person = make_object("person", "center", 1.3)
    chair = make_object("chair", "right", 1.5)
    chair.tid = 2
    table = make_object("table", "left", 2.0)
    table.tid = 3
    scene = scene_with(person, chair, table)
    text = g.describe_all(Sensor(1.3), scene)
    answer = g.bypass(Sensor(1.3), scene)
    show(text)
    show(answer)
    check("names more than one object",
          sum(w in text.lower() for w in ("person", "chair", "table")) >= 2,
          text)
    check("evaluates a side", ("left" in answer.lower()
                               or "right" in answer.lower()), answer)


def s8_very_close() -> None:
    print("\n[8] Object very close (0.35 m)")
    g = Guidance(step_len=0.65)
    scene = scene_with(make_object("chair", "center", 0.35))
    sit = g.assess(Sensor(0.35), scene)
    ann = g.announce(sit, now=300.0, scene=scene)
    show(ann.text if ann else "(silent)")
    check("state is stop", sit.state == "stop", sit.state)
    check("starts with Stop!", ann is not None
          and ann.text.startswith("Stop!"), ann.text if ann else "silent")
    check("names the object", ann is not None
          and "chair" in ann.text.lower(), ann.text if ann else "silent")
    check("gives centimetres when very close", ann is not None
          and "centimetres" in ann.text.lower(), ann.text if ann else "silent")


def s9_steps_with_stride() -> None:
    print("\n[9] Step calculation with a calibrated stride")
    short = Guidance(step_len=0.55)
    long_ = Guidance(step_len=0.80)
    scene = scene_with(make_object("chair", "center", 2.2))
    a = short.reach_object(scene.objects[0], scene)
    b = long_.reach_object(scene.objects[0], scene)
    show(f"stride 0.55 m: {a}")
    show(f"stride 0.80 m: {b}")
    check("stride changes the step count", a != b, f"{a} | {b}")
    check("both mention steps", "step" in a.lower() and "step" in b.lower())


def s10_bypass_instruction() -> None:
    print("\n[10] User asks to bypass an obstacle")
    g = Guidance(step_len=0.65)
    scene = scene_with(make_object("chair", "center", 1.4),
                       make_object("table", "right", 1.1))
    scene.objects[1].tid = 2
    answer = g.bypass(Sensor(1.4), scene)
    show(answer)
    check("gives a direction", ("left" in answer.lower()
                                or "right" in answer.lower()), answer)
    check("gives a step count", "step" in answer.lower(), answer)
    check("turns away from the blocked side",
          "left" in answer.lower(), answer)


def s11_passed() -> None:
    print("\n[11] Obstacle has been bypassed")
    before = scene_with(make_object("chair", "center", 2.0))
    after = scene_with()          # chair no longer detected
    still = [o for o in after.objects if o.label == "chair"]
    check("object is gone from the scene", not still, str(len(still)))
    check("scene reports nothing ahead",
          len(after.corridor(hazard_only=True)) == 0,
          str(len(after.corridor(hazard_only=True))))
    g = Guidance(step_len=0.65)
    text = g.steps_to_walk(Sensor(None), after)
    show(text)
    check("invites the user to continue",
          "clear" in text.lower() or "straight" in text.lower(), text)


def s12_uncertain() -> None:
    print("\n[12] Detection uncertain (30% confidence, no distance)")
    g = Guidance(step_len=0.65)
    obj = make_object("chair", "center", 2.0, conf=0.30)
    obj.dist_m = None             # height unknown -> no distance
    obj.history.clear()
    scene = scene_with(obj)
    risk = assess_object(obj, scene)
    text = g.reach_object(obj, scene)
    show(text)
    check("flagged as uncertain", risk.uncertain, str(risk.uncertain))
    check("not escalated to critical on a weak detection",
          risk.level < RiskLevel.CRITICAL, risk.level.word)
    check("refuses to invent a distance",
          "cannot estimate" in text.lower() or "closer" in text.lower(), text)


def s13_contradiction() -> None:
    print("\n[13] No contradictory instructions in one breath")
    g = Guidance(step_len=0.65)
    scene = scene_with(make_object("chair", "center", 1.3),
                       make_object("table", "left", 1.2))
    scene.objects[1].tid = 2
    answer = g.bypass(Sensor(1.3), scene)
    show(answer)
    turns = [w for w in ("left", "right") if w in answer.lower()]
    check("mentions exactly one direction", len(turns) <= 1, str(turns))


def s14_free_space() -> None:
    print("\n[14] Measured free space decides the direction")
    from smartcane.segmentation import free_space_from_mask, synthetic_mask

    g = Guidance(step_len=0.65)
    scene = scene_with()
    scene.free_space = free_space_from_mask(synthetic_mask(blocked="center"))
    direction = g.best_direction(scene)
    show(f"{scene.free_space.describe()} -> turn {direction}")
    check("measured free space picks the open side",
          direction == "left", str(direction))

    blocked = scene_with()
    blocked.free_space = free_space_from_mask(synthetic_mask(blocked="all"))
    d2 = g.best_direction(blocked)
    show(f"{blocked.free_space.describe()} -> turn {d2}")
    check("fully blocked offers no direction", d2 is None, str(d2))

    report = assess_scene(scene)
    check("a blocked walking surface raises a risk even unnamed",
          report.level >= RiskLevel.MEDIUM, report.level.word)


def s15_door_and_wall() -> None:
    print("\n[15] Door and wall - classes that do not exist in COCO")
    g = Guidance(step_len=0.65)
    scene = scene_with(make_object("door", "center", 1.0))
    risk = assess_object(scene.objects[0], scene)
    text = g.describe(Sensor(None), scene)
    show(text)
    check("door is detected and named", "door" in text.lower(), text)
    check("door in the path is a hazard",
          risk.level >= RiskLevel.MEDIUM, risk.level.word)

    wall = scene_with(make_object("wall", "left", 1.5))
    r2 = assess_object(wall.objects[0], wall)
    check("wall is classified", r2.level >= RiskLevel.LOW, r2.level.word)
    stairs = scene_with(make_object("stairs", "center", 1.4))
    r3 = assess_object(stairs.objects[0], stairs)
    check("stairs are a hazard", r3.level >= RiskLevel.MEDIUM, r3.level.word)


def main() -> int:
    print("=" * 66)
    print(" Sahayak Drishti - scenario tests (ADE20K)")
    print("=" * 66)
    s1_chair_safe()
    s2_chair_blocking()
    s3_car_approaching()
    s4_person_from_left()
    s5_obstacle_ahead()
    s6_clear_path()
    s7_multiple_obstacles()
    s8_very_close()
    s9_steps_with_stride()
    s10_bypass_instruction()
    s11_passed()
    s12_uncertain()
    s13_contradiction()
    s14_free_space()
    s15_door_and_wall()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [name for name, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 66)
    print(f" RESULT: {passed}/{len(RESULTS)} checks passed")
    if failed:
        print(" FAILED:")
        for name in failed:
            print(f"   - {name}")
    print("=" * 66)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
