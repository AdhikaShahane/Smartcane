#!/usr/bin/env python3
"""Calibrate the user's stride length.

Step counts are only useful if one step is *their* step. The population
default is 0.65 m, which is wrong for most people; a 20% error turns
"walk four steps" into "walk three" and the user stops short of the object.

Procedure: mark a start line, walk a known number of normal steps, measure the
distance covered, and this writes the result to ~/.smartcane_stride.

    python tools/calibrate_stride.py
    python tools/calibrate_stride.py --distance 7.5 --steps 10
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                              # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distance", type=float,
                        help="metres walked (omit to be prompted)")
    parser.add_argument("--steps", type=int, default=10,
                        help="number of steps taken (default 10)")
    args = parser.parse_args()

    print("=" * 60)
    print(" Stride calibration")
    print("=" * 60)
    print("1. Stand at a start mark on flat ground.")
    print(f"2. Walk {args.steps} normal steps and stop.")
    print("3. Measure the distance from the start mark to your front foot.")
    print()

    distance = args.distance
    if distance is None:
        try:
            distance = float(input(f"Distance covered in metres: ").strip())
        except (ValueError, EOFError):
            print("need a number, for example 7.5")
            return 1

    if distance <= 0:
        print("distance must be positive")
        return 1

    stride = distance / args.steps
    if not (config.STEP_MIN <= stride <= config.STEP_MAX):
        print(f"\nThat gives {stride:.2f} m per step, which is outside the "
              f"human range ({config.STEP_MIN}-{config.STEP_MAX} m).")
        print("Check the measurement and try again.")
        return 1

    config.STRIDE_FILE.write_text(f"{stride:.3f}\n", encoding="utf-8")
    print()
    print(f"stride = {distance:.2f} m / {args.steps} steps = {stride:.3f} m")
    print(f"saved to {config.STRIDE_FILE}")
    print()
    print("Restart smartcane and it will use this. A 2 m obstacle now reads")
    print(f"as {round(2.0 / stride)} steps instead of "
          f"{round(2.0 / config.STEP_DEFAULT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
