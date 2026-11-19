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
    check("stop command leads with Stop",
          any(s.startswith("Stop!") for s in said),
          str([s for s in said if s.startswith("Stop")]))
    check("stop explains why, not just 'Stop.'",
          any(s.startswith("Stop!") and len(s) > 25 for s in said),
          str([s for s in said if s.startswith("Stop")]))
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
          estimate_distance("unicorn", 300, 640) is None)


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
    """A genuine hazard is restated; a mere advisory is not.

    Repeating an advisory every few seconds is what made the cane feel like it
    would not shut up, so only URGENT and STOP are restated now.
    """
    print("persistent hazard reminder")
    import smartcane.config as cfg

    hazard = Guidance(step_len=0.65)
    t = 7000.0
    count = 0
    for _ in range(25):                      # 25 s of an unchanged URGENT hazard
        t += 1.0
        if hazard.announce(hazard.assess(FakeSensor(0.5), None), now=t):
            count += 1
    check("urgent hazard restated over 25 s", count >= 2,
          f"{count} announcements")
    check("not chattering every second", count <= 8, f"{count} announcements")
    expected = int(25 / cfg.REPEAT_AFTER_SEC) + 1
    check("roughly one per REPEAT_AFTER_SEC", abs(count - expected) <= 1,
          f"{count} vs ~{expected}")

    advisory = Guidance(step_len=0.65)
    t = 9000.0
    repeated = 0
    for _ in range(25):                      # 25 s of an unchanged ADVISORY
        t += 1.0
        if advisory.announce(advisory.assess(FakeSensor(1.2), None), now=t):
            repeated += 1
    check("an advisory is said once, not repeated", repeated == 1,
          f"{repeated} announcements")


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

        def corridor(self, hazard_only=False):
            return []

        def nearest(self, zone=None, hazard_only=False):
            return None

        def described(self, limit=3):
            return []

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
          near.startswith("I "), near)

    steps = g.steps_to_walk(FakeSensor(2.0), empty)
    check("steps answer is a full sentence",
          "step" in steps.lower() and steps.endswith("."), steps)
    check("steps uses words not digits", " 2 " not in steps, steps)

    blocked = g.steps_to_walk(FakeSensor(0.6), empty)
    check("too-close answer says stop", "stop" in blocked.lower(), blocked)

    for line in (clear, near, steps, blocked):
        print(f"    \"{line}\"")


def test_safety_answer() -> None:
    """'Is it safe?' must never say 'clear' while something is in the corridor.

    Regression from the Pi run: the camera plainly showed two people at ~3 m
    and the cane answered "Path is clear. You can walk." because the old check
    only looked for anything closer than 0.8 m.
    """
    print("safety answer")
    g = Guidance(step_len=0.65)

    class EmptyScene:
        objects: list = []
        frame_width = 640
        frame_height = 480
        infer_ms = 0.0
        backend = "test"

        def corridor(self, hazard_only=False):
            return []

        def nearest(self, zone=None, hazard_only=False):
            return None

        def described(self, limit=3):
            return []

    empty = EmptyScene()

    # nothing there -> clear
    text, earcon = g.safety_answer(FakeSensor(None), empty)
    check("empty path says clear", "clear" in text.lower(), text)
    check("clear uses the ok earcon", earcon == "ok", earcon)

    # something visible but far away -> must NOT claim clear
    text, earcon = g.safety_answer(FakeSensor(1.4), empty)
    check("object at 1.4 m is not called clear",
          "path is clear" not in text.lower(), text)
    check("object at 1.4 m is a caution", "caution" in text.lower(), text)
    check("caution uses the advisory earcon", earcon == "advisory", earcon)

    # something very close -> not safe
    text, earcon = g.safety_answer(FakeSensor(0.5), empty)
    check("object at 0.5 m says not safe", "not safe" in text.lower(), text)
    check("danger uses the urgent earcon", earcon == "urgent", earcon)

    for line in (g.safety_answer(FakeSensor(None), empty)[0],
                 g.safety_answer(FakeSensor(1.4), empty)[0],
                 g.safety_answer(FakeSensor(0.5), empty)[0]):
        print(f"    \"{line}\"")


def _scene_with(*specs):
    """Build a Scene from (label, zone, dist_m, conf) tuples."""
    import time
    from smartcane.vision import Scene, TrackedObject

    now = time.monotonic()
    scene = Scene(at=now)
    for index, (label, zone, dist, conf) in enumerate(specs):
        scene.objects.append(TrackedObject(
            tid=index + 1, label=label, x=320, y=240, box_h=100, box_w=60,
            zone=zone, hits=3, last_seen=now, dist_m=dist, best_conf=conf))
    return scene


