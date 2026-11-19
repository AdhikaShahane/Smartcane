#!/usr/bin/env python3
"""Fetch an ADE20K semantic-segmentation model into models/.

The cane needs a model that labels floor, sidewalk, path, road, door, wall,
stairs and step - none of which exist in COCO. Ultralytics names its
ADE20K semantic models inconsistently between releases, so this tries each
known name and reports exactly which one resolved.

    python tools/fetch_model.py

If nothing downloads, train one yourself:

    python tools/train_segmentation.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                                    # noqa: E402

# Tried in order. YOLO() downloads from the Ultralytics asset host when the
# name exists there.
CANDIDATES = [
    "yolo11n-sem-ade20k.pt",
    "yolo26n-sem-ade20k.pt",
    "yolo11s-sem-ade20k.pt",
]


def main() -> int:
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics is not installed.")
        print("  pip install ultralytics")
        return 1

    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 62)
    print(" Looking for an ADE20K semantic-segmentation checkpoint")
    print("=" * 62)

    for name in CANDIDATES:
        print(f"\n--> trying {name}")
        try:
            model = YOLO(name)          # downloads if the asset exists
        except Exception as exc:        # noqa: BLE001
            print(f"    not available: {exc}")
            continue
        src = Path(getattr(model, "ckpt_path", name) or name)
        if not src.exists():
            src = Path(name)
        if not src.exists():
            print("    downloaded but the file was not found on disk")
            continue
        dest = config.MODEL_DIR / src.name
        if src.resolve() != dest.resolve():
            shutil.move(str(src), str(dest))
        print(f"    saved to {dest}")
        print("\nDone. Restart smartcane; the log should say:")
        print("    segmentation model: " + dest.name)
        return 0

    print("\n" + "=" * 62)
    print(" No pretrained ADE20K checkpoint resolved.")
    print("=" * 62)
    print("Ultralytics does not always publish these weights. Two options:")
    print()
    print("1. Train one on ADE20K (about 1 GB download, several hours CPU):")
    print("     python tools/train_segmentation.py")
    print()
    print("2. Run without segmentation. The cane falls back to the legacy")
    print("   detector, which cannot see doors, walls or stairs. It will say")
    print("   so in the log.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
