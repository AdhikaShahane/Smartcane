"""Entry point: wire the threads together and run the decision loop."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

from . import __version__, config, intent
from .asr import Asr, SpeechEvent
from .audio_out import AudioOut
from .camera import Camera
from .guidance import (Guidance, Priority, State, _approx_distance, _round_half,
                       _with_article)
from .link import SerialLink
from .sos import SosAlarm, SosButton, build_message
from .util import get_logger, resolve_audio_device, setup_logging
from .vision import Vision

log = get_logger("main")


class SmartCane:
    def __init__(self, args) -> None:
        self.args = args
        self.running = True
        self.guidance = Guidance(step_len=config.STEP_DEFAULT)
        self.link = SerialLink(mock=args.mock, dump=args.dump_serial)
        self.camera = Camera(source=args.camera,
                             mock=args.mock or args.no_camera)
        self.vision = Vision(self.camera, mock=args.no_camera)
        self.audio = AudioOut(mute=args.mute, device=args.speaker)
        self.asr = Asr(on_event=self.on_speech,
                       on_speech_start=self.on_speech_start,
                       mock=args.mock, device=args.mic)
        # Panic button. Independent of everything else, so a stuck camera or a
        # crashed detector can never stop it working.
        self.sos = SosAlarm()
        self.sos_button = SosButton(on_press=self._on_sos_press)
        self._last_query_at = 0.0
        self._fault_warned = False
        self._keyboard_mode = False
        # What we were last talking about, so "how do I reach it" refers to
        # the object just described instead of starting from scratch.
        self._ctx_obj = None
        self._ctx_dist: float | None = None
        self._ctx_at = 0.0

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        log.info("Sahayak Drishti v%s starting", __version__)
        self.audio.start()
        self.link.start()
        self.camera.start()
        self.vision.start()

        if self.args.keyboard:
            self._use_keyboard("--keyboard requested")
        elif not self.args.no_mic:
            self.asr.start()
            if not self.asr.enabled:
                # The microphone is the one part we cannot fake. Rather than
                # run a demo with no way to give commands, fall back to the
                # keyboard so the rest of the system can still be shown.
                self._use_keyboard("no microphone available")

        self.sos_button.start()

        # Synthesise the alarm before it is needed. Pressing the button must
        # not also wait for espeak-ng to start.
        self.audio.prewarm([build_message(self.link.state()),
                            config.STARTUP_GREETING])

        self.audio.say(config.STARTUP_GREETING, Priority.INFO, earcon="ok")
        log.info("ready - camera=%s serial=%s tts=%s vision=%s input=%s",
                 self.camera.backend, self.link.state().source,
                 self.audio.tts.backend,
                 "on" if self.vision.enabled else "off",
                 "keyboard" if self._keyboard_mode else "microphone")
        if self.sos_button.available:
            log.info("SOS button armed on GPIO %d", config.SOS_PIN)
        else:
            log.info("SOS: say or type 'sos' (no button detected)")

    def _use_keyboard(self, reason: str) -> None:
        log.warning("=" * 62)
        log.warning("INPUT: %s", reason)
        log.warning("Falling back to KEYBOARD commands.")
        log.warning("Type a command and press Enter, for example:")
        log.warning("    what is ahead      how many steps")
        log.warning("    turn left          stop")
        log.warning("=" * 62)
        try:
            self.asr.stop()
        except Exception:                               # noqa: BLE001
            pass
        self._keyboard_mode = True
        self.asr = Asr(on_event=self.on_speech,
                       on_speech_start=self.on_speech_start,
                       mock=True, device=self.args.mic)
        self.asr.start()

    def stop(self) -> None:
        self.running = False
        try:
            self.sos_button.close()
        except Exception:                               # noqa: BLE001
            pass
        for part in (self.asr, self.vision, self.camera, self.link, self.audio):
            try:
                part.stop()
            except Exception:                           # noqa: BLE001
                pass
        log.info("stopped")

    # -- speech callbacks --------------------------------------------------
    def on_speech_start(self) -> None:
        """Barge-in: the user is talking, so stop talking."""
        if self.audio.is_speaking():
            log.info("barge-in")
            self.audio.interrupt()

    def on_speech(self, event: SpeechEvent) -> None:
        if not event.final:
            return                                  # act only on finals
        text = event.text.strip()
        if not text:
            return
        # The panic word is checked before intent matching so it works even if
        # the grammar does not recognise the rest of the sentence.
        lowered = text.lower()
        if "sos" in lowered or "emergency" in lowered:
            log.warning("SOS triggered by speech")
            self._on_sos_press()
            return

        cmd, score, phrase = intent.classify(text)
        log.info("heard %r -> %s (%.0f) [%s]", text, cmd.value, score, phrase)
        if cmd is intent.Intent.UNKNOWN:
            self.audio.say("Sorry, I did not understand.",
                           Priority.ANSWER, earcon="ok")
            return
        self.handle(cmd)

    # -- conversation context ---------------------------------------------
    def _remember(self, obj) -> None:
        self._ctx_obj = obj
        self._ctx_dist = obj.dist_m if obj is not None else None
        self._ctx_at = time.monotonic()

    def _context_object(self):
        """The object we last talked about, refreshed from the live scene."""
        if self._ctx_obj is None:
            return None
        if time.monotonic() - self._ctx_at > config.CONTEXT_TTL_SEC:
            return None
        scene = self.vision.scene()
        for obj in scene.objects:
            if obj.tid == self._ctx_obj.tid and obj.label == self._ctx_obj.label:
                return obj
        return None

    def _passed_text(self, scene) -> str:
        if self._ctx_obj is None:
            return ("I am not tracking an object. Ask me what is in front of "
                    "you first.")
        live = self._context_object()
        if live is None:
            return ("Yes. It is no longer in view, so you have passed it. "
                    "You can continue walking.")
        if live.dist_m is not None and self._ctx_dist is not None:
            if live.dist_m > self._ctx_dist + 0.5:
                return "Not yet. It is still ahead of you."
            if live.dist_m < self._ctx_dist - 0.5:
                return "Not yet. You are getting closer to it."
        return "It is still in view, so you have not passed it yet."

    def _turn_text(self, sensor, scene) -> str:
        sit = self.guidance.assess(sensor, scene)
        if sit.state in (State.STOP, State.URGENT):
            return "Stop first. Something is too close to turn safely."
        if sit.state == State.CLEAR:
            return "You can continue straight ahead. Nothing is blocking you."
        direction = self.guidance.best_direction(scene)
        if direction is None:
            return "Both sides look tight. Please stop and wait."
        return f"Turn slightly {direction}. That side has more room."

    def _side_text(self, scene, side: str) -> str:
        obj = scene.nearest(side, hazard_only=False) if scene else None
        if obj is None:
            return (f"I do not detect anything on your {side}. "
                    f"I cannot confirm it is completely clear.")
        if obj.dist_m is not None:
            approx = _approx_distance(_round_half(obj.dist_m))
            return (f"I can see {_with_article(obj.label)} on your {side}, "
                    f"{approx} away.")
        return f"I can see {_with_article(obj.label)} on your {side}."

    # -- command dispatch --------------------------------------------------
    def handle(self, cmd: intent.Intent) -> None:
        sensor = self.link.state()
        scene = self.vision.scene()

        if cmd is intent.Intent.STOP or cmd is intent.Intent.CANCEL:
            self.audio.interrupt()
            self.audio.say("Stopped.", Priority.ANSWER, earcon="ok")
            return

        if cmd in (intent.Intent.WHAT_AHEAD, intent.Intent.DESCRIBE):
            top = scene.described(1)
            self._remember(top[0] if top else None)
            self.audio.say(self.guidance.describe(sensor, scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.ALL_OBJECTS:
            self.audio.say(self.guidance.describe_all(sensor, scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.REACH:
            self.audio.say(
                self.guidance.reach_object(self._context_object(), scene),
                Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.PASSED:
            self.audio.say(self._passed_text(scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.TURN:
            self.audio.say(self._turn_text(sensor, scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.AROUND:
            self.audio.say(self.guidance.bypass(sensor, scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd in (intent.Intent.LEFT_CHECK, intent.Intent.RIGHT_CHECK):
            side = ("left" if cmd is intent.Intent.LEFT_CHECK else "right")
            self.audio.say(self._side_text(scene, side),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.IS_SAFE:
            text, earcon = self.guidance.safety_answer(sensor, scene)
            self.audio.say(text, Priority.ANSWER, earcon=earcon)
            return

        if cmd is intent.Intent.HOW_FAR:
            self.audio.say(self.guidance.steps_to_walk(sensor, scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.WHERE_AM_I:
            self.audio.say(self._location_text(sensor),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.REPEAT:
            self.audio.repeat_last()
            return

        if cmd in (intent.Intent.LEFT, intent.Intent.RIGHT,
                   intent.Intent.STRAIGHT):
            self.audio.say(self._direction_text(cmd, scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.LOUDER:
            self.audio.volume = min(1.0, self.audio.volume + 0.15)
            self.audio.say("Louder.", Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.QUIETER:
            self.audio.volume = max(0.15, self.audio.volume - 0.15)
            self.audio.say("Quieter.", Priority.ANSWER, earcon="ok")
            return

        if cmd in (intent.Intent.SLOWER, intent.Intent.FASTER):
            # speaking rate is a TTS property; acknowledge without faking it
            self.audio.say("Speaking rate is fixed for now.",
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.BATTERY:
            self.audio.say(self._battery_text(), Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.WEATHER:
            self.audio.say("Weather is not available offline.",
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.HELP:
            self.audio.say("Emergency. Please ask someone nearby for help.",
                           Priority.URGENT, earcon="urgent")
            return

    # -- honest answers only ----------------------------------------------
    def _location_text(self, sensor) -> str:
        if sensor is not None and sensor.gps_fix and sensor.gps_lat is not None:
            return (f"Location: latitude {sensor.gps_lat:.5f}, "
                    f"longitude {sensor.gps_lon:.5f}.")
        return "Location is not available. No GPS module is connected."

    def _direction_text(self, cmd: intent.Intent, scene) -> str:
        if cmd is intent.Intent.LEFT:
            zone = "left"
        elif cmd is intent.Intent.RIGHT:
            zone = "right"
        else:
            zone = "center"
        nearest = scene.nearest(zone)
        if nearest is None or nearest.dist_m is None:
            if zone == "center":
                return "I don't see anything straight ahead."
            return f"I don't see anything on your {zone}."
        approx = _approx_distance(_round_half(nearest.dist_m))
        where = "straight ahead" if zone == "center" else f"on your {zone}"
        return (f"I can see {_with_article(nearest.label)} {where}, "
                f"{approx} away.")

    def _battery_text(self) -> str:
        try:
            import subprocess
            out = subprocess.run(["vcgencmd", "get_throttled"],
                                 capture_output=True, text=True, timeout=2)
            if "throttled=0x0" in out.stdout:
                return "Power supply is healthy."
            return "Power warning: the supply may be inadequate."
        except Exception:                               # noqa: BLE001
            return "Battery status is not available on this setup."

    # -- SOS ---------------------------------------------------------------
    def _on_sos_press(self) -> None:
        """Button pressed: alarm on. Pressed again while active: cancel."""
        result = self.sos.handle_press()
        if result is None:
            log.debug("SOS press ignored (bounce)")
            return
        if result == "cancelled":
            self.audio.say("Emergency alarm cancelled.", Priority.ANSWER)
            log.warning("SOS cancelled by button")
            return
        now = time.monotonic()
        # Interrupt whatever is being said. This is the one thing that may
        # override an active warning.
        self._speak_sos(now)

    def _speak_sos(self, now: float | None = None) -> None:
        text = build_message(self.link.state())
        # REFLEX is the arbiter's top priority, so this preempts everything.
        self.audio.say(text, Priority.REFLEX)
        self.sos.mark_spoken(now)
        log.warning("SOS: %s", text)

    def _service_sos(self, sensor) -> None:
        """Repeat the alarm while it is active. Called every loop tick."""
        if not self.sos.active:
            return
        if self.sos.due():
            self._speak_sos()

    # -- main loop ---------------------------------------------------------
    def run(self) -> None:
        last_log = 0.0
        try:
            while self.running:
                sensor = self.link.state()
                scene = self.vision.scene()
                self._service_sos(sensor)
                sit = self.guidance.assess(sensor, scene)
                ann = self.guidance.announce(sit, scene=scene)
                if ann is not None:
                    self.audio.say_announcement(ann)

                if self.args.verbose and time.monotonic() - last_log > 2.0:
                    last_log = time.monotonic()
                    log.info("state=%-8s dist=%-6s obj=%-10s "
                             "infer=%.0fms frames=%d%s",
                             sit.state,
                             f"{sit.dist_m:.2f}m" if sit.dist_m else "-",
                             sit.label or "-", scene.infer_ms,
                             sensor.frames,
                             "  <== SENSOR FAULT" if sensor.sensor_fault
                             else "")

                # A dead ultrasonic reads as "clear" by design, so say so out
                # loud once instead of letting it look like an empty corridor.
                if sensor.sensor_fault and not self._fault_warned:
                    log.warning("ultrasonic is returning no valid readings - "
                                "check the sensor wiring; obstacle detection "
                                "is NOT active")
                    self._fault_warned = True
                elif not sensor.sensor_fault and self._fault_warned:
                    log.info("ultrasonic recovered")
                    self._fault_warned = False

                if self.args.duration and \
                        time.monotonic() - self._started > self.args.duration:
                    break
                time.sleep(0.05)
        except KeyboardInterrupt:
            log.info("interrupted")
        finally:
            self.stop()

    def mark_start(self) -> None:
        self._started = time.monotonic()


def _test_mic(device, seconds: float = 4.0) -> int:
    """Record a few seconds and report whether the microphone actually hears.

    This exists because "the mic does not work" is almost never one problem:
    it can be a missing capture device, a muted input, or a plug with no mic
    pin at all. Printing a level tells them apart in one run.
    """
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:                            # noqa: BLE001
        print(f"cannot load audio libraries: {exc}")
        return 1

    try:
        resolved = resolve_audio_device(device, "in")
    except Exception:                                   # noqa: BLE001
        resolved = None

    try:
        info = sd.query_devices(resolved, "input")
    except Exception as exc:                            # noqa: BLE001
        print(f"\nNO CAPTURE DEVICE AVAILABLE: {exc}")
        print("\nOn a Raspberry Pi this usually means the headset is plugged")
        print("into the 3.5mm jack, which is OUTPUT ONLY unless you have a")
        print("TRRS headset with a mic pin. A normal IEM/earphone cable is TRS")
        print("and carries no microphone.")
        print("\nUse a USB headset, or a USB sound card with a mic input.")
        print("Check what the system sees with:  arecord -l")
        return 1

    print(f"\nRecording {seconds:.0f}s from: {info['name']}")
    print(">>> SPEAK NOW: count out loud, one two three four <<<\n")

    # The device may not support 16 kHz. PortAudio refuses rates the hardware
    # does not offer, so try the same ladder the real microphone path uses --
    # otherwise this test reports MIC DEAD on perfectly good hardware.
    rec = None
    used_rate = 0
    for rate in (16000, 48000, 44100, 32000):
        try:
            rec = sd.rec(int(seconds * rate), samplerate=rate, channels=1,
                         dtype="int16", device=resolved)
            sd.wait()
            used_rate = rate
            break
        except Exception as exc:                        # noqa: BLE001
            print(f"  could not record at {rate} Hz: {exc}")
            rec = None
    if rec is None:
        print("\nRESULT: MIC DEAD - the device would not open at any rate.")
        print("  Check it is not in use by another program, then: arecord -l")
        return 1
    if used_rate != 16000:
        print(f"  (recorded at {used_rate} Hz - smartcane will resample this)")

    data = rec.astype("float32")
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
    print(f"peak = {peak:8.0f}    rms = {rms:8.1f}")

    if peak < 50:
        print("\nRESULT: MIC DEAD - no signal at all.")
        print("  The device opened but heard nothing. Wrong input device, or")
        print("  a plug with no mic pin.")
        return 1
    if peak < 300:
        print("\nRESULT: MIC VERY QUIET - something is connected but barely.")
        print("  Raise the gain:  alsamixer  (F4 for capture, up arrow)")
        return 1
    print("\nRESULT: MIC OK - it heard you. Voice input will work.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="smartcane",
                                description="Sahayak Drishti smart cane")
    p.add_argument("--mock", action="store_true",
                   help="no hardware: synthetic camera/sensor, type commands")
    p.add_argument("--no-camera", action="store_true", help="skip the camera")
    p.add_argument("--no-mic", action="store_true", help="skip speech input")
    p.add_argument("--keyboard", action="store_true",
                   help="type commands instead of speaking them "
                        "(use this if the microphone will not work)")
    p.add_argument("--mute", action="store_true", help="print instead of speak")
    p.add_argument("--demo", action="store_true",
                   help="SIMULATE location sharing in the SOS alarm (for "
                        "presentations only; nothing is actually sent)")
    p.add_argument("--camera", default=config.CAMERA_SOURCE,
                   help="auto | 0 | picamera2 | http://phone:8080/video")
    p.add_argument("--dump-serial", action="store_true",
                   help="print raw Arduino bytes (use this first when wiring)")
    p.add_argument("--list-audio", action="store_true",
                   help="list audio devices and exit (pick the Jabra/headset)")
    p.add_argument("--test-mic", action="store_true",
                   help="record a few seconds and report whether the mic hears")
    p.add_argument("--mic", default=config.AUDIO_INPUT_DEVICE,
                   help="input device index or name (for --test-mic too)")
    p.add_argument("--speaker", default=config.AUDIO_OUTPUT_DEVICE,
                   help="output device index or name")
    p.add_argument("--verbose", action="store_true", help="log state twice a second")
    p.add_argument("--duration", type=float, default=0.0,
                   help="stop after N seconds (0 = run forever)")
    p.add_argument("--version", action="version", version=__version__)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging("DEBUG" if args.verbose else config.LOG_LEVEL)

    if getattr(args, "demo", False):
        config.DEMO_MODE = True
    if config.DEMO_MODE:
        log.warning("=" * 68)
        log.warning("DEMO MODE - the SOS alarm SIMULATES location sharing.")
        log.warning("No coordinates are read, computed or transmitted, and no")
        log.warning("message reaches anyone. The spoken sentence describes a")
        log.warning("feature this build does not have yet.")
        log.warning("Do not show this mode to a real user as a working alarm.")
        log.warning("=" * 68)

    if args.list_audio:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            print(devices)
            ins = [i for i, d in enumerate(devices) if d["max_input_channels"] > 0]
            outs = [i for i, d in enumerate(devices) if d["max_output_channels"] > 0]
            print(f"\ncapture devices: {len(ins)}   playback devices: {len(outs)}")
            if ins:
                for i in ins:
                    print(f"  [{i}] IN  {devices[i]['name']}")
            else:
                print("  NONE - there is no microphone available.")
                print("  The Pi 3.5mm jack is OUTPUT ONLY on most setups. A TRS")
                print("  headset plug has no mic pin. Use a USB headset or a")
                print("  USB sound card with a separate mic input.")
            print(f"\nDefault input : {sd.default.device[0]}")
            print(f"Default output: {sd.default.device[1]}")
            print("\nTo pin a device, export before running:")
            print("  SMARTCANE_MIC=<index>  SMARTCANE_SPEAKER=<index>")
        except Exception as exc:                        # noqa: BLE001
            log.error("cannot query audio devices: %s", exc)
            log.error("on the Pi this usually means: "
                      "sudo apt install -y libportaudio2")
        return 0

    if args.test_mic:
        return _test_mic(args.mic, args.duration or 4.0)

    if args.dump_serial:
        link = SerialLink(mock=args.mock, dump=True)
        link.start()
        log.info("dumping serial - press Ctrl+C to stop")
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            link.stop()
        return 0

    cane = SmartCane(args)
    cane.mark_start()

    def _sigint(_sig, _frame):
        cane.running = False

    signal.signal(signal.SIGINT, _sigint)

    try:
        cane.start()
    except Exception as exc:                            # noqa: BLE001
        log.exception("startup failed: %s", exc)
        return 1
    cane.run()
    # OpenCV, torch and PortAudio leave C++ objects alive in worker threads.
    # The normal interpreter teardown can abort with "terminate called without
    # an active exception" *after* a clean shutdown. Flush logs and leave now.
    logging.shutdown()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
