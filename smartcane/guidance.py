"""Decision layer: turns sensors + scene into a state and, only when it matters,
into words.

Two rules drive everything here:

1. **Announce on transitions, not on a timer.** The user asked for guidance
   "only when necessary". The same state repeated is silence; a state *change*
   is what earns an utterance.

2. **Never claim more path than we have verified.** A step count is capped by
   what the ultrasonic actually measured inside the walking corridor, minus a
   stopping margin. Saying "walk six steps" from a 4 m sensor reading is how an
   assistive device walks someone into a chair.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum

from . import config
from .risk import RiskLevel, RiskReport, assess_scene
from .util import clamp, get_logger

log = get_logger("guidance")


class State(str):
    CLEAR = "clear"
    WATCH = "watch"
    ADVISORY = "advisory"
    URGENT = "urgent"
    STOP = "stop"


class Priority(IntEnum):
    REFLEX = 0     # earcon, preempts everything
    URGENT = 1     # immediate warning
    ANSWER = 2     # reply to a question
    ADVISORY = 3   # proactive guidance
    INFO = 4       # path clear, status


@dataclass
class Announcement:
    text: str
    priority: Priority
    earcon: str | None = None
    key: str = ""


@dataclass
class Situation:
    state: str = State.CLEAR
    label: str = ""
    dist_m: float | None = None
    zone: str = "center"
    steps: int = 0
    movement: str = "stationary"
    blocked: bool = False
    sensor_ok: bool = True
    source: str = "vision"
    # Filled in by the risk engine. `risk` is the graded judgement; `state` is
    # the legacy announcement bucket derived from it.
    risk: RiskLevel = RiskLevel.NONE
    reason: str = ""
    ttc: float | None = None
    closing_speed: float | None = None
    uncertain: bool = False
    report: RiskReport | None = None


def step_length_from_gait(a_max: float, a_min: float,
                          k: float = config.STEP_K) -> float:
    """SL = K * (a_max - a_min) ** 0.25  (Weinberg). Clamped to human range."""
    diff = max(0.01, a_max - a_min)
    return clamp(k * (diff ** 0.25), config.STEP_MIN, config.STEP_MAX)


def steps_available(dist_m: float | None, step_len: float) -> int:
    """How many safe steps we can honestly promise."""
    if dist_m is None or step_len <= 0:
        return 0
    usable = min(dist_m, config.SENSOR_HORIZON) - config.STOP_MARGIN
    if usable <= 0:
        return 0
    return int(clamp(int(usable / step_len), 0,
                     config.MAX_STEPS_TO_ANNOUNCE))


def _round_half(dist_m: float) -> float:
    """Round to the nearest half metre.

    Speech and step count are both derived from this value so the two can never
    contradict each other. Saying "about 2 metres, walk 1 step" is the kind of
    inconsistency that makes a blind user distrust the device.
    """
    return max(0.5, round(dist_m * 2.0) / 2.0)


class Guidance:
    def __init__(self, step_len: float = config.STEP_M) -> None:
        self.step_len = step_len
        self._state = State.CLEAR
        self._last_key = ""
        # Hazards and the "path clear" reassurance are timed separately. Sharing
        # one timer meant that right after saying "Path clear", a person
        # stepping out in front of the user was silently suppressed for the
        # whole advisory cooldown.
        self._last_hazard_at = 0.0
        self._last_clear_at = 0.0
        self._clear_since: float | None = None
        self._clear_announced = False

    def _escape_hint(self, scene) -> str:
        """Which way is out of a stop.

        A stop with no exit is only half an instruction: the user is told not
        to move but not where they may move to. The direction is only spoken
        when it was measured - never guessed.
        """
        if scene is None:
            return ""
        direction = self.best_direction(scene)
        if direction is not None:
            return f" Step to your {direction}."
        free = getattr(scene, "free_space", None)
        if free is not None and getattr(free, "valid", False):
            return " Both sides are blocked. Stay where you are."
        return ""

    def _stop_text(self, sit: Situation, scene=None) -> str:
        """Explain a STOP. Never just shout 'Stop!' at someone.

        The user has to know what they must not walk into, how far it is, where
        it is, and why it is dangerous - all in one short breath.
        """
        unnamed = sit.uncertain or sit.label in ("", "obstacle")
        if unnamed:
            thing = "An unidentified obstacle"
        else:
            thing = _with_article(sit.label).capitalize()

        where = ("directly in front of you" if sit.zone == "center"
                 else f"on your {sit.zone}")

        if sit.dist_m is None:
            distance = ""
        elif sit.dist_m < 1.0:
            distance = f" at approximately {int(round(sit.dist_m * 100))} centimetres"
        else:
            distance = (" at approximately "
                        + _approx_distance(_round_half(sit.dist_m))
                        .replace("about ", ""))

        if sit.ttc is not None and sit.ttc <= config.TTC_CRITICAL_SEC:
            why = " Collision risk."
        elif sit.state == State.STOP:
            why = " Do not move forward."
        else:
            why = " Do not move forward."

        return f"Stop! {thing} is {where}{distance}.{why}" + self._escape_hint(scene)

    # -- assessment --------------------------------------------------------
    def assess(self, sensor, scene) -> Situation:
        """Grade the scene with the risk engine, then bucket it for speech.

        Distance alone is no longer what decides danger: the risk engine also
        weighs whether the object is in the walking corridor, whether it is
        closing, and how long until contact.
        """
        sensor_ok = sensor is not None and sensor.valid
        sensor_m = sensor.dist_m if sensor_ok else None

        report = assess_scene(scene, sensor_m)
        sit = Situation(sensor_ok=sensor_ok, risk=report.level, report=report)

        primary = report.primary
        if primary is not None:
            sit.label = primary.label
            sit.dist_m = primary.dist_m
            sit.zone = primary.zone
            sit.source = primary.source
            sit.reason = primary.reason
            sit.ttc = primary.ttc
            sit.closing_speed = primary.closing_speed
            sit.uncertain = primary.uncertain

        # Carry the tracked object's motion so the phrase can mention it.
        if scene is not None and primary is not None:
            match = scene.nearest(primary.zone)
            if match is not None and match.label == primary.label:
                sit.movement = match.movement

        # Graded risk -> legacy announcement bucket.
        if report.level == RiskLevel.CRITICAL:
            sit.state = (State.STOP
                         if (sit.dist_m is not None
                             and sit.dist_m <= config.STOP_METERS)
                         else State.URGENT)
        elif report.level == RiskLevel.MEDIUM:
            sit.state = State.ADVISORY
        elif report.level == RiskLevel.LOW:
            # Visible but not threatening: watch it silently unless it is near.
            sit.state = (State.WATCH
                         if (sit.dist_m is not None
                             and sit.dist_m <= config.WATCH_METERS)
                         else State.CLEAR)
        else:
            sit.state = State.CLEAR

        sit.state = self._damped(sit.state, sit.dist_m)

        sit.blocked = sit.state in (State.URGENT, State.STOP)
        sit.steps = steps_available(sit.dist_m, self.step_len)
        return sit

    _SEVERITY = {State.CLEAR: 0, State.WATCH: 1, State.ADVISORY: 2,
                 State.URGENT: 3, State.STOP: 4}

    def _damped(self, new_state: str, dist_m: float | None) -> str:
        """Stop the state flapping across a threshold.

        Escalation is applied immediately: if something suddenly becomes
        dangerous the user must hear about it now. Relaxation waits until the
        reading has clearly improved, because a sensor hovering at a boundary
        otherwise announces the same thing over and over.
        """
        previous = self._state
        new_rank = self._SEVERITY.get(new_state)
        old_rank = self._SEVERITY.get(previous)
        if new_rank is None or old_rank is None or new_rank >= old_rank:
            return new_state                      # escalating or unchanged
        if dist_m is None:
            return new_state                      # no distance: nothing to damp

        band = {State.STOP: config.STOP_METERS,
                State.URGENT: config.URGENT_METERS,
                State.ADVISORY: config.ADVISORY_METERS}.get(previous)
        if band is None:
            return new_state
        if dist_m < band + config.STATE_HYSTERESIS_M:
            return previous                       # not clear enough yet
        return new_state

    # -- announcement ------------------------------------------------------
    def _may_speak(self, sit: Situation) -> bool:
        """Is this situation worth interrupting the user for?

        Continuous alerts are how an assistive device gets switched off. In
        the default "critical" mode the cane is silent unless something is
        genuinely a stop-level hazard, or the user asked a question. Everything
        else waits to be asked.
        """
        mode = config.UNSOLICITED_ALERTS
        if mode == "all":
            return True
        if mode == "medium":
            return sit.state in (State.ADVISORY, State.URGENT, State.STOP)
        # critical: a stop-level hazard, OR anything physically this close.
        # The distance test matters because a 0.9 m obstacle can still grade as
        # ADVISORY, and staying silent at arm's length would be wrong.
        if sit.state in (State.URGENT, State.STOP):
            return True
        return (sit.dist_m is not None
                and sit.dist_m <= config.ALERT_DISTANCE_M)

    def announce(self, sit: Situation, now: float | None = None,
                 scene=None) -> Announcement | None:
        """Return words only when the situation has meaningfully changed."""
        now = now if now is not None else time.monotonic()
        may_speak = self._may_speak(sit)

        if sit.state in (State.CLEAR, State.WATCH):
            if self._state in (State.ADVISORY, State.URGENT, State.STOP):
                self._clear_since = now
                self._clear_announced = False
            self._state = sit.state
            if not may_speak:
                return None
            # Reassure once, and only after a genuinely quiet period, so a
            # hazard that just cleared is not immediately overwritten.
            if (self._clear_since is not None and not self._clear_announced
                    and now - self._clear_since >= config.SPEAK_CLEAR_AFTER_SEC
                    and now - self._last_hazard_at >= config.SPEAK_CLEAR_AFTER_SEC):
                self._clear_announced = True
                self._last_clear_at = now
                return Announcement("Path clear. You can walk.",
                                    Priority.INFO, key="clear")
            return None

        key = f"{sit.state}:{sit.label}:{sit.zone}:{sit.steps}"
        changed = (sit.state != self._state) or (key != self._last_key)

        # A hazard that does not change must still be restated now and then.
        # Announcements fire on transitions, so without this a person standing
        # in the path was announced once and then never mentioned again --
        # the user was told once and left to walk into them in silence.
        # Only genuine hazards get restated. Repeating an advisory every 8 s is
        # what made the cane feel like it would not shut up.
        if (not changed
                and sit.state in (State.URGENT, State.STOP)
                and (now - self._last_hazard_at) >= config.REPEAT_AFTER_SEC):
            changed = True

        # SAFETY: a cooldown must never silence an urgent warning. Only
        # ADVISORY chatter is rate-limited; URGENT and STOP may interrupt,
        # with a much shorter guard so they cannot machine-gun the speaker.
        if sit.state in (State.STOP, State.URGENT):
            cooled = (now - self._last_hazard_at) >= config.URGENT_MIN_GAP_SEC
        else:
            cooled = (now - self._last_hazard_at) >= config.ANNOUNCE_COOLDOWN_SEC

        if not may_speak or not changed or not cooled:
            self._state = sit.state
            self._last_key = key
            return None

        self._state = sit.state
        self._last_key = key
        self._last_hazard_at = now
        self._clear_since = None

        return self._phrase(sit, scene)

    def _phrase(self, sit: Situation, scene=None) -> Announcement:
        label = _nice(sit.label)
        # One rounded value drives BOTH the spoken distance and the step count,
        # so they can never contradict each other.
        dist = _round_half(sit.dist_m or 0.0)
        approx = _approx_distance(dist)
        steps = steps_available(dist, self.step_len)

        if sit.state == State.STOP:
            return Announcement(self._stop_text(sit, scene), Priority.REFLEX,
                                earcon="stop", key="stop")

        if sit.state == State.URGENT:
            return Announcement(self._stop_text(sit, scene), Priority.URGENT,
                                earcon="urgent", key="urgent")

        # ADVISORY: a step count when there is room to walk, otherwise a steer
        # towards whichever side actually has more room.
        if sit.zone == "center":
            if steps >= 1:
                text = (f"{label} ahead, {approx}. "
                        f"Walk straight {_num(steps)} "
                        f"{'step' if steps == 1 else 'steps'}.")
            else:
                side = self.best_direction(scene) or "right"
                text = f"{label} ahead, {approx}. Turn {side}."
        else:
            steer = "right" if sit.zone == "left" else "left"
            text = (f"{label} on your {sit.zone}, {approx}. "
                    f"Step to your {steer}.")

        if sit.movement == "toward":
            text += " It's coming toward you."
        elif sit.movement in ("left_to_right", "right_to_left"):
            text += " It's crossing in front of you."

        return Announcement(text, Priority.ADVISORY, key="advisory")

    # -- helpers for query intents ----------------------------------------
    def describe(self, sensor, scene) -> str:
        """Answer 'what is in front of me?' by naming everything visible.

        Previously this reported only the single nearest object in the walking
        corridor, so a chair beside a person was never mentioned.
        """
        objects = scene.described(3) if scene is not None else []

        if objects:
            phrases = []
            for obj in objects:
                where = ("right in front of you" if obj.zone == "center"
                         else f"on your {obj.zone}")
                if obj.dist_m is not None:
                    phrases.append(
                        f"{_with_article(obj.label)} {where}, "
                        f"{_approx_distance(_round_half(obj.dist_m))} away")
                else:
                    phrases.append(f"{_with_article(obj.label)} {where}")
            if len(phrases) == 1:
                text = f"I can see {phrases[0]}."
            else:
                text = f"I can see {', '.join(phrases[:-1])}, and {phrases[-1]}."
            if objects[0].movement == "toward":
                text += " The nearest one is coming toward you."
            return text

        sit = self.assess(sensor, scene)
        if sit.dist_m is not None:
            approx = _approx_distance(_round_half(sit.dist_m))
            if approx == "very close":
                return ("I don't see it clearly, but something is very close "
                        "in front of you.")
            return (f"I don't see anything clearly, but something is "
                    f"{approx} away.")
        return ("I don't see anything close in front of you. "
                "The path looks clear.")

    def best_direction(self, scene) -> str | None:
        """Which side has more room?

        Prefers *measured* free space from the segmentation mask over the
        old heuristic of "nothing was detected there, so probably fine".
        """
        if scene is None:
            return None
        free = getattr(scene, "free_space", None)
        if free is not None and getattr(free, "valid", False):
            # A measured answer is final: if neither side is walkable, say so
            # rather than falling back to guesswork.
            return free.best_side

        left = scene.nearest("left", hazard_only=True)
        right = scene.nearest("right", hazard_only=True)
        left_m = left.dist_m if (left and left.dist_m is not None) else 99.0
        right_m = right.dist_m if (right and right.dist_m is not None) else 99.0
        if left_m < 1.0 and right_m < 1.0:
            return None                       # both sides are tight
        return "left" if left_m >= right_m else "right"

    def clearance(self, scene, zone: str) -> float | None:
        """Nearest hazard on one side, or None when nothing was detected.

        None means "nothing detected", NOT "guaranteed clear". Callers must
        phrase it as "appears clear", never as a promise.
        """
        if scene is None:
            return None
        obj = scene.nearest(zone, hazard_only=True)
        if obj is None or obj.dist_m is None:
            return None
        return obj.dist_m

    def reach_object(self, obj, scene) -> str:
        """Steps to reach a specific, already-identified object."""
        if obj is None:
            return ("I am not sure which object you mean. Ask me what is in "
                    "front of you first, then ask how to reach it.")
        if obj.dist_m is None:
            return ("I can see it but I cannot estimate the distance. "
                    "Please move a little closer and ask again.")
        steps = int(round(obj.dist_m / self.step_len))
        steps = max(1, min(steps, config.MAX_STEPS_TO_REACH))
        if obj.zone == "center":
            return (f"Walk approximately {_num(steps)} steps forward. "
                    f"It is directly ahead.")
        return (f"Turn slightly {obj.zone} and walk approximately "
                f"{_num(steps)} steps.")

    def bypass(self, sensor, scene) -> str:
        """How to get around whatever is blocking the path."""
        sit = self.assess(sensor, scene)
        if sit.state in (State.STOP, State.URGENT):
            return "Stop first. Something is too close to step around safely."
        if sit.state == State.CLEAR:
            return "Nothing is blocking your path. Continue walking forward."

        direction = self.best_direction(scene)
        if direction is None:
            return ("Both sides look tight. Please stop and wait, or ask "
                    "someone nearby for help.")

        side_m = self.clearance(scene, direction)
        steps = (steps_available(_round_half(side_m), self.step_len)
                 if side_m is not None else 2)
        steps = max(1, min(steps, config.MAX_STEPS_TO_ANNOUNCE))
        unnamed = sit.uncertain or sit.label in ("", "obstacle")
        thing = ("an unidentified obstacle" if unnamed
                 else _with_article(sit.label))
        return (f"{thing.capitalize()} is blocking your path. Turn slightly "
                f"{direction} and walk {_num(steps)} steps to go around it.")

    def describe_all(self, sensor, scene) -> str:
        """'What objects are around me?' â€” all three zones, not just ahead."""
        if scene is None or not scene.objects:
            sit = self.assess(sensor, scene)
            if sit.dist_m is None:
                return "I do not see any objects around you."
            return (f"I do not recognise any objects, but something is "
                    f"{_approx_distance(_round_half(sit.dist_m))} ahead.")
        parts = []
        for zone, where in (("center", "ahead"),
                            ("left", "on your left"),
                            ("right", "on your right")):
            obj = scene.nearest(zone, hazard_only=False)
            if obj is None:
                continue
            if obj.dist_m is not None:
                parts.append(f"{_with_article(obj.label)} {where}, "
                             f"{_approx_distance(_round_half(obj.dist_m))} away")
            else:
                parts.append(f"{_with_article(obj.label)} {where}")
        if not parts:
            return "I do not see any objects around you."
        return "I can see " + "; ".join(parts) + "."

    def safety_answer(self, sensor, scene) -> tuple[str, str]:
        """Answer 'is it safe?' honestly. Returns (text, earcon).

        The old version only checked whether something was within 0.8 m, so a
        person plainly visible on camera at 3 m got "the path is clear" --
        which is exactly the false all-clear that makes the cane untrustworthy.
        """
        sit = self.assess(sensor, scene)
        if sit.blocked:
            return f"Not safe. {self.describe(sensor, scene)}", "urgent"
        if sit.dist_m is not None and sit.state == State.ADVISORY:
            return (f"Caution. {self.describe(sensor, scene)} "
                    f"You can still walk, but keep to the side."), "advisory"
        return "The path is clear ahead. You can walk.", "ok"

    def steps_to_walk(self, sensor, scene) -> str:
        """Answer 'how many steps?' â€” with a turn when the way is blocked.

        The old version only ever said "walk N steps" and never suggested a
        direction, so a blocked corridor produced no usable guidance.
        """
        sit = self.assess(sensor, scene)

        # Something already very close: do not tell the user to walk anywhere.
        if sit.state in (State.STOP, State.URGENT):
            return ("Stop. Something is very close in front of you. "
                    "Wait until it moves, then ask me again.")

        if sit.dist_m is None:
            return ("The path ahead is clear. Walk straight three steps, "
                    "then ask me again.")

        steps = steps_available(_round_half(sit.dist_m), self.step_len)

        if steps >= 1 and sit.zone == "center":
            return (f"Walk straight {_num(steps)} "
                    f"{'step' if steps == 1 else 'steps'} before the next "
                    f"obstacle, then ask me again.")

        direction = self.best_direction(scene)
        if direction is not None:
            side = scene.nearest(direction, hazard_only=True) if scene else None
            side_m = side.dist_m if (side and side.dist_m is not None) else None
            side_steps = (steps_available(_round_half(side_m), self.step_len)
                          if side_m is not None else 2)
            side_steps = max(1, min(side_steps, config.MAX_STEPS_TO_ANNOUNCE))
            return (f"The way ahead is blocked. Turn {direction}, then walk "
                    f"{_num(side_steps)} "
                    f"{'step' if side_steps == 1 else 'steps'}.")

        return ("The way ahead is blocked and both sides are tight. "
                "Please stop and wait.")


def _nice(label: str) -> str:
    if not label:
        return "Obstacle"
    if label == "obstacle":
        return "Obstacle"
    if label == "dining table":
        return "Table"
    return label.capitalize()


def _with_article(label: str) -> str:
    """'a person', 'an obstacle' - so answers read like speech, not labels."""
    word = _nice(label).lower()
    return ("an " if word[:1] in "aeiou" else "a ") + word


def _approx_distance(dist_m: float) -> str:
    """Distance in words.

    Spoken numbers sound stilted ("about 1.5 metres"), so small distances use
    the phrasing a person would actually use. Everything is fed a value that
    has already been rounded to the nearest half metre.
    """
    if dist_m <= 0.5:
        return "very close"
    if dist_m <= 1.0:
        return "about a metre"
    if dist_m <= 1.5:
        return "about a metre and a half"
    if dist_m <= 2.0:
        return "about two metres"
    if dist_m <= 2.5:
        return "about two and a half metres"
    if dist_m <= 3.0:
        return "about three metres"
    return f"about {dist_m:g} metres"


def _num(n: int) -> str:
    """Small counts as words, because 'walk 2 steps' sounds like a machine."""
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))
