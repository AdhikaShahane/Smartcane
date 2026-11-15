#!/usr/bin/env python3
"""Smoke tests that need no hardware.

Run on the Pi or a laptop:

    python tests/smoke_test.py

These exist because the demo is remote: whoever is holding the Pi needs a way to
tell "the code is broken" from "the wiring is broken" in ten seconds.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartcane import intent                                   # noqa: E402
from smartcane.guidance import (Guidance, Priority, State,      # noqa: E402
                                steps_available, step_length_from_gait)
from smartcane.audio_out import make_earcon                     # noqa: E402

FAILS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail else ""))
    if not condition:
        FAILS.append(name)


class FakeSensor:
    """Minimal stand-in for link.SensorState."""

    def __init__(self, metres: float | None) -> None:
        self.dist_cm = None if metres is None else metres * 100.0
        self.updated_at = float("inf")
        self.valid = metres is not None

    @property
    def dist_m(self) -> float | None:
        return None if self.dist_cm is None else self.dist_cm / 100.0


def test_intent() -> None:
    print("intent matching")
    cases = {
        "what is ahead": intent.Intent.WHAT_AHEAD,
        "what's ahead": intent.Intent.WHAT_AHEAD,
        "turn left": intent.Intent.LEFT,
        "move right": intent.Intent.RIGHT,
        "stop": intent.Intent.STOP,
        "is the path clear": intent.Intent.IS_SAFE,
        "how many steps": intent.Intent.HOW_FAR,
        "repeat": intent.Intent.REPEAT,
        "describe the scene": intent.Intent.DESCRIBE,
    }
    for text, expected in cases.items():
        cmd, score, _ = intent.classify(text)
        check(f"{text!r} -> {expected.value}", cmd is expected, f"{score:.0f}")

    # bare direction words must NOT trigger: they are common in conversation
    for text in ("left", "right", "i left my bag at home", "hello there"):
        cmd, _, _ = intent.classify(text)
        check(f"{text!r} stays unknown", cmd is intent.Intent.UNKNOWN, cmd.value)


def test_no_false_triggers() -> None:
    """The safety property of an always-listening cane.

    These assertions must hold identically whether rapidfuzz is installed or the
    difflib fallback is used. They caught a real bug: `partial_ratio("left",
    "turn left")` scores 100, so a bare "left" heard in conversation fired a
    turn command. Never use a substring scorer for command matching.
    """
    print("false-trigger guards")
    directional = (intent.Intent.LEFT, intent.Intent.RIGHT,
                   intent.Intent.STRAIGHT)
    for word in ("left", "right", "straight", "forward", "ahead"):
        cmd, score, _ = intent.classify(word)
        check(f"bare {word!r} is not a direction command",
              cmd not in directional, f"{cmd.value} {score:.0f}")

    # ordinary conversation must never become a command
    for sentence in (
        "i left my bag at home",
        "hello there",
        "can you turn the light on",
        "she went right past me",
        "we should stop for coffee later",
        "the weather was nice yesterday",
        "okay",
        "um",
    ):
        cmd, score, _ = intent.classify(sentence)
        check(f"{sentence!r} is not a command",
              cmd is intent.Intent.UNKNOWN, f"{cmd.value} {score:.0f}")

    # the real commands must still work
    for text, expected in (("turn left", intent.Intent.LEFT),
                           ("move right", intent.Intent.RIGHT),
                           ("go straight", intent.Intent.STRAIGHT),
                           ("stop", intent.Intent.STOP)):
        cmd, score, _ = intent.classify(text)
        check(f"{text!r} still works", cmd is expected, f"{score:.0f}")


def test_steps() -> None:
    print("step maths")
    check("Weinberg in human range",
          0.30 <= step_length_from_gait(12.0, 10.0) <= 1.10)
    check("no steps when too close", steps_available(0.9, 0.65) == 0)
    check("capped by sensor horizon", steps_available(9.0, 0.65) <= 3)
    check("1.5 m gives 1 step", steps_available(1.5, 0.65) == 1)
    check("2.0 m gives 2 steps", steps_available(2.0, 0.65) == 2)


def test_state_machine() -> None:
    print("state machine")
    g = Guidance(step_len=0.65)
    t = 1000.0
    seen: list[str] = []
    texts: list[str] = []
    for dist in (2.6, 2.0, 1.6, 1.2, 0.9, 0.7, 0.5, 0.35, 0.2):
        t += 0.5
        sit = g.assess(FakeSensor(dist), None)
        seen.append(sit.state)
        ann = g.announce(sit, now=t)
        if ann is not None:
            texts.append(ann.text)

    check("reaches STOP", State.STOP in seen, ",".join(dict.fromkeys(seen)))
    check("urgent or stop spoken", any(
        ("Stop" in s) or ("very close" in s) for s in texts))
    check("something was announced", bool(texts), f"{len(texts)} utterances")

    # distance and step count must never contradict each other
    bad = []
    for dist in (1.1, 1.4, 1.6, 1.9, 2.0):
        g2 = Guidance(step_len=0.65)
        sit = g2.assess(FakeSensor(dist), None)
        ann = g2.announce(sit, now=2000.0)
        if ann is None:
            continue
        text = ann.text
        if "Walk straight" in text and "metres" in text:
            n = int(text.split("Walk straight ")[1].split()[0])
            m = float(text.split("about ")[1].split(" metre")[0])
            if abs(n * 0.65 - (min(m, 2.0) - 0.5)) > 0.8:
                bad.append(f"{m}m/{n}steps")
    check("distance and steps agree", not bad, ", ".join(bad))

    # an urgent warning must not be swallowed by the advisory cooldown
    g3 = Guidance(step_len=0.65)
    t = 3000.0
    sit_a = g3.assess(FakeSensor(1.5), None)
    g3.announce(sit_a, now=t)
    sit_u = g3.assess(FakeSensor(0.7), None)
    ann = g3.announce(sit_u, now=t + 0.9)
    check("urgent survives cooldown", ann is not None,
          ann.text if ann else "SUPPRESSED")


def test_earcons() -> None:
    print("earcons")
    for kind in ("stop", "urgent", "advisory", "ok"):
        pcm = make_earcon(kind)
        check(f"{kind} generated", pcm.size > 0 and pcm.shape[1] == 2,
              f"{pcm.shape[0]} samples")


def main() -> int:
    print("=" * 60)
    print(" Sahayak Drishti - smoke tests (no hardware required)")
    print("=" * 60)
    test_intent()
    test_no_false_triggers()
    test_steps()
    test_state_machine()
    test_earcons()
    print("=" * 60)
    if FAILS:
        print(f" {len(FAILS)} FAILED: {', '.join(FAILS)}")
        return 1
    print(" all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
