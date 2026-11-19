#!/usr/bin/env python3
"""Verify the SOS button wiring before trusting it.

Prints the live state of the button pin for 20 seconds so you can see whether
your two wires actually landed on a switch contact pair.

    python tools/test_sos.py

    python tools/test_sos.py --pin 22

Reading guide
-------------
    released  (should be the normal state)
    PRESSED   <-- when you push the button

If it never changes, the two wires are on legs that are internally shorted
together. Move ONE wire to the diagonally opposite leg.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import config                                    # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=int, default=config.SOS_PIN)
    parser.add_argument("--seconds", type=float, default=20.0)
    args = parser.parse_args()

    print("=" * 62)
    print(f" SOS button wiring test - GPIO {args.pin}")
    print("=" * 62)
    print(" Expected wiring:")
    print(f"   GPIO {args.pin}  (physical pin 11) -> one leg of the button")
    print("   GND     (physical pin  9)  -> the DIAGONAL opposite leg")
    print("   No resistor. Never use a 5V pin.")
    print()
    print(f" Press it a few times. Testing for {args.seconds:.0f} s...")
    print()

    backend = None
    is_pressed = None

    try:
        from gpiozero import Button
        button = Button(args.pin, pull_up=True, bounce_time=0.05)
        is_pressed = lambda: button.is_pressed          # noqa: E731
        backend = "gpiozero"
    except Exception:                                   # noqa: BLE001
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(args.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            is_pressed = lambda: GPIO.input(args.pin) == 0   # noqa: E731
            backend = "RPi.GPIO"
        except Exception as exc:                        # noqa: BLE001
            print("!! No GPIO library available.")
            print(f"   {exc}")
            print()
            print("   Install one:")
            print("     sudo apt install python3-gpiozero python3-rpi.gpio")
            print("   Or test without hardware: python -m smartcane --keyboard")
            print("   then type 'sos'.")
            return 1

    print(f" backend: {backend}\n")

    deadline = time.monotonic() + args.seconds
    previous = None
    presses = 0
    try:
        while time.monotonic() < deadline:
            state = bool(is_pressed())
            if state != previous:
                if state:
                    presses += 1
                    print(f"  PRESSED   ({presses})")
                else:
                    print("  released")
                previous = state
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            import RPi.GPIO as GPIO
            GPIO.cleanup(args.pin)
        except Exception:                               # noqa: BLE001
            pass

    print()
    print("-" * 62)
    if presses == 0:
        print(" RESULT: no presses detected.")
        print()
        print(" Most likely cause: both wires are on legs that are already")
        print(" connected inside the switch. On a 4-leg button the legs form")
        print(" two permanently-linked pairs. Move ONE wire to the")
        print(" DIAGONALLY OPPOSITE leg and try again.")
        print()
        print(" Second possibility: the pin number is wrong, or the wire is")
        print(" not making contact with the header hole.")
        return 1
    if previous:
        print(" RESULT: the button is still held down. Release it, or the")
        print(" wires are shorted to each other somewhere.")
        return 1
    print(f" RESULT: wiring works. {presses} press(es) detected on GPIO "
          f"{args.pin}.")
    print(" Start the cane with:  python -m smartcane --demo")
    print(" The log should say:   SOS button armed on GPIO "
          f"{args.pin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