def test_multi_object_and_turns() -> None:
    """Name every object, and turn towards the side that has room."""
    print("multi-object description and turns")
    g = Guidance(step_len=0.65)

    # person in front, chair beside it
    scene = _scene_with(("person", "center", 1.5, 0.9),
                        ("chair", "left", 2.0, 0.8))
    text = g.describe(FakeSensor(1.5), scene)
    check("names the person", "person" in text.lower(), text)
    check("also names the chair", "chair" in text.lower(), text)
    check("mentions a side for the chair", "left" in text.lower(), text)
    print(f"    \"{text}\"")

    # a cup is nameable but must not be treated as a walking hazard
    cup_scene = _scene_with(("cup", "center", 0.5, 0.9))
    check("cup is not a hazard",
          len(cup_scene.corridor(hazard_only=True)) == 0,
          str(len(cup_scene.corridor(hazard_only=True))))
    check("cup is still describable", "cup" in g.describe(
        FakeSensor(None), cup_scene).lower())

    # blocked ahead but not yet dangerous (1.0 m = ADVISORY, 0 steps), and the
    # right side is tighter than the left -> tell the user to turn left
    blocked = _scene_with(("person", "center", 1.0, 0.9),
                          ("chair", "right", 0.6, 0.8))
    answer = g.steps_to_walk(FakeSensor(1.0), blocked)
    check("blocked path suggests a turn", "turn" in answer.lower(), answer)
    check("turns towards the clear side", "left" in answer.lower(), answer)
    check("gives a step count after the turn",
          "step" in answer.lower(), answer)
    print(f"    \"{answer}\"")

    # something already very close must say stop, never "walk"
    danger = _scene_with(("person", "center", 0.5, 0.9))
    stop_answer = g.steps_to_walk(FakeSensor(0.5), danger)
    check("very close says stop", "stop" in stop_answer.lower(), stop_answer)
    check("very close does not tell you to walk",
          "walk" not in stop_answer.lower(), stop_answer)
    print(f"    \"{stop_answer}\"")

    # clear ahead -> straight steps
    clear = g.steps_to_walk(FakeSensor(None), _scene_with())
    check("clear path gives steps", "step" in clear.lower(), clear)
    print(f"    \"{clear}\"")


def _scene_with(*specs):
    """Build a Scene from (label, zone, dist_m, conf) tuples."""
    import time
    from smartcane.vision import Scene, TrackedObject

    now = time.monotonic()
    scene = Scene(at=now)
    for index, (label, zone, dist, conf) in enumerate(specs):
        scene.objects.append(TrackedObject(
            tid=index + 1, label=label, x=320.0 if zone == "center" else
            (100.0 if zone == "left" else 540.0), y=240, box_h=100, box_w=60,
            zone=zone, hits=5, last_seen=now, dist_m=dist, best_conf=conf,
            label_stable=True, label_votes={label: 5}))
    return scene


def test_quiet_by_default() -> None:
    """The cane must NOT chatter. Only close hazards, or a direct question.

    This is the complaint that matters most in practice: continuous alerts make
    the device get switched off. Default mode is "critical".
    """
    print("quiet by default")
    import smartcane.config as cfg

    old_mode = cfg.UNSOLICITED_ALERTS
    cfg.UNSOLICITED_ALERTS = "critical"
    try:
        _run_quiet_checks(cfg)
    finally:
        cfg.UNSOLICITED_ALERTS = old_mode


def _run_quiet_checks(cfg) -> None:
    g = Guidance(step_len=0.65)
    far = _scene_with(("chair", "center", 1.5, 0.9))
    sit = g.assess(FakeSensor(1.5), far)
    ann = g.announce(sit, now=100.0, scene=far)
    check("1.5 m ahead stays silent", ann is None,
          ann.text if ann else "silent")

    far2 = _scene_with(("person", "center", 2.0, 0.9))
    sit2 = g.assess(FakeSensor(2.0), far2)
    ann2 = g.announce(sit2, now=150.0, scene=far2)
    check("2.0 m ahead stays silent", ann2 is None,
          ann2.text if ann2 else "silent")

    close = _scene_with(("chair", "center", 0.9, 0.9))
    sit3 = g.assess(FakeSensor(0.9), close)
    ann3 = g.announce(sit3, now=300.0, scene=close)
    check("0.9 m DOES alert", ann3 is not None,
          ann3.text if ann3 else "silent")

    # a direct question is always answered, regardless of mode
    answer, _earcon = g.safety_answer(FakeSensor(1.5), far)
    check("direct questions always answered", bool(answer), answer)


