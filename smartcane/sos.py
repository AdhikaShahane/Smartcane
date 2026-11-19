"""Panic button: one press, loud alarm, repeat until cancelled.

Wiring
------
    GPIO 17 (physical pin 11) ----[ button ]---- GND (pin 9 or 14)

The internal pull-up is enabled in software, so no resistor is needed: the pin
reads HIGH when idle and LOW when pressed. A cheap tactile button is fine; a
panel-mount button is better because it survives being carried around.

Honesty rule
------------
This cane has **no GPS**. A message saying "your location has been shared"
would be false, and a blind person in trouble would wait for help that was
never called. So the alarm says what is actually true:

    with a GPS fix     -> "Emergency. I need help. My location is 18.520,
                          73.856."
    without one        -> "Emergency. I need help. My location is unknown."

Add a GPS module to the Arduino and send `fix/lat/lon` frames (link.py already
parses them) and the message upgrades by itself, with no code change here.
"""
from __future__ import annotations

import time
from typing import Callable

from . import config
from .util import get_logger

log = get_logger("sos")


def location_sentence(sensor) -> str:
    """What we truthfully know about where the user is."""
    fix = getattr(sensor, "gps_fix", 0) if sensor is not None else 0
    lat = getattr(sensor, "gps_lat", None) if sensor is not None else None
    lon = getattr(sensor, "gps_lon", None) if sensor is not None else None
    if fix and lat is not None and lon is not None:
        return f"My location is {lat:.3f}, {lon:.3f}."
    return "My location is unknown."


def build_message(sensor) -> str:
    """The full alarm sentence.

    In demo mode this returns the simulated "location shared" line, which the
    product would only be able to say once a real GPS and a real notification
    channel were fitted. Outside demo mode it never claims anything untrue.
    """
    if config.DEMO_MODE:
        return config.SOS_DEMO_MESSAGE
    location = location_sentence(sensor)
    try:
        return config.SOS_MESSAGE.format(location=location)
    except (KeyError, IndexError):
        # A custom message without the placeholder is used verbatim.
        return config.SOS_MESSAGE


class SosButton:
    """A debounced panic button, with graceful degradation.

    Falls back in this order: gpiozero -> RPi.GPIO -> keyboard only. A missing
    GPIO library must never stop the cane from starting.
    """

    def __init__(self, on_press: Callable[[], None] | None = None,
                 on_release: Callable[[], None] | None = None,
                 pin: int | None = None) -> None:
        self.pin = config.SOS_PIN if pin is None else pin
        self.on_press = on_press
        self.on_release = on_release
        self.backend = "none"
        self.available = False
        self._button = None
        self._pressed_at: float | None = None

    def start(self) -> bool:
        if not config.SOS_ENABLED:
            log.info("SOS button disabled (SMARTCANE_SOS=0)")
            return False
        if self._start_gpiozero() or self._start_rpigpio():
            self.available = True
            log.info("SOS button on GPIO %d (%s)", self.pin, self.backend)
            return True
        log.info("SOS button unavailable - no GPIO library. "
                 "Use the keyboard: type 'sos'")
        return False

    def _start_gpiozero(self) -> bool:
        try:
            from gpiozero import Button
        except Exception:                               # noqa: BLE001
            return False
        try:
            self._button = Button(
                self.pin, pull_up=True,
                bounce_time=config.SOS_BOUNCE_SEC)
            self._button.when_pressed = self._handle_press
            self._button.when_released = self._handle_release
            self.backend = "gpiozero"
            return True
        except Exception as exc:                        # noqa: BLE001
            log.debug("gpiozero failed on GPIO %d: %s", self.pin, exc)
            return False

    def _start_rpigpio(self) -> bool:
        try:
            import RPi.GPIO as GPIO
        except Exception:                               # noqa: BLE001
            return False
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(
                self.pin, GPIO.FALLING,
                callback=lambda _ch: self._handle_press(),
                bouncetime=int(config.SOS_BOUNCE_SEC * 1000))
            self.backend = "RPi.GPIO"
            return True
        except Exception as exc:                        # noqa: BLE001
            log.debug("RPi.GPIO failed on GPIO %d: %s", self.pin, exc)
            return False

    # -- events ------------------------------------------------------------
    def _handle_press(self) -> None:
        self._pressed_at = time.monotonic()
        log.warning("SOS button pressed")
        if self.on_press is not None:
            try:
                self.on_press()
            except Exception as exc:                    # noqa: BLE001
                log.error("SOS handler failed: %s", exc)

    def _handle_release(self) -> None:
        held = 0.0
        if self._pressed_at is not None:
            held = time.monotonic() - self._pressed_at
            self._pressed_at = None
        if self.on_release is not None:
            try:
                self.on_release(held)
            except Exception as exc:                    # noqa: BLE001
                log.error("SOS release handler failed: %s", exc)

    def simulate_press(self) -> None:
        """Used by the keyboard fallback and by tests."""
        self._handle_press()

    def simulate_release(self, held: float = 0.0) -> None:
        if self.on_release is not None:
            try:
                self.on_release(held)
            except Exception as exc:                    # noqa: BLE001
                log.error("SOS release handler failed: %s", exc)

    def close(self) -> None:
        try:
            if self._button is not None:
                self._button.close()
        except Exception:                               # noqa: BLE001
            pass


class SosAlarm:
    """Tracks whether the alarm is active and when to repeat it.

    Deliberately dumb: it decides *when* to speak, not *what* to say. The main
    loop owns the speaker so the alarm cannot fight the audio arbiter.
    """

    def __init__(self) -> None:
        self.active = False
        self.started_at = 0.0
        self._last_spoken = 0.0
        self._last_event_at = -1e9

    def trigger(self, now: float | None = None) -> bool:
        """Turn the alarm on. Returns True if it was not already on."""
        now = now if now is not None else time.monotonic()
        if self.active:
            return False
        self.active = True
        self.started_at = now
        self._last_spoken = 0.0            # force an immediate announcement
        return True

    def handle_press(self, now: float | None = None) -> str | None:
        """One press = raise, next press = cancel, bounce = ignore.

        Returns "triggered", "cancelled", or None when the press was too soon
        after the last one to be a real, separate press.
        """
        now = now if now is not None else time.monotonic()
        if (now - self._last_event_at) < config.SOS_DEBOUNCE_SEC:
            return None
        self._last_event_at = now
        if self.active:
            self.cancel()
            return "cancelled"
        self.trigger(now)
        return "triggered"

    def cancel(self) -> bool:
        if not self.active:
            return False
        self.active = False
        return True

    def due(self, now: float | None = None) -> bool:
        """Has enough time passed that the alarm should sound again?

        With SOS_REPEAT_SEC at 0 - the default - this always returns False:
        one press says the alarm once and then stays quiet.
        """
        if not self.active:
            return False
        if config.SOS_REPEAT_SEC <= 0:
            return False
        now = now if now is not None else time.monotonic()
        return (now - self._last_spoken) >= config.SOS_REPEAT_SEC

    def mark_spoken(self, now: float | None = None) -> None:
        self._last_spoken = now if now is not None else time.monotonic()

    @property
    def duration(self) -> float:
        if not self.active:
            return 0.0
        return time.monotonic() - self.started_at
