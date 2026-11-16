# Deploying Sahayak Drishti on the Raspberry Pi 4

Everything here is ordered so that **each step can fail on its own and you know
immediately which part is broken.** Do not skip to the end — steps 6 and 7 exist
to prove the sensors and the audio work before you try the full system.

Estimated time: 60–90 minutes on a fresh Pi, mostly downloading.

---

## 1. What you need

| Part | Notes |
|---|---|
| Raspberry Pi 4B (4 GB) | 64-bit Raspberry Pi OS Bookworm |
| Pi Camera Module (OV5647 / v1.3) | CSI ribbon, blue side toward the USB ports |
| USB headset **with microphone** | Jabra Evolve2 30 SE or similar |
| Arduino Uno | USB cable to the Pi |
| **Grove Ultrasonic Ranger V2.0** | 3 wires: GND, 5V, SIG. Not an HC-SR04 |
| 32 GB SD card | class 10 |

That is the whole build. No GPS, no accelerometer, no motor.

> ⚠️ **The sensor is a Grove Ultrasonic Ranger V2.0, not an HC-SR04.** They are
> wired differently and the code is different. The Ranger has pins labelled
> `GND VCC NC SIG` — trigger and echo share the single SIG wire. An HC-SR04
> has separate TRIG and ECHO pins and will not work with this sketch.

---

## 2. Flash the Arduino

1. Open `arduino/smartcane_sensor_hub/smartcane_sensor_hub.ino` in the Arduino IDE.
2. **No libraries to install** — it uses only what ships with the IDE.
3. Upload to the Uno.

**Wiring — the Grove Ranger needs 3 wires, not 4:**

| Grove wire | Board label | Arduino pin |
|---|---|---|
| **Black** | GND | GND (POWER header) |
| **Red** | VCC | **5V** (POWER header — not RESET, not 3V3) |
| **White** | NC | *leave unconnected* |
| **Yellow** | SIG | **D7** (DIGITAL header) |

D13 is the Uno's own onboard LED. It lights whenever something is closer than
60 cm — no wiring needed, and it is the quickest way to see the sensor working.

The module needs **at least 60 ms between pings**; the sketch measures every
80 ms and streams to the Pi at 20 Hz.

---

## 3. Pi OS and hardware enablement

