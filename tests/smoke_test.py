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


def test_serial_parsers() -> None:
    """The Pi must read whatever the Arduino happens to be sending.

    The real Grove sketch prints a banner first and then text lines, so format
    detection has to survive the banner. These cases come from actual output
    captured off the board.
    """
    print("serial parsers")
    from smartcane.link import SerialLink

    def crc8(b: bytes) -> int:
        c = 0
        for x in b:
            c ^= x
            for _ in range(8):
                c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
        return c

    # 1. the friend's text sketch: banner then "Distance: 150.0 cm | PATH CLEAR"
    link = SerialLink(mock=False)
    link.feed(b"================================\r\n")
    link.feed(b" Grove Ultrasonic Ranger V2.0\r\n")
    link.feed(b"Distance: 150.0 cm  | PATH CLEAR\r\n")
    check("text banner detected as kv", link._format == "kv", str(link._format))
    check("Distance: 150.0 parsed", link.state().dist_cm == 150.0,
          str(link.state().dist_cm))

    # 2. corrupted digit must NOT become a 1 cm obstacle
    link_bad = SerialLink(mock=False)
    link_bad.feed(b"Distance: 150.0 cm  | PATH CLEAR\r\n")
    good = link_bad.state().dist_cm
    link_bad.feed(b"Distance: 1s.7 cm  | PATH CLEAR\r\n")
    check("corrupt line discarded, keeps last good",
          link_bad.state().dist_cm == good, f"was {good}, now "
          f"{link_bad.state().dist_cm}")

    link_corrupt = SerialLink(mock=False)
    link_corrupt.feed(b"Distance: 1s.7 cm  | PATH CLEAR\r\n")
    check("corrupt-only stream yields no distance",
          link_corrupt.state().dist_cm is None,
          str(link_corrupt.state().dist_cm))

    # 3. our binary protocol
    link2 = SerialLink(mock=False)
    body = bytes([0xAA, 0x55, 0x01, 0x04, 7, 0x2C, 0x01, 0x00])
    link2.feed(body + bytes([crc8(body)]))
    st = link2.state()
    check("binary frame detected", link2._format == "binary", str(link2._format))
    check("binary dist 300cm", st.dist_cm == 300.0, str(st.dist_cm))

    # 3. plain CSV
    link3 = SerialLink(mock=False)
    link3.feed(b"123,45\n")
    check("csv parsed", link3.state().dist_cm == 123.0, str(link3.state().dist_cm))

    # 4. JSON
    link4 = SerialLink(mock=False)
    link4.feed(b'{"d":88,"m":1}\n')
    check("json parsed", link4.state().dist_cm == 88.0, str(link4.state().dist_cm))


def test_phrasing() -> None:
    """What the cane actually says out loud.

    These strings are the product. They must be short, natural and never
    contradictory ("about 2 metres, walk 1 step" was a real bug).
    """
    print("spoken phrasing")
    g = Guidance(step_len=0.65)
    t = 1000.0
    said: list[str] = []
    for dist in (2.2, 1.5, 1.0, 0.7, 0.3):
        t += 5.0
        sit = g.assess(FakeSensor(dist), None)
        ann = g.announce(sit, now=t)
        if ann:
            said.append(ann.text)

    for line in said:
        print(f"    \"{line}\"")

    check("something was said", bool(said), f"{len(said)} lines")
    check("stop is short and blunt",
          any(s.strip() == "Stop." for s in said))
    check("no digits spelled as numerals in step counts",
          not any("straight 1 step" in s or "straight 2 step" in s for s in said))
    check("distance uses words not '1 metre'",
          not any("about 1 metre" in s for s in said))
    check("mentions a direction or action",
          any(("Step to your" in s) or ("Walk straight" in s) or
              ("Stop." in s) for s in said))

    # steps and distance must agree (regression: this was broken once)
    g2 = Guidance(step_len=0.65)
    sit = g2.assess(FakeSensor(1.5), None)
    ann = g2.announce(sit, now=2000.0)
    if ann and "Walk straight" in ann.text:
        check("1.5 m says one step", "straight one step" in ann.text, ann.text)


def test_cooldown_isolation() -> None:
    """A hazard right after 'Path clear' must still be announced.

    Regression: hazards and the reassurance shared one timestamp, so after
    saying "Path clear" a person stepping into the path was silently
    suppressed for the whole advisory cooldown.
    """
    print("cooldown isolation")
    g = Guidance(step_len=0.65)
    t = 5000.0
    events: list[tuple[float, str]] = []

    # obstacle -> long clear (triggers "Path clear") -> obstacle again
    for dist in (1.5, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 1.2):
        t += 1.0
        ann = g.announce(g.assess(FakeSensor(dist), None), now=t)
        if ann:
            events.append((dist, ann.text))

    said_clear = any("Path clear" in text for _, text in events)
    hazard_after = any(d < 2.0 and "Path clear" not in text
                       for d, text in events if d == 1.2)

    check("said 'Path clear' during the quiet stretch", said_clear,
          f"{len(events)} utterances")
    check("hazard after clear was still announced", hazard_after,
          str([text for d, text in events if d == 1.2]))


