"""Always-listening speech input.

The user's requirement: no push-to-talk. They speak whenever they want and the
cane must hear it. That means three problems have to be solved, and each one is
handled explicitly here.

1. **Never clip the first syllable.** The capture stream is opened once at boot
   and a PREROLL_SEC ring buffer is kept. When the VAD fires, the buffered audio
   *before* the trigger is fed to the recogniser first. The original code called
   `adjust_for_ambient_noise(0.5)` and reopened the microphone before every
   command, which guaranteed the first phoneme was lost.

2. **Restricted vocabulary.** The recogniser is given the closed command
   grammar, not free-form English. This is the single biggest accuracy win for
   short commands and it also cuts false triggers from background conversation.

3. **Barge-in.** Speech detected while the cane is talking interrupts playback.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

from . import config, intent
from .util import StoppableThread, get_logger

log = get_logger("asr")

try:
    import sounddevice as sd
    _HAVE_SD = True
except (ImportError, OSError):                          # pragma: no cover
    sd = None                                           # type: ignore
    _HAVE_SD = False

try:
    from vosk import KaldiRecognizer, Model, SetLogLevel
    _HAVE_VOSK = True
except ImportError:                                     # pragma: no cover
    KaldiRecognizer = Model = None                      # type: ignore
    _HAVE_VOSK = False


@dataclass
class SpeechEvent:
    text: str
    final: bool
    confidence: float = 0.0
    at: float = 0.0


class EnergyVad:
    """Adaptive-energy VAD.

    Deliberately dependency-free: it has to work on the Pi on day one. Silero is
    better in noise and is used automatically when installed.
    """

    def __init__(self, frame_len: int) -> None:
        self.frame_len = frame_len
        self.noise_floor = 0.004
        self.speech_frames = 0
        self.trigger_ratio = 2.6

    def is_speech(self, frame: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)) + 1e-9)
        if rms < self.noise_floor * 1.4:
            # quiet: adapt the floor downward slowly
            self.noise_floor = 0.995 * self.noise_floor + 0.005 * rms
        elif rms < self.noise_floor * self.trigger_ratio:
            self.noise_floor = 0.999 * self.noise_floor + 0.001 * rms
        speech = rms > self.noise_floor * self.trigger_ratio
        self.speech_frames = self.speech_frames + 1 if speech else 0
        return self.speech_frames >= 2          # 2 frames = ~64 ms of evidence


class SileroVad:
    def __init__(self) -> None:
        import torch
        from silero_vad import load_silero_vad
        self._torch = torch
        self.model = load_silero_vad()
        self.model.eval()

    def is_speech(self, frame: np.ndarray) -> bool:
        tensor = self._torch.from_numpy(frame.astype(np.float32))
        with self._torch.no_grad():
            return float(self.model(tensor, 16000).item()) > 0.5


class Asr:
    def __init__(self, on_event, on_speech_start=None, mock: bool = False
                 ) -> None:
        self.on_event = on_event
        self.on_speech_start = on_speech_start
        self.mock = mock
        self.enabled = False
        self._rec = None
        self._model = None
        self._stream = None
        self._audio_q: queue.Queue = queue.Queue(maxsize=64)
        self._preroll: deque = deque(maxlen=max(
            1, int(config.PREROLL_SEC * config.MIC_RATE / config.MIC_BLOCK)))
        self._vad = None
        self._thread: StoppableThread | None = None
        self._speaking = False
        self._silence = 0.0
        self._started_at = 0.0

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self.mock:
            self._thread = _MockAsr(self)
            self._thread.start()
            log.info("ASR: mock (type commands in this terminal)")
            return
        if not _HAVE_VOSK:
            log.error("vosk not installed - pip install vosk")
            return
        if not _HAVE_SD:
            log.error("sounddevice not available - no microphone")
            return
        if not config.VOSK_MODEL.exists():
            log.error("Vosk model missing at %s", config.VOSK_MODEL)
            return

        SetLogLevel(-1)
        log.info("loading Vosk model from %s", config.VOSK_MODEL)
        self._model = Model(str(config.VOSK_MODEL))
        grammar = json.dumps(intent.grammar_phrases())
        self._rec = KaldiRecognizer(self._model, config.MIC_RATE, grammar)
        self._rec.SetWords(False)
        self._vad = self._make_vad()

        try:
            self._stream = sd.RawInputStream(
                samplerate=config.MIC_RATE, blocksize=config.MIC_BLOCK,
                dtype="int16", channels=1, callback=self._cb)
            self._stream.start()
        except Exception as exc:                        # noqa: BLE001
            log.error("cannot open microphone: %s", exc)
            return

        self.enabled = True
        self._thread = _Process(self)
        self._thread.start()
        log.info("ASR listening (grammar: %d phrases)",
                 len(intent.grammar_phrases()))

    def _make_vad(self):
        try:
            vad = SileroVad()
            log.info("VAD: Silero")
            return vad
        except Exception as exc:                        # noqa: BLE001
            log.info("VAD: energy (Silero unavailable: %s)", exc)
            return EnergyVad(config.MIC_BLOCK)

    def stop(self) -> None:
        if self._thread:
            self._thread.stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:                           # noqa: BLE001
                pass

    # -- capture callback (runs on the audio thread: keep it trivial) ------
    def _cb(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("mic status: %s", status)
        try:
            self._audio_q.put_nowait(bytes(indata))
        except queue.Full:
            pass                                    # drop rather than block

    # -- processing --------------------------------------------------------
    def feed(self, chunk: bytes) -> None:
        frame = np.frombuffer(chunk, dtype=np.int16)

        # keep the ring buffer full regardless of VAD state
        self._preroll.append(frame)

        speech = False
        try:
            speech = self._vad.is_speech(frame)
        except Exception:                               # noqa: BLE001
            speech = True

        now = time.monotonic()
        if speech and not self._speaking:
            self._speaking = True
            self._started_at = now
            self._silence = 0.0
            if self.on_speech_start:
                try:
                    self.on_speech_start()
                except Exception:                       # noqa: BLE001
                    pass
            # replay the pre-roll so the first phoneme is not lost
            for buffered in self._preroll:
                self._accept(buffered.tobytes())
            return

        if self._speaking:
            self._accept(chunk)
            if speech:
                self._silence = 0.0
            else:
                self._silence += config.MIC_BLOCK / config.MIC_RATE
                if self._silence >= config.VAD_END_SILENCE:
                    self._finish()

    def _accept(self, chunk: bytes) -> None:
        if self._rec is None:
            return
        if self._rec.AcceptWaveform(chunk):
            self._emit_final()
        else:
            self._emit_partial()

    def _emit_partial(self) -> None:
        try:
            partial = json.loads(self._rec.PartialResult()).get("partial", "")
        except Exception:                               # noqa: BLE001
            return
        if partial:
            self.on_event(SpeechEvent(partial, final=False,
                                      at=time.monotonic()))

    def _emit_final(self) -> None:
        try:
            result = json.loads(self._rec.Result())
        except Exception:                               # noqa: BLE001
            return
        text = (result.get("text") or "").strip()
        if text:
            self.on_event(SpeechEvent(text, final=True,
                                      at=time.monotonic()))

    def _finish(self) -> None:
        self._speaking = False
        self._silence = 0.0
        if self._rec is not None:
            # force a final hypothesis for the utterance just ended
            try:
                self._emit_final()
            finally:
                self._rec.Reset()


class _Process(StoppableThread):
    def __init__(self, asr: Asr) -> None:
        super().__init__("asr")
        self.asr = asr

    def _run(self) -> None:
        while not self.stopped:
            try:
                chunk = self.asr._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.asr.feed(chunk)
            except Exception as exc:                    # noqa: BLE001
                log.warning("asr frame error: %s", exc)


class _MockAsr(StoppableThread):
    """Reads commands from stdin so the whole pipeline runs with no hardware."""

    def __init__(self, asr: Asr) -> None:
        super().__init__("asr-mock")
        self.asr = asr

    def _run(self) -> None:
        log.info("mock ASR: type a command and press Enter "
                 "(e.g. 'what is ahead')")
        while not self.stopped:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                return
            text = line.strip()
            if not text:
                continue
            if self.asr.on_speech_start:
                try:
                    self.asr.on_speech_start()
                except Exception:                       # noqa: BLE001
                    pass
            self.asr.on_event(SpeechEvent(text, final=True,
                                          at=time.monotonic()))
