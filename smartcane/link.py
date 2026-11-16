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
        return self.dist_cm is not None and self.age < config.SERIAL_STALE_SEC


class SerialLink:
    def __init__(self, mock: bool = False, dump: bool = False) -> None:
        self.mock = mock
        self.dump = dump
        self._state = SensorState()
        self._lock = threading.Lock()
        self._ser = None
        self._thread: StoppableThread | None = None
        self._format: str | None = None
        self._buf = bytearray()
        self._mock_dist = 250.0

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
            try:
                ser = serial.Serial(port, config.SERIAL_BAUD,
                                    timeout=config.SERIAL_TIMEOUT)
                log.info("opened %s @ %d", port, config.SERIAL_BAUD)
                self._ser = ser
                return port
            except Exception as exc:                    # noqa: BLE001
                log.debug("cannot open %s: %s", port, exc)
        return None

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
                log.debug("bad frame %r: %s", text, exc)

    def _apply_json(self, text: str) -> None:
        obj = json.loads(text)
        self._publish(
            dist_cm=_num(obj.get("d") or obj.get("dist") or obj.get("distance")),
            motion=int(_num(obj.get("m") or obj.get("motion")) or 0),
            gps_fix=int(_num(obj.get("fix")) or 0),
            gps_lat=_num(obj.get("lat")), gps_lon=_num(obj.get("lon")))

    def _apply_kv(self, text: str) -> None:
        vals = {k.lower(): float(v) for k, v in self._KV_RE.findall(text)}
        if not vals:
            return
        dist = vals.get("distance")
        if dist is None:
            dist = vals.get("dist")
        if dist is None:
            dist = vals.get("d")
        # A sketch that prints "Distance: 150.0 cm" is already in centimetres.
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
