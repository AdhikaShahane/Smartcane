# Sahayak Drishti â€” AI Smart Cane

An assistive navigation system for visually impaired users. A Raspberry Pi 4
runs the perception and speech stack; an Arduino Uno streams ultrasonic
distance to it over serial.

**Current hardware build:** Pi Camera Module, USB headset (mic + headphones),
and an Arduino Uno with a **Grove Ultrasonic Ranger V2.0**. Nothing else â€” no
GPS, no accelerometer, no motor. The code still runs correctly if any of the
three is missing, and says so.

```
   Arduino Uno  (sensor only)      Raspberry Pi 4
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚ Grove Ranger  20 Hz  â”‚      â”‚ REFLEX   distance -> earcon  â”‚
  â”‚ one-wire trig/echo   â”‚  USB â”‚ VISION   YOLO@320 + tracker  â”‚
  â”‚ median-of-3          â”‚ â”€â”€â”€â–º â”‚ DIALOGUE Vosk + grammar      â”‚
  â”‚ LED13 when < 60 cm   â”‚      â”‚ ARBITER  one speaker owner   â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜      â”‚          piper / espeak      â”‚
                                â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
        Camera   â”€â”€ CSI â”€â”€â”€â”€â”€â”€â”€â–º
        Headset  â”€â”€ USB â”€â”€â”€â”€â”€â”€â”€â–º
```

## What it does

- **Warns of obstacles** using ultrasonic distance, with stereo earcons that
  convey direction and proximity faster than a sentence can.
- **Understands the scene, not just objects.** ADE20K semantic segmentation
  labels every pixel, including **floor, sidewalk, path, road, door, wall,
  railing, column, stairs and step** â€” the classes a blind pedestrian actually
  collides with, none of which exist in COCO.
- **Measures free space** instead of guessing it. Walkable pixels are counted
  in the left, centre and right thirds of the near field, so "turn left" is
  based on a measurement, not on the absence of a detection.
- **Names what it can see.** Ask *"what is in front of me"* and it lists up to
  three, nearest first: *"I can see a person right in front of you, about a
  metre and a half away, and a chair on your left, about two metres away."*
- **Guides in steps, with turns**: *"The way ahead is blocked. Turn left, then
  walk two steps."* or *"The path ahead is clear. Walk straight three steps,
  then ask me again."*
- **Answers questions hands-free** â€” no push-to-talk: *"what is in front of
  me"*, *"how many steps"*, *"is it safe"*, *"turn left"*, *"stop"*.
- **Interrupts itself** when you start speaking (barge-in).

### What it still cannot see

ADE20K has no **curb** and no **pole** class. Both still appear as
non-walkable surface, so the cane treats them as obstacles â€” it just cannot
name them. There is also no class for a pothole or a wet floor.

A monocular camera cannot measure real depth either: distance is estimated
from a known object height, so a child, a low chair or a tilted camera all
bias it. The ultrasonic corrects this in the centre corridor only.

If the ADE20K model is missing, the cane falls back to the legacy COCO
detector and **says so in the log**: doors, walls and stairs will not be
recognised in that mode.

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
  __main__.py    entry point, threads, command dispatch, conversation context
  config.py      every pin, port and threshold in one file
  link.py        Arduino serial - auto-detects baud + binary/JSON/CSV/key:value
  camera.py      cv2 -> picamera2 -> network discovery -> synthetic fallback
  segmentation.py  ADE20K semantic model -> obstacle boxes + measured free space
  vision.py      tracker, zones with hysteresis, closing speed, time-to-collision
  risk.py        three-level risk engine (low / medium / critical)
  guidance.py    decision layer: step maths, turns, bypass, STOP explanations
  asr.py         always-listening Vosk, restricted grammar, pre-roll buffer
  intent.py      rapidfuzz command matching (no LLM: too slow on a Pi 4)
  audio_out.py   single-owner speaker, priority queue, earcons, barge-in
arduino/smartcane_sensor_hub/   sensor hub + hardware reflex
tools/fetch_model.py            download an ADE20K segmentation checkpoint
tools/train_segmentation.py     train one on ADE20K if none is published
tools/optimize_model.py         export to ncnn/ONNX (about 4x faster)
tools/calibrate_stride.py       measure the user's own step length
tools/benchmark.py              CPU-side decision-layer timing
tests/smoke_test.py             hardware-free checks
tests/scenarios.py              the twelve navigation scenarios
docs/DEPLOY.md                  the guide to follow on the Pi
docs/DEMO.md                    the demo script and contingencies
```

## How it decides

Risk is graded on evidence, not on object category. A car is not critical
because it is a car; a chair is not harmless because it is furniture.

| Level | Triggered by | Behaviour |
|---|---|---|
| **LOW** | visible, not in the corridor, or far away | named on request, never interrupts |
| **MEDIUM** | in the walking corridor, or closing with TTC â‰¤ 4 s | warns and suggests a side |
| **CRITICAL** | within 0.8 m in the path, TTC â‰¤ 1.5 s, or blocking the view with no distance | `Stop!` with object, distance and reason |

Inputs: estimated distance, closing speed, time to collision, corridor overlap,
frame-filling, and detection confidence. A weak detection is downgraded and
spoken as "an unidentified obstacle" rather than trusted or invented.

The ultrasonic is graded too, because it measures distance directly. A close
reading with no matching camera object is still critical. Measured free space
is graded as well: if the walkable surface ahead disappears, something is
there whether or not the model can name it.

## Voice commands

| Ask | Get |
|---|---|
| "what is in front of me" | names up to three objects with side and distance |
| "what objects are around me" | all three zones |
| "how many steps" | step count, plus a turn if the way is blocked |
| "how do I reach it" | steps to the object just described |
| "guide me around it" | which side is clearer, and how many steps |
| "which direction should I turn" | the side with more room |
| "what is on my left" / "right" | what is detected there |
| "have I passed it" | whether the object is still in view |
| "is it safe" | clear / caution / not safe, with the reason |
| "stop" | immediate silence |

Stride length is calibrated per user, not assumed:
`python tools/calibrate_stride.py`

## Measured performance (Raspberry Pi 4)

| Stage | Latency |
|---|---|
| Ultrasonic reading â†’ earcon | ~60 ms |
| Detection (ncnn @320) | 53â€“133 ms |
| Detection (PyTorch @320, no export) | ~300 ms |
| Voice answer end to end | 500â€“900 ms |

The previous version took 1.5â€“2.5 s to warn and 2.5â€“4 s to answer, because
inference ran on PyTorch at 640 px and speech went through a cloud API.

## Legacy code

`src/`, `server.ts`, `package.json` and the rest of the React app are the earlier
web prototype. They are **not part of the device** and are not used by the demo.
They contained no local object detector at all â€” the "vision" was a Gemini cloud
call per frame. Kept for reference only. `docs/legacy_detect_webcam.py` is the
original vision engine whose zone and hysteresis logic was ported into
`vision.py`.

## Requirements

See `requirements-pi.txt`. Optional but recommended: `soxr` (clean resampling),
`piper-tts` (better voice), `silero-vad` (better noise handling).

## License

Student project. Not certified as a medical or safety device.
