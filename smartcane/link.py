"""Arduino sensor-hub link.

Reads the microcontroller's serial stream and publishes a `SensorState`.

Why so defensive: the Pi has no idea what firmware the Arduino is running. So
this parser auto-detects four plausible formats and can dump raw bytes with
`python -m smartcane --dump-serial`, which is the first thing to run when the
distance readings look wrong.

Supported wire formats
  1. binary   AA 55 | type | len | payload... | crc8      (recommended sketch)
  2. json     {"d":123,"m":1,"fix":1,"lat":..,"lon":..}
  3. csv      123,45,1
  4. key:val  dist:123 mot:45 fix:1
"""
from __future__ import annotations

import glob
import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from . import config
from .util import StoppableThread, get_logger

log = get_logger("link")

FRAME_HEADER = b"\xaa\x55"
TYPE_FAST = 0x01
TYPE_SLOW = 0x02

# A line that carries a number, used to identify the wire format. Banners and
# headers must not match these.
_KV_LINE = re.compile(rb"[A-Za-z_][A-Za-z_0-9]*\s*[:=]\s*-?\d")
_CSV_LINE = re.compile(rb"^\s*-?\d+(\.\d+)?\s*[,;]")
_BARE_NUMBER = re.compile(rb"^\s*-?\d+(\.\d+)?\s*$")

# Distance values must be followed by a unit or a separator. Without that rule
# a corrupted line such as "Distance: 1s.7 cm" matches the leading "1" and the
# Pi believes there is an obstacle 1 cm away.
_KV_RE = re.compile(
    r"([a-zA-Z_][a-zA-Z_0-9]*)\s*[:=]\s*(-?\d+(?:\.\d+)?)\s*"
    r"(?:cm|mm|metres?|meters?|m\b|$|\||,|;)",
    re.IGNORECASE)

# The Grove Ranger cannot see closer than 2 cm or further than 350 cm, so any
# reading outside this window is a corrupt frame, not a distance.
DIST_MIN_CM = 2.0
DIST_MAX_CM = 400.0


def _crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


@dataclass
class SensorState:
    dist_cm: float | None = None
    motion: int = 0
    gps_fix: int = 0
    gps_lat: float | None = None
    gps_lon: float | None = None
    sensor_fault: bool = False
    # False when too many frames on the wire are corrupt to trust any of them.
    reliable: bool = True
    updated_at: float = 0.0
    frames: int = 0
    source: str = "none"

    @property
    def dist_m(self) -> float | None:
        return None if self.dist_cm is None else self.dist_cm / 100.0

    @property
    def age(self) -> float:
        return time.monotonic() - self.updated_at if self.updated_at else 1e9

    @property
    def valid(self) -> bool:
        return (self.dist_cm is not None
                and self.age < config.SERIAL_STALE_SEC
                and self.reliable)


