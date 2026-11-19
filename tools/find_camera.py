#!/usr/bin/env python3
"""Work out where the camera actually is, and remember it.

Run this on the Pi when the camera does not appear, or before the demo. It
prints the network facts instead of leaving you to guess:

    python tools/find_camera.py

    python tools/find_camera.py --save     # remember the best result

What it checks, in order:
  1. the Pi's own address, subnet and gateway
  2. the URL the cane currently remembers, and whether it answers
  3. a parallel scan of this subnet for anything serving a webcam
  4. each hit is actually opened, so "the port is open" is not mistaken for
     "the video works"
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                                    # noqa: E402
from smartcane.camera import discover_ip_webcams                # noqa: E402


def local_address() -> tuple[str | None, str | None]:
    """(ip, subnet in /24 form) for the interface that reaches the internet."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))          # no packet is sent
        ip = sock.getsockname()[0]
        sock.close()
    except Exception as exc:                        # noqa: BLE001
        print(f"  cannot determine local address: {exc}")
        return None, None
    if ip.startswith("127."):
        return None, None
    return ip, ip.rsplit(".", 1)[0] + ".0/24"


def default_gateway() -> str:
    for command in (["ip", "route", "show", "default"],
                    ["ip", "route"]):
        try:
            out = subprocess.run(command, capture_output=True, text=True,
                                 timeout=3).stdout
            for line in out.splitlines():
                if "default via" in line:
                    return line.split("default via")[1].split()[0]
        except Exception:                           # noqa: BLE001
            continue
    return "unknown"


def responds(url: str, timeout: float = 1.5) -> str:
    """Short description of whether the URL answers at all."""
    try:
        host = url.split("//", 1)[1].split("/")[0]
        hostname, _, port = host.partition(":")
        with socket.create_connection((hostname, int(port or 80)),
                                      timeout=timeout):
            return "port open"
    except Exception as exc:                        # noqa: BLE001
        return f"unreachable ({type(exc).__name__})"


def try_open(url: str) -> str | None:
    """Open the stream and report its size, or None if it does not work."""
    try:
        import cv2
    except ImportError:
        return "opencv not installed - cannot verify the video"
    try:
        cap = cv2.VideoCapture(url)
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok or frame is None:
            return None
        height, width = frame.shape[:2]
        return f"video OK, {width}x{height}"
    except Exception as exc:                        # noqa: BLE001
        return f"open failed: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true",
                        help="write the best working URL to the cache")
    args = parser.parse_args()

    print("=" * 64)
    print(" Camera discovery")
    print("=" * 64)

    ip, subnet = local_address()
    print(f"\n1. This Pi")
    print(f"   address : {ip or 'unknown'}")
    print(f"   subnet  : {subnet or 'unknown'}")
    print(f"   gateway : {default_gateway()}")
    if ip is None:
        print("\n   The Pi has no network address. Join the hotspot first:")
        print('     sudo nmcli device wifi connect "NAME" password "PASS"')
        return 1

    print(f"\n2. Remembered URL")
    cached = None
    try:
        cached = config.CAMERA_CACHE.read_text(encoding="utf-8").strip()
    except Exception:                               # noqa: BLE001
        pass
    if cached:
        print(f"   {cached}")
        print(f"   {responds(cached)}")
    else:
        print("   none - the cane has not found a camera yet")

    print(f"\n3. Scanning {subnet} for port {config.CAMERA_SCAN_PORT}")
    found = discover_ip_webcams()
    if not found:
        print("   nothing found.")
        print("\n   Most likely causes:")
        print("     - the camera phone is on a DIFFERENT network")
        print("     - this hotspot uses client isolation")
        print("     - IP Webcam is not running on the phone")
        print("     - the hotspot subnet is bigger than /24, so the scan")
        print("       only covers this slice")
        return 1

    print(f"\n4. Checking each candidate")
    working: list[str] = []
    for url in found:
        print(f"   {url}")
        status = try_open(url)
        print(f"      {status or 'port open but no video'}")
        if status and status.startswith("video OK"):
            working.append(url)

    print("\n" + "-" * 64)
    if not working:
        print(" No candidate delivered video.")
        print(" The port is open somewhere, but the stream is not usable.")
        print(" Check IP Webcam is actually serving, not just listening.")
        return 1

    best = working[0]
    print(f" Working camera: {best}")
    if len(working) > 1:
        print(f" ({len(working)} worked; using the first)")
    if args.save:
        config.CAMERA_CACHE.write_text(best + "\n", encoding="utf-8")
        print(f" Saved to {config.CAMERA_CACHE}")
        print(" The cane will use this address on its next start.")
    else:
        print("\n To remember it:")
        print("   python tools/find_camera.py --save")
    return 0


if __name__ == "__main__":
    sys.exit(main())