```bash
sudo raspi-config
#  3 Interface Options -> I1 Camera  -> Enable
#  3 Interface Options -> I2 SSH     -> Enable (so you can work remotely)
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

**Camera — the most common failure point.** Bookworm uses libcamera, and the
CSI camera is *not* exposed as `/dev/video0` by default. Our `camera.py` handles
this by using `picamera2` first, so install it:

```bash
sudo apt install -y python3-picamera2 python3-libcamera
```

Check it:

```bash
libcamera-hello -t 3000        # should show a preview for 3 seconds
```

If `libcamera-hello` works but our code says "camera backend: mock", tell us —
that is a picamera2/venv issue, not a hardware one.

**Audio:**

```bash
sudo apt install -y alsa-utils espeak-ng
aplay -l            # note the card number of your headset
arecord -l          # the mic must appear here too
```

Test both directions:

```bash
speaker-test -t sine -f 440 -l 1     # do you hear a tone?
arecord -f cd -d 3 /tmp/t.wav && aplay /tmp/t.wav    # do you hear yourself?
```

Then let the software check the microphone for you:

```bash
python -m smartcane --test-mic
```

It records 4 seconds, prints a peak level, and says `MIC OK`, `MIC VERY
QUIET` or `MIC DEAD`. Use it before blaming the recogniser.

> The Pi 4 3.5 mm jack is a **combo** jack: it takes TRRS headsets (mic + stereo
> out). If `arecord -l` shows no capture device, your headset is TRS (no mic) and
> you need a USB sound card.

---

## 4. Get the code

```bash
cd ~
git clone https://github.com/AdhikaShahane/Smartcane.git
cd Smartcane
```

The Vosk model and YOLO weights are already in `models/` (about 74 MB), so this
clone is the only download you need.

---

## 5. Python environment

```bash
python3 -m venv ~/cane
source ~/cane/bin/activate
pip install --upgrade pip
pip install -r requirements-pi.txt
```

`ultralytics` pulls in PyTorch, which is large (~800 MB). On a 4 GB Pi this
works but is slow to install — let it run.

Add the system packages to the venv so `picamera2` is visible:

```bash
echo "/usr/lib/python3/dist-packages" > ~/cane/lib/python3*/site-packages/system.pth
```

**TTS (optional but strongly recommended):**

```bash
pip install piper-tts
mkdir -p models && cd models
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
cd ..
```

If piper is not installed the system falls back to `espeak-ng`, then to printing
to the console. It never crashes because of a missing voice.

---

## 6. Verify the sensor link FIRST

This is the step that saves hours. With the Arduino plugged in:

```bash
cd ~/Smartcane
source ~/cane/bin/activate
python -m smartcane --dump-serial
```

You should see lines like:

```
RAW[9] b'\xaa\x55\x01\x04\x12\xa4\x00\x00\x6d'
```

- **Nothing at all** → wrong port or bad cable. Check `ls /dev/ttyACM*` and
  `ls /dev/ttyUSB*`, then set `SMARTCANE_SERIAL=/dev/ttyACM0`.
- **Garbage that never stops** → baud mismatch. Confirm the sketch uses 115200.
- **`b'123\r\n'` style text** → your Arduino is running different firmware. That
  is fine: `link.py` auto-detects CSV, `dist:123`, and JSON formats too.

Wave your hand in front of the sensor and confirm the numbers move.

---

## 7. Run the whole system

**Step A — no hardware at all (proves the software):**

```bash
python -m smartcane --mock --no-mic --mute --duration 15 --verbose
```

You should see the state walk `clear → watch → advisory → urgent → stop` and
lines like `SPEAK: Obstacle ahead, about 1.5 metres. Walk straight 1 step.`

**Step B — real camera, no speech:**

```bash
python -m smartcane --no-mic --verbose
```

Watch for `camera backend: picamera2` and `detector: yolov8n.pt (pytorch)`.

**Step C — full system:**

```bash
python -m smartcane --verbose
```

Then speak: *"what is ahead"*, *"turn left"*, *"stop"*, *"how many steps"*.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `camera backend: mock` | CSI camera not enabled / picamera2 missing | §3; run `libcamera-hello` |
| `no YOLO model found` | `models/` missing | re-clone, or check `ls models/` |
| `no Arduino serial port found` | cable / permissions | `sudo usermod -aG dialout $USER`, then log out and in |
| `cannot open microphone` | headset is TRS not TRRS | use a USB sound card |
| Recognises nothing | Vosk grammar too tight, or mic gain | see below |
| Speech is chipmunk/slow | sample-rate mismatch | `pip install soxr` — this is the classic 22050→48000 bug |
| Two sentences overlap | two TTS engines | only one process may own the speaker; check nothing else is running |
| Very slow (1–2 FPS) | PyTorch at 640 | run `python tools/optimize_model.py` (§9) |

**If it recognises nothing**, print what Vosk actually hears:

```bash
python - <<'PY'
import json, queue, sounddevice as sd
from vosk import Model, KaldiRecognizer
m = Model("models/vosk-model-small-en-us-0.15")
r = KaldiRecognizer(m, 16000)
q = queue.Queue()
with sd.RawInputStream(samplerate=16000, blocksize=800, dtype="int16",
                       channels=1, callback=lambda d,f,t,s: q.put(bytes(d))):
    print("speak now...")
    while True:
        if r.AcceptWaveform(q.get()):
            print(json.loads(r.Result()).get("text",""))
PY
```

If that prints nothing either, it is a microphone problem, not our code.

---

## 9. Speed up detection (optional, big win)

```bash
python tools/optimize_model.py
```

This exports `yolov8n.pt` to ncnn/ONNX at 320×320. `vision.py` prefers
`models/yolov8n_ncnn_model/` automatically on the next run. Measured on a Pi 4,
ncnn at 320 is roughly 4× faster than PyTorch at 640.

---

## 10. If something fails, send back exactly this

```bash
python -m smartcane --verbose 2>&1 | tee ~/cane-log.txt
uname -a >> ~/cane-log.txt
libcamera-hello --list-cameras >> ~/cane-log.txt
aplay -l >> ~/cane-log.txt
arecord -l >> ~/cane-log.txt
ls /dev/ttyACM* /dev/ttyUSB* >> ~/cane-log.txt 2>&1
```

That file is enough to diagnose almost anything without guessing.