def test_label_stability() -> None:
    """A name must be earned before it is spoken.

    On the Pi a seated person was announced as a "microwave". A segmentation
    model flickers between classes on the same object, and naming the first
    frame it emits turns noise into confident lies.
    """
    print("label stability (anti-hallucination)")
    from smartcane.vision import TrackedObject, _stable_label

    label, stable = _stable_label({"person": 3, "microwave": 3})
    check("a 50/50 flicker is not stable", not stable, f"{label}")

    label2, stable2 = _stable_label({"person": 5, "microwave": 1})
    check("a clear majority is stable", stable2 and label2 == "person", label2)

    _l3, stable3 = _stable_label({"person": 1})
    check("one vote is not enough", not stable3, str(stable3))

    def obj_for(name):
        return TrackedObject(
            tid=1, label=name, x=320, y=240, box_h=100, box_w=60,
            zone="center", hits=5, last_seen=0.0, dist_m=1.0,
            label_stable=True, label_votes={name: 5})

    check("chair is named", obj_for("chair").spoken_label == "chair",
          obj_for("chair").spoken_label)
    check("escalator is off-profile indoors -> obstacle",
          obj_for("escalator").spoken_label == "obstacle",
          obj_for("escalator").spoken_label)
    check("boat is off-profile indoors -> obstacle",
          obj_for("boat").spoken_label == "obstacle",
          obj_for("boat").spoken_label)

    unstable = obj_for("chair")
    unstable.label_stable = False
    check("an unstable label becomes obstacle",
          unstable.spoken_label == "obstacle", unstable.spoken_label)


def test_serial_trust() -> None:
    """A noisy link must be ignored, not believed.

    From a real Pi session: the Arduino's text was perfectly readable but the
    number field was randomly corrupted, so "150.4 cm" arrived as "19.4 cm".
    That is inside the valid range, so it sailed past the range check and
    produced "Stop! obstacle at 19 centimetres" as a false alert.
    """
    print("serial trust (corrupt link)")
    from smartcane.link import SerialLink, _looks_like_our_text

    good = b"Distance: 150.4 cm  | PATH CLEAR\r\n"
    corrupt = [
        b"Distance: 1S.0 cm  | OBSTACLE NEARBY\r\n",
        b"Distance: 1T.5 cm  | OBSTACLE NEARBY\r\n",
        b"Distance: 1U.3 cm  | OBSTACLE NEARBY\r\n",
        b"Distance: 1M.4 cm  | OBSTACLE NEARBY\r\n",
    ]

    noisy = SerialLink(mock=False)
    for i in range(60):
        noisy.feed(corrupt[i % 4])
    st = noisy.state()
    check("unreadable link is not trusted", not st.reliable, str(st.reliable))
    check("and reports no distance", st.dist_cm is None, str(st.dist_cm))
    check("so the sensor is treated as invalid", not st.valid, str(st.valid))

    mixed = SerialLink(mock=False)
    for i in range(40):
        mixed.feed(good)
        mixed.feed(corrupt[i % 4])
    sm = mixed.state()
    check("a corrupt reading is rejected against the median",
          sm.dist_cm == 150.4, str(sm.dist_cm))
    check("a half-clean link is still usable", sm.valid, str(sm.valid))

    change = SerialLink(mock=False)
    for _ in range(10):
        change.feed(good)
    check("clean link is trusted", change.state().valid)
    change.feed(b"Distance: 20.0 cm  | OBSTACLE NEARBY\r\n")
    check("a single wild reading is held back",
          change.state().dist_cm == 150.4, str(change.state().dist_cm))
    change.feed(b"Distance: 20.0 cm  | OBSTACLE NEARBY\r\n")
    check("a confirmed change is accepted",
          abs(change.state().dist_cm - 20.0) < 1.0, str(change.state().dist_cm))

    check("corrupt-but-readable text still proves the baud",
          _looks_like_our_text(corrupt[0]))
    check("binary frames are not mistaken for text",
          not _looks_like_our_text(bytes([0xAA, 0x55, 1, 4, 7, 0x2C, 1, 0])))


