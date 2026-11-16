"""Single owner of the speaker.

This is the fix for "audio output everything is messed up". The original code
called pyttsx3 from two threads at once, which is not thread-safe and produces
clipped, garbled or skipped speech. Here exactly one thread ever touches the
output device, and everyone else enqueues messages with a priority.

    Priority 0  REFLEX    earcon, preempts everything
    Priority 1  URGENT    immediate warning, preempts speech
    Priority 2  ANSWER    reply to a command
    Priority 3  ADVISORY  proactive guidance
    Priority 4  INFO      path clear, status

Two more fixes live here:
  * one sample rate end to end (48 kHz). Piper and espeak-ng emit 22.05 kHz;
    feeding that straight to a 48 kHz device is the "messed up audio" bug class.
  * every utterance is interruptible, so barge-in works.
"""
from __future__ import annotations

import io
import queue
import shutil
import subprocess
import threading
import wave
from dataclasses import dataclass

import numpy as np

from . import config
from .guidance import Announcement, Priority
from .util import StoppableThread, get_logger, resolve_audio_device

log = get_logger("audio_out")

try:
    import sounddevice as sd
    _HAVE_SD = True
except (ImportError, OSError) as _exc:                  # pragma: no cover
    sd = None                                           # type: ignore
    _HAVE_SD = False
    log.warning("sounddevice unavailable (%s) - text-only mode", _exc)