class SerialLink:
    def __init__(self, mock: bool = False, dump: bool = False) -> None:
        self.mock = mock
        self.dump = dump
        self._state = SensorState()
        self._lock = threading.Lock()
        self._ser = None
        self._baud = config.SERIAL_BAUD
        self._thread: StoppableThread | None = None
        self._format: str | None = None
        self._buf = bytearray()
        self._mock_dist = 250.0
        self._discard_count = 0
        self._discard_logged_at = 0.0
        # Outlier rejection: recent accepted distances, and a candidate change
        # that must be confirmed by a second agreeing reading.
        self._accepted: deque = deque(maxlen=5)
        self._pending_cm: float | None = None
        # Rolling readability window, for the reliability gate.
        self._frame_results: deque = deque(
            maxlen=config.LINK_RELIABILITY_WINDOW)

    # -- public ------------------------------------------------------------
    def start(self) -> None:
        if self.mock:
            self._state.source = "mock"
            self._thread = _MockLink(self)
        else:
            port = self._open()
            if port is None:
                log.warning("no Arduino serial port found - camera-only mode")
                self._state.source = "none"
                return
            self._state.source = port
            self._thread = _SerialReader(self)
        self._thread.start()
        log.info("serial link up (%s)", self._state.source)

    def stop(self) -> None:
        if self._thread:
            self._thread.stop()
        if self._ser:
            try:
                self._ser.close()
            except Exception:                           # noqa: BLE001
                pass

    def state(self) -> SensorState:
        with self._lock:
            return SensorState(
                dist_cm=self._state.dist_cm, motion=self._state.motion,
                gps_fix=self._state.gps_fix, gps_lat=self._state.gps_lat,
                gps_lon=self._state.gps_lon,
                sensor_fault=self._state.sensor_fault,
                reliable=self._state.reliable,
                updated_at=self._state.updated_at,
                frames=self._state.frames, source=self._state.source)

    # -- internals ---------------------------------------------------------
    def _open(self):
        try:
            import serial
        except ImportError:
            log.error("pyserial not installed: pip install pyserial")
            return None

        candidates: list[str] = []
        if config.SERIAL_PORT:
            candidates = [config.SERIAL_PORT]
        else:
            candidates = sorted(
                glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
                + glob.glob("/dev/serial0") + glob.glob("/dev/rfcomm*")
                + [f"COM{i}" for i in range(1, 9) if os.name == "nt"])

        for port in candidates:
            baud = self._probe_baud(port, serial)
            try:
                ser = serial.Serial(port, baud, timeout=config.SERIAL_TIMEOUT)
                log.info("opened %s @ %d", port, baud)
                self._ser = ser
                self._baud = baud
                return port
            except Exception as exc:                    # noqa: BLE001
                log.debug("cannot open %s: %s", port, exc)
        return None

    def _probe_baud(self, port: str, serial) -> int:
        """Work out which baud rate the Arduino is actually using.

        The sketch on the board may run at 9600 (a plain text sketch) or
        115200 (our binary protocol). Opening at the wrong rate yields garbage
        and looks exactly like a broken sensor, so try both and keep whichever
        one produces parseable data.
        """
        candidates = [config.SERIAL_BAUD]
        for alt in (9600, 19200, 38400, 57600, 115200):
            if alt not in candidates:
                candidates.append(alt)

        for baud in candidates:
            try:
                ser = serial.Serial(port, baud, timeout=0.1)
            except Exception as exc:                    # noqa: BLE001
                log.debug("probe %s @ %d failed: %s", port, baud, exc)
                continue
            try:
                probe = SerialLink(mock=False)
                raw = bytearray()
                deadline = time.monotonic() + 1.2
                while (time.monotonic() < deadline
                       and probe._state.frames < 3):
                    chunk = ser.read(ser.in_waiting or 1)
                    if chunk:
                        raw.extend(chunk)
                        probe.feed(chunk)
                # Readable text proves the baud is right even when every number
                # is corrupted. Requiring parsed frames meant a noisy-but-
                # correctly-configured link was reported as "cannot confirm
                # the baud rate", which sent the user chasing the wrong fault.
                if probe._state.frames >= 3 or _looks_like_our_text(raw):
                    if baud != config.SERIAL_BAUD:
                        log.warning("Arduino is talking at %d baud, not %d "
                                    "- using %d", baud, config.SERIAL_BAUD, baud)
                    else:
                        log.info("Arduino confirmed at %d baud", baud)
                    return baud
            except Exception as exc:                    # noqa: BLE001
                log.debug("probe read failed at %d: %s", baud, exc)
            finally:
                try:
                    ser.close()
                except Exception:                       # noqa: BLE001
                    pass

        log.warning("could not confirm the Arduino's baud rate - "
                    "trying %d", config.SERIAL_BAUD)
        return config.SERIAL_BAUD

    def _publish(self, **kw) -> None:
        with self._lock:
            for key, value in kw.items():
                if value is not None:
                    setattr(self._state, key, value)
            self._state.updated_at = time.monotonic()
            self._state.frames += 1

    def _detect_format(self, chunk: bytes) -> str:
        """Identify the wire format from buffered data.

        Many sketches print a banner first ("====...", "Grove Ultrasonic
        Ranger V2.0") and only then real data. Deciding on the first bytes
        would lock onto the banner and misread every later line, so we scan
        line by line and commit only when a line actually looks like data.
        """
        if chunk.startswith(FRAME_HEADER):
            return "binary"
        for raw in chunk.split(b"\n"):
            line = raw.strip()
            if not line:
                continue
            if line.startswith(b"{"):
                return "json"
            if _KV_LINE.search(line):
                return "kv"
            if _CSV_LINE.match(line) or _BARE_NUMBER.match(line):
                return "csv"
        return ""

    def feed(self, chunk: bytes) -> None:
        """Parse whatever bytes arrived. Safe to call with partial frames."""
        if not chunk:
            return
        if self.dump:
            print(f"RAW[{len(chunk)}] {chunk!r}", flush=True)
        self._buf.extend(chunk)

        if self._format is None:
            buf = bytes(self._buf)
            if buf.startswith(FRAME_HEADER):
                self._format = "binary"
            else:
                detected = self._detect_format(buf)
                if not detected:
                    if len(buf) > 8192:
                        # give up waiting and assume csv so we at least try
                        self._format = "csv"
                        log.warning("could not identify serial format, "
                                    "assuming csv")
                    else:
                        return                      # wait for a data line
                else:
                    self._format = detected
            log.info("serial format detected: %s", self._format)

        if self._format == "binary":
            self._parse_binary()
        else:
            self._parse_text()

    def _parse_binary(self) -> None:
        buf = self._buf
        while True:
            idx = buf.find(FRAME_HEADER)
            if idx < 0:
                buf.clear()
                return
            if idx:
                del buf[:idx]
            if len(buf) < 4:
                return
            length = buf[3]
            total = 4 + length + 1
            if len(buf) < total:
                return
            body = bytes(buf[:4 + length])
            crc = buf[total - 1]
            if _crc8(body) != crc:
                del buf[:2]                             # resync
                continue
            ftype = buf[2]
            payload = body[4:]
            del buf[:total]
            if ftype == TYPE_FAST and len(payload) >= 4:
                # seq:u8, dist_cm:u16, flags:u8
                #   bit0 = reflex asserted, bit1 = motion, bit2 = sensor fault
                dist = payload[1] | (payload[2] << 8)
                flags = payload[3]
                self._publish(dist_cm=float(dist),
                              motion=(flags >> 1) & 0x01,
                              sensor_fault=bool(flags & 0x04))
            elif ftype == TYPE_SLOW and len(payload) >= 11:
                fix, sats = payload[0], payload[1]
                lat = int.from_bytes(payload[2:6], "little", signed=True) / 1e7
                lon = int.from_bytes(payload[6:10], "little", signed=True) / 1e7
                self._publish(gps_fix=fix, gps_lat=lat, gps_lon=lon)

    _KV_RE = re.compile(r"([a-zA-Z_]+)\s*[:=]\s*(-?\d+(?:\.\d+)?)")

    def _parse_text(self) -> None:
        while b"\n" in self._buf:
            line, _, rest = bytes(self._buf).partition(b"\n")
            self._buf = bytearray(rest)
            text = line.decode("utf-8", "ignore").strip()
            if not text:
                continue
            try:
                if self._format == "json":
                    self._apply_json(text)
                elif self._format == "kv":
                    self._apply_kv(text)
                else:
                    self._apply_csv(text)
            except Exception as exc:                    # noqa: BLE001
                self._record_frame(False)
                log.debug("bad frame %r: %s", text, exc)

    def _apply_json(self, text: str) -> None:
        obj = json.loads(text)
        self._publish(
            dist_cm=_num(obj.get("d") or obj.get("dist") or obj.get("distance")),
            motion=int(_num(obj.get("m") or obj.get("motion")) or 0),
            gps_fix=int(_num(obj.get("fix")) or 0),
            gps_lat=_num(obj.get("lat")), gps_lon=_num(obj.get("lon")))

    def _accept_distance(self, dist_cm: float) -> bool:
        """Is this reading consistent with what the sensor has been saying?

        A corrupt byte inside the number field produces a reading that is
        still inside the valid range - "150.4 cm" becomes "19.4 cm" - so a
        range check alone cannot catch it. Comparing against the recent median
        does, and requiring a second agreeing reading means a genuine change
        (someone stepping closer) is still accepted after one frame.
        """
        if len(self._accepted) < 3:
            self._accepted.append(dist_cm)
            return True

        recent = sorted(self._accepted)
        median = recent[len(recent) // 2]
        jump_cm = config.OUTLIER_JUMP_M * 100.0

        if abs(dist_cm - median) <= jump_cm:
            self._accepted.append(dist_cm)
            self._pending_cm = None
            return True

        # Disagrees with the recent median. Only accept it once a second
        # reading confirms the new value, so real movement is not blocked.
        if self._pending_cm is not None and abs(dist_cm - self._pending_cm) <= 30.0:
            self._accepted.clear()
            self._accepted.append(dist_cm)
            self._pending_cm = None
            return True

        self._pending_cm = dist_cm
        return False

    def _record_frame(self, ok: bool) -> None:
        self._frame_results.append(ok)
        if len(self._frame_results) >= 8:
            ratio = sum(self._frame_results) / float(len(self._frame_results))
            self._state.reliable = ratio >= config.MIN_LINK_RELIABILITY

    def _apply_kv(self, text: str) -> None:
        vals = {k.lower(): float(v) for k, v in self._KV_RE.findall(text)}
        if not vals:
            # A line we could not parse at all is still a failed frame. Not
            # counting it let a stream of unreadable noise look perfectly
            # reliable, because only parseable-but-out-of-range lines scored.
            self._record_frame(False)
            return
        dist = vals.get("distance")
        if dist is None:
            dist = vals.get("dist")
        if dist is None:
            dist = vals.get("d")
        if dist is None:
            return
        # A sketch that prints "Distance: 150.0 cm" is already in centimetres.
        if not (DIST_MIN_CM <= dist <= DIST_MAX_CM):
            # Corrupt or out-of-range frame: drop it rather than act on it.
            # Log at most once every two seconds: a bad baud rate produces
            # thousands of these and would bury the rest of the log.
            self._discard_count += 1
            self._record_frame(False)
            now = time.monotonic()
            if now - self._discard_logged_at >= 2.0:
                log.warning(
                    "serial line is corrupt (%d bad frames, e.g. %r). "
                    "Check the cable; the binary sketch sends a CRC and "
                    "would reject these cleanly.",
                    self._discard_count, text.strip()[:60])
                self._discard_logged_at = now
            if not self._state.reliable:
                log.debug("serial link unreliable - ultrasonic ignored")
            return

        if not self._accept_distance(dist):
            self._record_frame(False)
            log.debug("outlier rejected: %.1f cm vs median of %s",
                      dist, [round(v) for v in self._accepted])
            return

        self._record_frame(True)
        self._publish(
            dist_cm=dist,
            motion=int(vals.get("mot", vals.get("m", 0))),
            gps_fix=int(vals.get("fix", 0)),
            gps_lat=vals.get("lat"), gps_lon=vals.get("lon"))

    def _apply_csv(self, text: str) -> None:
        parts = [p.strip() for p in text.replace(";", ",").split(",")]
        nums = [float(p) for p in parts if _is_num(p)]
        if not nums:
            return
        self._publish(dist_cm=nums[0],
                      motion=int(nums[1]) if len(nums) > 1 else 0)


def _is_num(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _looks_like_our_text(raw: bytes) -> bool:
    """True when the stream is mostly printable ASCII with a known marker.

    Used only to confirm a baud rate: corrupt numbers still prove the rate is
    correct as long as the surrounding text is readable.
    """
    if len(raw) < 12:
        return False
    printable = sum(1 for b in raw if 32 <= b < 127 or b in (9, 10, 13))
    if printable / float(len(raw)) < 0.9:
        return False
    lowered = raw.lower()
    return any(marker in lowered for marker in
               (b"istanc", b" cm", b"path", b"obstacle", b"dist"))


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _SerialReader(StoppableThread):
    def __init__(self, link: SerialLink) -> None:
        super().__init__("serial")
        self.link = link

    def _run(self) -> None:
        ser = self.link._ser
        while not self.stopped:
            try:
                chunk = ser.read(ser.in_waiting or 1)
            except Exception as exc:                    # noqa: BLE001
                log.warning("serial read failed: %s", exc)
                self.sleep(0.5)
                continue
            if chunk:
                self.link.feed(chunk)


class _MockLink(StoppableThread):
    """Synthetic distance so the whole system can be exercised with no hardware."""

    def __init__(self, link: SerialLink) -> None:
        super().__init__("serial-mock")
        self.link = link
        self._t = 0.0

    def _run(self) -> None:
        while not self.stopped:
            self._t += 0.05
            # slow sweep 2.6 m -> 0.3 m -> 2.6 m
            phase = (self._t % 12.0) / 12.0
            dist_cm = 260.0 - 230.0 * (1 - abs(phase * 2 - 1))
            self.link._publish(dist_cm=dist_cm, motion=1)
            self.sleep(0.05)