def test_slow_segmentation_self_disables() -> None:
    """A model too slow to be useful must disable itself and say so.

    Measured on the Pi: SegFormer-B1 at 512x512 took 3517 ms per frame, i.e.
    0.28 fps. A blind user gets no feedback for three seconds at a time, which
    is worse than having no segmentation at all.
    """
    print("slow segmentation self-disables")
    import time as _time

    import numpy as np
    import smartcane.config as cfg
    from smartcane.vision import Vision

    class FakeCam:
        def latest(self):
            return None

    class SlowSeg:
        backend = "fake"
        session = None
        model = None

        def infer(self, image):
            _time.sleep(0.02)
            return None

    old_max, old_warm = cfg.SEG_MAX_MS, cfg.SEG_WARMUP_FRAMES
    try:
        cfg.SEG_MAX_MS = 0.5          # force the trigger with a 20 ms model
        cfg.SEG_WARMUP_FRAMES = 1
        vision = Vision(FakeCam(), mock=False)
        vision.enabled = True
        vision.backend = "segmentation"
        vision.seg = SlowSeg()
        frame = np.zeros((120, 160, 3), np.uint8)
        for _ in range(8):
            vision.process(frame)
        check("segmentation switched off when too slow",
              vision.backend != "segmentation", vision.backend)
    finally:
        cfg.SEG_MAX_MS, cfg.SEG_WARMUP_FRAMES = old_max, old_warm


def test_naming_at_slow_frame_rate() -> None:
    """A track must survive a slow detector, or nothing is ever named.

    Real failure on the Pi: segmentation took 0.8-3.5 s per frame while
    TRACK_MAX_AGE was 1.0 s, so every track expired before the next frame
    arrived. Each frame created a brand new track with a single label vote, the
    vote never reached the threshold, and every object - cabinet, chair,
    whatever - was announced as "obstacle" forever.
    """
    print("naming survives a slow frame rate")
    from smartcane.vision import Detection, Vision

    class FakeCam:
        def latest(self):
            return None

    vision = Vision(FakeCam(), mock=False)
    vision.enabled = True
    box = Detection("chair", 300.0, 200.0, 380.0, 400.0, 0.9)

    # one detection per second - a realistic 1 fps segmentation loop
    start = 100.0
    for index in range(3):
        vision._update_tracks([box], start + index * 1.0, 640)

    check("one track, not one per frame", len(vision._tracks) == 1,
          f"{len(vision._tracks)} tracks")
    track = list(vision._tracks.values())[0]
    check("label became stable at 1 fps", track.label_stable,
          f"{track.label} stable={track.label_stable}")
    check("the object is named, not 'obstacle'",
          track.spoken_label == "chair", track.spoken_label)


def test_stop_gives_an_exit() -> None:
    """A stop with no exit is only half an instruction."""
    print("stop tells you which way to move")
    from smartcane.segmentation import free_space_from_mask, synthetic_mask

    def scene_blocked(where):
        scene = _scene_with(("chair", "center", 0.6, 0.9))
        scene.free_space = free_space_from_mask(synthetic_mask(blocked=where))
        return scene

    open_left = scene_blocked(None)
    g1 = Guidance(step_len=0.65)
    text = g1._stop_text(g1.assess(FakeSensor(0.6), open_left), open_left)
    check("says which way to step", "step to your left" in text.lower(), text)

    blocked_left = scene_blocked("left")
    g2 = Guidance(step_len=0.65)
    text2 = g2._stop_text(g2.assess(FakeSensor(0.6), blocked_left),
                          blocked_left)
    check("turns the other way when left is blocked",
          "step to your right" in text2.lower(), text2)

    both = scene_blocked("all")
    g3 = Guidance(step_len=0.65)
    text3 = g3._stop_text(g3.assess(FakeSensor(0.6), both), both)
    check("refuses to invent an exit when none exists",
          "both sides are blocked" in text3.lower(), text3)
    check("still leads with Stop", text3.startswith("Stop!"), text3)


def main() -> int:
    print("=" * 60)
    print(" Sahayak Drishti - smoke tests (no hardware required)")
    print("=" * 60)
    import smartcane.config as cfg

    # The chatty behaviours are opt-in now, so those tests ask for them.
    original_mode = cfg.UNSOLICITED_ALERTS
    cfg.UNSOLICITED_ALERTS = "all"
    test_intent()
    test_no_false_triggers()
    test_steps()
    test_state_machine()
    test_cooldown_isolation()
    test_persistent_hazard_repeats()
    test_phrasing()
    test_quiet_by_default()
    test_label_stability()
    test_query_responses()
    test_safety_answer()
    test_multi_object_and_turns()
    test_distance_scaling()
    test_resample()
    test_earcons()
    test_serial_parsers()
    test_serial_trust()
    test_slow_segmentation_self_disables()
    test_naming_at_slow_frame_rate()
    test_stop_gives_an_exit()
    print("=" * 60)
    if FAILS:
        print(f" {len(FAILS)} FAILED: {', '.join(FAILS)}")
        return 1
    print(" all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
