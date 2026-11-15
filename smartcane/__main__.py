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
from .guidance import Guidance, Priority, State
from .link import SerialLink
from .util import get_logger, setup_logging
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
        self.audio = AudioOut(mute=args.mute)
        self.asr = Asr(on_event=self.on_speech,
                       on_speech_start=self.on_speech_start,
                       mock=args.mock)
        self._last_query_at = 0.0

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        log.info("Sahayak Drishti v%s starting", __version__)
        self.audio.start()
        self.link.start()
        self.camera.start()
        self.vision.start()
        if not self.args.no_mic:
            self.asr.start()
        self.audio.say(config.STARTUP_GREETING, Priority.INFO, earcon="ok")
        log.info("ready - camera=%s serial=%s tts=%s vision=%s",
                 self.camera.backend, self.link.state().source,
                 self.audio.tts.backend,
                 "on" if self.vision.enabled else "off")

    def stop(self) -> None:
        self.running = False
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
        cmd, score, phrase = intent.classify(text)
        log.info("heard %r -> %s (%.0f) [%s]", text, cmd.value, score, phrase)
        if cmd is intent.Intent.UNKNOWN:
            self.audio.say("Sorry, I did not understand.",
                           Priority.ANSWER, earcon="ok")
            return
        self.handle(cmd)

    # -- command dispatch --------------------------------------------------
    def handle(self, cmd: intent.Intent) -> None:
        sensor = self.link.state()
        scene = self.vision.scene()

        if cmd is intent.Intent.STOP or cmd is intent.Intent.CANCEL:
            self.audio.interrupt()
            self.audio.say("Stopped.", Priority.ANSWER, earcon="ok")
            return

        if cmd in (intent.Intent.WHAT_AHEAD, intent.Intent.DESCRIBE):
            self.audio.say(self.guidance.describe(sensor, scene),
                           Priority.ANSWER, earcon="ok")
            return

        if cmd is intent.Intent.IS_SAFE:
            sit = self.guidance.assess(sensor, scene)
            if sit.blocked:
                self.audio.say(f"Not safe. {self.guidance.describe(sensor, scene)}",
                               Priority.ANSWER, earcon="urgent")
            else:
                self.audio.say("Path is clear. You can walk.",
                               Priority.ANSWER, earcon="ok")
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
        return "No GPS fix yet. I cannot give your location."

    def _direction_text(self, cmd: intent.Intent, scene) -> str:
        if cmd is intent.Intent.LEFT:
            zone = "left"
        elif cmd is intent.Intent.RIGHT:
            zone = "right"
        else:
            zone = "center"
        nearest = scene.nearest(zone)
        if nearest is None or nearest.dist_m is None:
            return f"Nothing detected on your {zone}." if zone != "center" \
                else "Nothing detected ahead."
        return (f"Something on your {zone}, "
                f"about {nearest.dist_m:.1f} metres.")

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

    # -- main loop ---------------------------------------------------------
    def run(self) -> None:
        last_log = 0.0
        try:
            while self.running:
                sensor = self.link.state()
                scene = self.vision.scene()
                sit = self.guidance.assess(sensor, scene)
                ann = self.guidance.announce(sit)
                if ann is not None:
                    self.audio.say_announcement(ann)

                if self.args.verbose and time.monotonic() - last_log > 2.0:
                    last_log = time.monotonic()
                    log.info("state=%-8s dist=%-6s obj=%-10s "
                             "infer=%.0fms frames=%d",
                             sit.state,
                             f"{sit.dist_m:.2f}m" if sit.dist_m else "-",
                             sit.label or "-", scene.infer_ms,
                             sensor.frames)

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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="smartcane",
                                description="Sahayak Drishti smart cane")
    p.add_argument("--mock", action="store_true",
                   help="no hardware: synthetic camera/sensor, type commands")
    p.add_argument("--no-camera", action="store_true", help="skip the camera")
    p.add_argument("--no-mic", action="store_true", help="skip speech input")
    p.add_argument("--mute", action="store_true", help="print instead of speak")
    p.add_argument("--camera", default=config.CAMERA_SOURCE,
                   help="auto | 0 | picamera2 | http://phone:8080/video")
    p.add_argument("--dump-serial", action="store_true",
                   help="print raw Arduino bytes (use this first when wiring)")
    p.add_argument("--verbose", action="store_true", help="log state twice a second")
    p.add_argument("--duration", type=float, default=0.0,
                   help="stop after N seconds (0 = run forever)")
    p.add_argument("--version", action="version", version=__version__)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging("DEBUG" if args.verbose else config.LOG_LEVEL)

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