# ---------------------------------------------------------------------------
# resampling: one rate everywhere
# ---------------------------------------------------------------------------
def resample(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or pcm.size == 0:
        return pcm
    try:
        import soxr
        return soxr.resample(pcm.astype(np.float32), src_rate, dst_rate)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(src_rate, dst_rate)
        out = resample_poly(pcm.astype(np.float32),
                            dst_rate // g, src_rate // g)
        return out
    except Exception:                                   # noqa: BLE001
        pass
    n_out = int(round(len(pcm) * dst_rate / src_rate))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    x_old = np.linspace(0.0, 1.0, len(pcm), endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_new, x_old, pcm.astype(np.float32)).astype(np.float32)


def _to_float(pcm: np.ndarray) -> np.ndarray:
    if pcm.dtype == np.int16:
        return pcm.astype(np.float32) / 32768.0
    return pcm.astype(np.float32)


# ---------------------------------------------------------------------------
# earcons: the fast path
# ---------------------------------------------------------------------------
def make_earcon(kind: str, rate: int = config.AUDIO_RATE) -> np.ndarray:
    """Short, non-verbal cues. 60-100 ms is readable instantly; a sentence is not."""
    def tone(freq: float, dur: float, amp: float = 0.5,
             pan: float = 0.0) -> np.ndarray:
        n = int(rate * dur)
        t = np.arange(n) / rate
        wave_ = np.sin(2 * np.pi * freq * t) * amp
        env = np.minimum(1.0, np.minimum(t / 0.008,
                                        (dur - t) / 0.012).clip(min=0.0))
        wave_ *= env
        left = wave_ * (1.0 - max(0.0, pan))
        right = wave_ * (1.0 + min(0.0, pan))
        return np.stack([left, right], axis=1)

    gap = np.zeros((int(rate * 0.03), 2), dtype=np.float32)

    if kind == "stop":
        return np.concatenate([tone(440, 0.09, 0.65), gap,
                               tone(330, 0.13, 0.65)]).astype(np.float32)
    if kind == "urgent":
        return np.concatenate([tone(660, 0.05, 0.55), gap,
                               tone(880, 0.05, 0.55), gap,
                               tone(1100, 0.07, 0.55)]).astype(np.float32)
    if kind == "advisory":
        return tone(720, 0.07, 0.35).astype(np.float32)
    if kind == "ok":
        return tone(880, 0.06, 0.30).astype(np.float32)
    return tone(600, 0.06, 0.30).astype(np.float32)


# ---------------------------------------------------------------------------
# TTS backends
# ---------------------------------------------------------------------------
class TtsEngine:
    """piper -> espeak-ng -> text only. First one that works wins."""

    def __init__(self) -> None:
        self.backend = "none"
        self.rate = config.AUDIO_RATE
        self._piper_model = None
        self._piper_bin = None
        self._espeak = None
        self._cache: dict[str, tuple[np.ndarray, int]] = {}
        self._cache_order: list[str] = []
        self._detect()

    def _detect(self) -> None:
        piper = shutil.which("piper") or shutil.which("piper-tts")
        if piper:
            for name in ("en_US-lessac-medium.onnx", "en_US-glados.onnx",
                         "en_US-amy-medium.onnx", "en_US-lessac-low.onnx"):
                candidate = config.MODEL_DIR / name
                if candidate.exists():
                    self._piper_bin = piper
                    self._piper_model = candidate
                    self.backend = "piper"
                    self.rate = 22050
                    log.info("TTS: piper (%s) - natural voice", name)
                    return
            log.info("piper found but no voice model in %s "
                     "(run: bash tools/install_piper.sh)", config.MODEL_DIR)

        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if espeak:
            self._espeak = espeak
            self.backend = "espeak"
            self.rate = 22050
            log.info("TTS: %s (robotic - run tools/install_piper.sh for a "
                     "natural voice)", espeak)
            return

        log.warning("no TTS binary found - speaking to the console only")

    def synthesize(self, text: str) -> tuple[np.ndarray, int] | None:
        """Synthesize, with a cache.

        A blind user hears the same dozen phrases constantly ("Stop.", "Path
        clear."). Caching them makes a repeat instant instead of paying the
        full synthesis cost every time.
        """
        key = text.strip().lower()
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = None
        if self.backend == "piper":
            result = self._synth_piper(text)
        elif self.backend == "espeak":
            result = self._synth_espeak(text)

        if result is not None:
            self._cache[key] = result
            self._cache_order.append(key)
            while len(self._cache_order) > 40:
                self._cache.pop(self._cache_order.pop(0), None)
        return result

    def _synth_piper(self, text: str):
        try:
            proc = subprocess.run(
                [self._piper_bin, "--model", str(self._piper_model),
                 "--output-raw"],
                input=text.encode("utf-8"), capture_output=True, timeout=20)
            if proc.returncode != 0 or not proc.stdout:
                log.warning("piper failed: %s", proc.stderr[:200])
                return None
            pcm = np.frombuffer(proc.stdout, dtype=np.int16)
            return pcm, self.rate
        except Exception as exc:                        # noqa: BLE001
            log.warning("piper error: %s", exc)
            return None

    def _synth_espeak(self, text: str):
        # espeak defaults are shrill and machine-like. A female variant at a
        # lower pitch and a slightly slower rate is markedly easier to listen
        # to. This is still the fallback; piper is the real fix.
        variants = [config.ESPEAK_VOICE, "en-us"]
        for voice in variants:
            try:
                proc = subprocess.run(
                    [self._espeak, "-v", voice,
                     "-s", str(config.ESPEAK_RATE),
                     "-p", str(config.ESPEAK_PITCH),
                     "-g", "4", "--stdout", text],
                    capture_output=True, timeout=20)
                if proc.returncode != 0 or not proc.stdout:
                    continue
                with wave.open(io.BytesIO(proc.stdout), "rb") as wf:
                    rate = wf.getframerate()
                    frames = wf.readframes(wf.getnframes())
                    ch = wf.getnchannels()
                pcm = np.frombuffer(frames, dtype=np.int16)
                if ch > 1:
                    pcm = pcm.reshape(-1, ch).mean(axis=1).astype(np.int16)
                return pcm, rate
            except Exception as exc:                    # noqa: BLE001
                log.debug("espeak voice %r failed: %s", voice, exc)
        log.warning("espeak could not synthesize: %r", text[:40])
        return None


# ---------------------------------------------------------------------------
# the owner
# ---------------------------------------------------------------------------
@dataclass
class _Item:
    seq: int
    priority: int
    text: str
    earcon: str | None


class AudioOut:
    def __init__(self, volume: float = config.TTS_VOLUME,
                 mute: bool = False) -> None:
        self.volume = volume
        self.mute = mute
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = 0
        self._lock = threading.Lock()
        self._speaking = threading.Event()
        self._interrupt = threading.Event()
        self._thread: StoppableThread | None = None
        self.tts = TtsEngine()
        self.device = resolve_audio_device(config.AUDIO_OUTPUT_DEVICE, "out")
        self.last_text = ""
        self._last_spoken = ""
        self._last_spoken_at = 0.0

    # -- public ------------------------------------------------------------
    def start(self) -> None:
        self._thread = _Player(self)
        self._thread.start()

    def stop(self) -> None:
        if self._thread:
            self._thread.stop()
        self.interrupt()

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def say(self, text: str, priority: int = Priority.INFO,
            earcon: str | None = None, key: str = "") -> None:
        if not text and not earcon:
            return
        # A repeated identical string still gets spoken: React's setState
        # bailout swallowed repeats in the web app and a repeated hazard alert
        # was never re-announced.
        with self._lock:
            self._seq += 1
            seq = self._seq
        if priority <= Priority.REFLEX:
            self._drain()
        self._q.put((int(priority), seq, _Item(seq, int(priority), text, earcon)))

    def say_announcement(self, ann: Announcement) -> None:
        self.say(ann.text, ann.priority, ann.earcon, ann.key)

    def repeat_last(self) -> None:
        if self.last_text:
            self.say(self.last_text, Priority.ANSWER, earcon="ok", key="repeat")

    def interrupt(self) -> None:
        """Barge-in: stop instantly and drop anything queued below URGENT."""
        self._interrupt.set()
        if _HAVE_SD:
            try:
                sd.stop()
            except Exception:                           # noqa: BLE001
                pass
        self._drain(keep_urgent=True)

    # -- internals ---------------------------------------------------------
    def _drain(self, keep_urgent: bool = False) -> None:
        kept: list[tuple] = []
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if keep_urgent and item[0] <= Priority.URGENT:
                kept.append(item)
        for item in kept:
            self._q.put(item)

    def _play_pcm(self, pcm: np.ndarray, rate: int) -> None:
        if self.mute or not _HAVE_SD:
            return
        if pcm.dtype == np.int16:
            data = _to_float(pcm)
        else:
            data = pcm.astype(np.float32)
        data = resample(data, rate, config.AUDIO_RATE)
        if data.size == 0:
            return
        data = np.clip(data * self.volume, -1.0, 1.0)
        if data.ndim == 1:
            data = np.stack([data, data], axis=1)

        self._interrupt.clear()
        try:
            sd.play(data.astype(np.float32), config.AUDIO_RATE, blocking=False,
                    device=self.device)
            while not self._interrupt.is_set():
                stream = sd.get_stream()
                if stream is None or not stream.active:
                    break
                self._thread.sleep(0.008)               # type: ignore[union-attr]
        except Exception as exc:                        # noqa: BLE001
            log.warning("playback failed: %s", exc)
        finally:
            try:
                sd.stop()
            except Exception:                           # noqa: BLE001
                pass

    def _handle(self, item: _Item) -> None:
        self._speaking.set()
        try:
            if item.earcon:
                self._play_pcm(make_earcon(item.earcon), config.AUDIO_RATE)
                if self._interrupt.is_set():
                    return
            if not item.text:
                return
            log.info("SPEAK: %s", item.text)
            self.last_text = item.text
            result = self.tts.synthesize(item.text)
            if result is None:
                # text-only mode: still record it so --verbose runs are useful
                return
            pcm, rate = result
            self._play_pcm(pcm, rate)
        finally:
            self._speaking.clear()


class _Player(StoppableThread):
    def __init__(self, out: AudioOut) -> None:
        super().__init__("audio-out")
        self.out = out

    def _run(self) -> None:
        while not self.stopped:
            try:
                _prio, _seq, item = self.out._q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.out._handle(item)
            except Exception as exc:                    # noqa: BLE001
                log.warning("audio item failed: %s", exc)
