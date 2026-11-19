#!/usr/bin/env python3
"""Train a semantic-segmentation model on ADE20K.

Only needed if tools/fetch_model.py could not find a pretrained checkpoint.
ADE20K is ~1 GB and training on a Pi 4 CPU is slow (many hours). Train on a
laptop or Colab and copy the resulting .pt into models/.

    python tools/train_segmentation.py --epochs 30 --imgsz 320

The dataset is not downloaded automatically: get ADEChallengeData2016.zip from
http://sceneparsing.csail.mit.edu/ and extract it into `datasets/`. Full
instructions: https://docs.ultralytics.com/datasets/semantic/ade20k
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                                    # noqa: E402

BASE_MODELS = ["yolo11n-seg.pt", "yolov8n-seg.pt"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--data", default="ade20k.yaml")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("pip install ultralytics")
        return 1

    dataset = Path("datasets") / "ADEChallengeData2016"
    if not dataset.exists():
        print("ADE20K is not in datasets/ADEChallengeData2016")
        print("Download ADEChallengeData2016.zip (~1 GB) from")
        print("  http://sceneparsing.csail.mit.edu/")
        print("and extract it so that datasets/ADEChallengeData2016/images exists.")
        return 1

    model = None
    for name in BASE_MODELS:
        try:
            model = YOLO(name)
            print(f"base model: {name}")
            break
        except Exception as exc:        # noqa: BLE001
            print(f"  {name} unavailable: {exc}")
    if model is None:
        print("no base segmentation model available")
        return 1

    print(f"training on {args.data} for {args.epochs} epochs at {args.imgsz}px")
    results = model.train(data=args.data, epochs=args.epochs,
                          imgsz=args.imgsz, batch=args.batch)

    best = Path(getattr(results, "save_dir", "runs")) / "weights" / "best.pt"
    if not best.exists():
        print(f"training finished but {best} was not found")
        return 1

    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.MODEL_DIR / "smartcane-seg.pt"
    shutil.copy(best, dest)
    print(f"\nsaved {dest}")
    print("Restart smartcane; the segmentation model is picked up automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
