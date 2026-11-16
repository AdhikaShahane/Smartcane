# Sahayak Drishti — AI Smart Cane

An assistive navigation system for visually impaired users. A Raspberry Pi 4
runs the perception and speech stack; an Arduino Uno streams ultrasonic
distance to it over serial.

**Current hardware build:** Pi Camera Module, USB headset (mic + headphones),
and an Arduino Uno with an HC-SR04. Nothing else — no GPS, no accelerometer, no
motor. The code still runs correctly if any of the three is missing, and says so.

```
   Arduino Uno  (sensor only)      Raspberry Pi 4
  ┌──────────────────────┐      ┌──────────────────────────────┐
  │ HC-SR04   20 Hz      │      │ REFLEX   distance -> earcon  │
  │ median-of-3          │  USB │ VISION   YOLO@320 + tracker  │
  │ LED13 when < 60 cm   │ ───► │ DIALOGUE Vosk + grammar      │
  └──────────────────────┘      │ ARBITER  one speaker owner   │
                                │          piper / espeak      │
        Camera   ── CSI ───────►│                              │
        Headset  ── USB ───────►│                              │
                                └──────────────────────────────┘
```

## What it does

- **Warns of obstacles** using ultrasonic distance, with stereo earcons that
  convey direction and proximity faster than a sentence can.
- **Identifies what is ahead** with a quantised detector and describes it in one
  short sentence, only when the situation changes.
- **Guides in steps**: *"Chair ahead, about 1.5 metres. Walk straight 1 step."*
- **Answers questions hands-free** — no push-to-talk: *"what is ahead"*,
  *"how many steps"*, *"is it safe"*, *"turn left"*, *"stop"*.
- **Interrupts itself** when you start speaking (barge-in).

## Design rules

1. **Nothing in the safety path depends on a model, a network, or a sentence.**
   The ultrasonic reports 20 times a second and drives the earcon directly; the
   detector and the recogniser are never in that path.
2. **One owner of the speaker.** Every utterance goes through a single priority
   queue. Two threads calling TTS at once was the cause of the garbled audio in
   the previous version.
3. **Announce on transitions, not on a timer.** Repeated states are silence.
4. **Never claim more path than has been verified.** Step counts are capped by
   the sensor horizon minus a stopping margin.
5. **Never invent data.** If a sensor is missing or a value cannot be read, it
   says so. The previous version answered "the person is on your right"
   regardless of what the camera saw.

## Quick start

```bash
# no hardware needed - proves the software end to end
python -m smartcane --mock --no-mic --mute --duration 15 --verbose

# smoke tests (no hardware, no deps beyond numpy)
python tests/smoke_test.py

# see what the Arduino is sending
python -m smartcane --dump-serial

# full system
python -m smartcane --verbose
```

Full installation, wiring and troubleshooting: **[docs/DEPLOY.md](docs/DEPLOY.md)**

## Layout

```
smartcane/
  __main__.py    entry point, threads, command dispatch
  config.py      every pin, port and threshold in one file
  link.py        Arduino serial - auto-detects binary/JSON/CSV/key:value
  camera.py      cv2 -> picamera2 -> synthetic fallback
  vision.py      YOLO@320, zones with hysteresis, tracker, distance
  guidance.py    state machine, step maths, announcement policy
  asr.py         always-listening Vosk, restricted grammar, pre-roll buffer
  intent.py      rapidfuzz command matching (no LLM: too slow on a Pi 4)
  audio_out.py   single-owner speaker, priority queue, earcons, barge-in
arduino/smartcane_sensor_hub/   sensor hub + hardware reflex
tools/optimize_model.py         export to ncnn/ONNX (about 4x faster)
tests/smoke_test.py             hardware-free checks
docs/DEPLOY.md                  the guide to follow on the Pi
```

## Measured performance (Raspberry Pi 4)

| Stage | Latency |
|---|---|
| Ultrasonic reading → earcon | ~60 ms |
| Detection (ncnn @320) | 53–133 ms |
| Detection (PyTorch @320, no export) | ~300 ms |
| Voice answer end to end | 500–900 ms |

The previous version took 1.5–2.5 s to warn and 2.5–4 s to answer, because
inference ran on PyTorch at 640 px and speech went through a cloud API.

## Legacy code

`src/`, `server.ts`, `package.json` and the rest of the React app are the earlier
web prototype. They are **not part of the device** and are not used by the demo.
They contained no local object detector at all — the "vision" was a Gemini cloud
call per frame. Kept for reference only. `docs/legacy_detect_webcam.py` is the
original vision engine whose zone and hysteresis logic was ported into
`vision.py`.

## Requirements

See `requirements-pi.txt`. Optional but recommended: `soxr` (clean resampling),
`piper-tts` (better voice), `silero-vad` (better noise handling).

## License

Student project. Not certified as a medical or safety device.