def test_distance_scaling() -> None:
    """Distance must not depend on the camera resolution.

    The phone webcam often streams at 1280 or 1920 wide while FOCAL_PX is
    calibrated for 640. Without scaling, every distance is wrong by that
    ratio -- a person 2 m away reads as 1 m at 1280 wide.
    """
    print("distance scaling")
    from smartcane.vision import estimate_distance

    a = estimate_distance("person", 300, 640)
    b = estimate_distance("person", 600, 1280)   # same scene, double resolution
    check("resolution independent", a is not None and b is not None
          and abs(a - b) < 0.05, f"{a} vs {b}")

    near = estimate_distance("person", 600, 640)
    far = estimate_distance("person", 300, 640)
    check("bigger box means closer", near is not None and far is not None
          and near < far, f"{near} < {far}")

    check("unknown class returns None",
          estimate_distance("toaster", 300, 640) is None)


def test_resample() -> None:
    """Vosk needs 16 kHz; many USB headsets only do 48 kHz.

    PortAudio refuses to open a rate the device does not support, so without
    this the microphone looks broken on perfectly good hardware.
    """
    print("resampling")
    import numpy as np
    from smartcane.util import resample

    x = np.full(4800, 0.5, dtype=np.float32)
    y = resample(x, 48000, 16000)
    check("48k -> 16k is a third of the length",
          abs(len(y) - 1600) <= 2, f"{len(x)} -> {len(y)}")
    check("amplitude preserved",
          abs(float(np.mean(np.abs(y))) - 0.5) < 0.05,
          f"{float(np.mean(np.abs(y))):.3f}")
    check("same rate is a no-op", len(resample(x, 16000, 16000)) == len(x))
    check("44.1k -> 16k works", len(resample(np.zeros(4410, np.float32),
                                             44100, 16000)) > 0)


def test_persistent_hazard_repeats() -> None:
    """A hazard that does not change must be restated.

    Regression: announcements fire on transitions, so a person standing in
    the path was announced once at the start and then never mentioned again.
    The user was warned once and then left to walk into them in silence.
    """
    print("persistent hazard reminder")
    import smartcane.config as cfg
    g = Guidance(step_len=0.65)
    t = 7000.0
    count = 0
    for _ in range(25):                      # 25 s of an unchanged obstacle
        t += 1.0
        ann = g.announce(g.assess(FakeSensor(1.2), None), now=t)
        if ann:
            count += 1
    check("obstacle restated over 25 s", count >= 2, f"{count} announcements")
    check("not chattering every second", count <= 8, f"{count} announcements")
    expected = int(25 / cfg.REPEAT_AFTER_SEC) + 1
    check("roughly one per REPEAT_AFTER_SEC", abs(count - expected) <= 1,
          f"{count} vs ~{expected}")


def test_query_responses() -> None:
    """What the cane says when asked a question.

    The product is a conversation: "what is in front of me" -> "I can see a
    person right in front of you, about a metre and a half away."
    """
    print("query responses")
    g = Guidance(step_len=0.65)

    class EmptyScene:
        objects: list = []
        frame_width = 640
        frame_height = 480
        infer_ms = 0.0
        backend = "test"

        def corridor(self):
            return []

        def nearest(self, zone=None):
            return None

    empty = EmptyScene()

    clear = g.describe(FakeSensor(None), empty)
    check("clear answer is a sentence", clear.endswith(".") and len(clear) > 20,
          clear)
    check("clear answer does not claim an object",
          "don't see" in clear or "nothing" in clear.lower(), clear)

    near = g.describe(FakeSensor(1.5), empty)
    check("near answer names a thing", "a " in near or "an " in near, near)
    check("near answer gives a distance", "metre" in near, near)
    check("sounds like speech, not a label",
          near.startswith("I can see"), near)

    steps = g.steps_to_walk(FakeSensor(2.0), empty)
    check("steps answer is a full sentence",
          steps.startswith("You can walk"), steps)
    check("steps uses words not digits", " 2 " not in steps, steps)

    blocked = g.steps_to_walk(FakeSensor(0.6), empty)
    check("too-close answer says stop", "stop" in blocked.lower(), blocked)

    for line in (clear, near, steps, blocked):
        print(f"    \"{line}\"")


def main() -> int:
    print("=" * 60)
    print(" Sahayak Drishti - smoke tests (no hardware required)")
    print("=" * 60)
    test_intent()
    test_no_false_triggers()
    test_steps()
    test_state_machine()
    test_cooldown_isolation()
    test_persistent_hazard_repeats()
    test_phrasing()
    test_query_responses()
    test_distance_scaling()
    test_resample()
    test_earcons()
    test_serial_parsers()
    print("=" * 60)
    if FAILS:
        print(f" {len(FAILS)} FAILED: {', '.join(FAILS)}")
        return 1
    print(" all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
