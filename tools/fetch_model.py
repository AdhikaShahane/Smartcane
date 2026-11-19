#!/usr/bin/env python3
"""Download an ADE20K semantic-segmentation model.

IMPORTANT: Ultralytics does **not** publish an ADE20K semantic model. Its
`*-seg.pt` weights are COCO *instance* segmentation - they outline objects and
cannot label floor, wall, path, door or stairs, which is the whole reason this
project moved off COCO.

What does exist is SegFormer fine-tuned on ADE20K, published with ONNX weights
by Xenova on HuggingFace. That is what this downloads. Quantised first because
it is roughly 4x faster on a Pi 4 CPU.

    python tools/fetch_model.py

If you have no internet on the Pi, download the file on a laptop and copy it
into models/ with the name shown below.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                                    # noqa: E402

TARGET = config.MODEL_DIR / "segformer-ade20k.onnx"

# (url, note) - tried in order. Quantised int8 first: on a Pi 4 it is the
# difference between ~1 s and ~0.3 s per frame.
SOURCES = [
    ("https://huggingface.co/Xenova/segformer-b1-finetuned-ade-512-512/"
     "resolve/main/onnx/model_quantized.onnx",
     "SegFormer-B1 ADE20K, int8 (recommended)"),
    ("https://huggingface.co/Xenova/segformer-b1-finetuned-ade-512-512/"
     "resolve/main/onnx/model.onnx",
     "SegFormer-B1 ADE20K, fp32"),
    ("https://huggingface.co/Xenova/segformer-b0-finetuned-ade-512-512/"
     "resolve/main/onnx/model_quantized.onnx",
     "SegFormer-B0 ADE20K, int8 (smallest, fastest)"),
]


def _download(url: str) -> bool:
    print(f"  GET {url.split('/onnx/')[-1]}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "smartcane"})
        with urllib.request.urlopen(req, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
            done = 0
            with open(TARGET, "wb") as handle:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r    {done/1e6:6.1f} / {total/1e6:.1f} MB",
                              end="", flush=True)
            print()
        return TARGET.exists() and TARGET.stat().st_size > 1_000_000
    except Exception as exc:                            # noqa: BLE001
        print(f"    failed: {exc}")
        if TARGET.exists():
            TARGET.unlink()
        return False


def main() -> int:
    print("=" * 64)
    print(" ADE20K segmentation model")
    print("=" * 64)

    if TARGET.exists():
        print(f"already present: {TARGET} "
              f"({TARGET.stat().st_size / 1e6:.1f} MB)")
        return 0

    for url, note in SOURCES:
        print(f"\n--> {note}")
        if _download(url):
            print(f"    saved to {TARGET}")
            break
    else:
        print("\n" + "=" * 64)
        print(" Download failed.")
        print("=" * 64)
        print("No internet on the Pi, or the HuggingFace repo moved.")
        print("Fix: on a laptop, download")
        print("  https://huggingface.co/Xenova/segformer-b1-finetuned-ade-512-512")
        print("     /resolve/main/onnx/model_quantized.onnx")
        print(f"and copy it to  {TARGET}")
        print("Then run:  pip install onnxruntime")
        return 1

    try:
        import onnxruntime as ort
        print(f"\n==> onnxruntime {ort.__version__}")
        session = ort.InferenceSession(
            str(TARGET), providers=["CPUExecutionProvider"])
        shape = session.get_inputs()[0].shape
        out = session.get_outputs()[0].shape
        print(f"    input  {shape}")
        print(f"    output {out}")
        if len(out) >= 2 and (out[1] == 150 or out[-1] == 150):
            print("    OK - 150 ADE20K classes confirmed")
        else:
            print("    WARNING: output does not look like 150 classes")
    except ImportError:
        print("\n!! onnxruntime is not installed:")
        print("     pip install onnxruntime")
        print("   The model is downloaded but cannot run yet.")
        return 1
    except Exception as exc:                            # noqa: BLE001
        print(f"\n!! could not open the model: {exc}")
        return 1

    print("\nDone. Restart smartcane; the log should say:")
    print("    segmentation model: segformer-ade20k.onnx (onnx)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
