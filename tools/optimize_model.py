#!/usr/bin/env python3
"""Export yolov8n to a faster runtime for the Pi.

Measured on a Raspberry Pi 4 (ncnn, 1950 MHz, inference only):

    YOLOv8n 640x640  PyTorch   ~1.5-3 FPS
    YOLOv8n 320x320  ncnn      ~4x faster than the above

vision.py picks whichever artifact exists, preferring ncnn then ONNX then .pt,
so running this once is enough — no configuration change needed.

Usage:
    python tools/optimize_model.py            # both ncnn and onnx
    python tools/optimize_model.py --onnx     # onnx only
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
SRC = MODELS / "yolov8n.pt"
IMGSZ = 320


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", action="store_true", help="export ONNX only")
    args = parser.parse_args()

    if not SRC.exists():
        print(f"error: {SRC} not found")
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print("error: ultralytics not installed (pip install ultralytics)")
        return 1

    model = YOLO(str(SRC))
    formats = ["onnx"] if args.onnx else ["ncnn", "onnx"]

    for fmt in formats:
        print(f"\n=== exporting {fmt} at {IMGSZ}px ===")
        try:
            out = model.export(format=fmt, imgsz=IMGSZ)
        except Exception as exc:                        # noqa: BLE001
            print(f"  failed: {exc}")
            continue
        out_path = Path(str(out))
        print(f"  produced: {out_path}")
        if not out_path.exists():
            print("  warning: export path does not exist, skipping move")
            continue
        target = MODELS / out_path.name
        if target.exists():
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        shutil.move(str(out_path), str(target))
        print(f"  moved to: {target}")

    print("\nDone. Restart the system; vision.py will pick the new model up.")
    print("Check the log for:  detector: <name> (ncnn|onnx|pytorch)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
