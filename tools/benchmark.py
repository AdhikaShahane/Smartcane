#!/usr/bin/env python3
"""Measure the parts of the pipeline that run on the CPU.

Object detection needs PyTorch/ultralytics and is measured separately on the
Pi (see docs/DEPLOY.md); everything else is pure Python and is measured here
so the decision layer's cost is a known quantity rather than a guess.

    python tools/benchmark.py
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                                    # noqa: E402
from smartcane.guidance import Guidance                         # noqa: E402
from smartcane.intent import classify                           # noqa: E402
from smartcane.risk import assess_scene                         # noqa: E402
from smartcane.vision import Scene, TrackedObject               # noqa: E402


def build_scene(count: int = 6) -> Scene:
    scene = Scene(at=1.0, frame_width=640, frame_height=480)
    labels = ["person", "chair", "table", "bottle", "dog", "car"]
    zones = ["center", "left", "right", "left", "right", "center"]
    for i in range(count):
        label = labels[i % len(labels)]
        real_h = config.OBJ_HEIGHTS.get(label, 1.0)
        dist = 1.0 + i * 0.8
        box_h = real_h * config.FOCAL_PX / dist
        obj = TrackedObject(
            tid=i + 1, label=label, x=100 + i * 90, y=240, box_h=box_h,
            box_w=box_h * 0.6, zone=zones[i % len(zones)], hits=5,
            last_seen=1.0, dist_m=dist, best_conf=0.8)
        for k in range(5):
            obj.history.append((obj.x, 240, box_h, dist, k * 0.2))
        scene.objects.append(obj)
    return scene


def bench(name: str, fn, iterations: int = 2000) -> float:
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000.0)
    mean = statistics.mean(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    print(f"  {name:<34} mean {mean:7.3f} ms   p95 {p95:7.3f} ms")
    return mean


class Sensor:
    dist_m = 1.4
    valid = True
    updated_at = 0.0


def main() -> int:
    print("=" * 62)
    print(" Sahayak Drishti - CPU-side benchmark")
    print("=" * 62)

    scene = build_scene(6)
    sensor = Sensor()
    guidance = Guidance(step_len=config.STEP_M)

    total = 0.0
    print("\ndecision layer (pure Python)")
    total += bench("intent classification",
                   lambda: classify("what is in front of me"))
    total += bench("risk assessment (6 objects)",
                   lambda: assess_scene(scene, sensor.dist_m))
    total += bench("full situation assessment",
                   lambda: guidance.assess(sensor, scene))
    total += bench("announcement phrasing",
                   lambda: guidance._phrase(
                       guidance.assess(sensor, scene), scene))
    total += bench("describe (multi-object)",
                   lambda: guidance.describe(sensor, scene))
    total += bench("bypass planning",
                   lambda: guidance.bypass(sensor, scene))

    print(f"\n  {'sum of decision layer':<34} {total:7.3f} ms per cycle")
    print("\nnote: object detection is NOT included. It dominates the frame")
    print("      budget and is measured on the Pi:")
    print("        PyTorch @320   ~300 ms/frame   (measured on the Pi)")
    print("        ncnn    @320   ~80-130 ms/frame (after tools/optimize_model.py)")
    print(f"\n  camera frame budget at {config.DETECT_FPS} fps target = "
          f"{1000.0 / config.DETECT_FPS:.0f} ms")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
