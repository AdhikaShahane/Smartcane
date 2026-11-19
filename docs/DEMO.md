# Demo script

Fifteen minutes of preparation, five minutes of demo, and a plan for when
something does not cooperate.

---

## 1. Before you start (do this in order)

```bash
cd ~/Smartcane
source ~/cane/bin/activate
git pull
bash tools/healthcheck.sh
```

Read the PASS/FAIL table. You want at least:

| Line | Must say |
|---|---|
| unit tests | `[PASS]` |
| audio devices | `[PASS] microphone device found` |
| microphone | `[PASS] microphone hears you` |
| Arduino | `[PASS] Arduino serial device present` |
| camera | `[PASS]` |
| speech output | `[PASS] natural voice (piper) installed` |

Anything that FAILs prints its own fix on the next line. Fix what you can;
note what you cannot and use the fallbacks below.

**Then start the phone camera** (IP Webcam app Ã¢â€ â€™ Start server) and confirm the
Pi is on the same Wi-Fi.

**Then run once to warm everything up** Ã¢â‚¬â€ the first run loads YOLO and Vosk,
which takes about 12 seconds. Do this *before* the audience is watching:

```bash
python -m smartcane --camera scan --verbose
```
Wait for `ready - ... vision=on`, then `Ctrl+C`.

---

## 2. The demo, in order

### Opening (say this)

> "This is Sahayak Drishti, an AI smart cane for visually impaired users. The
> Raspberry Pi is the brain Ã¢â‚¬â€ it sees with a camera, senses distance with an
> ultrasonic sensor, and talks. The Arduino handles the ultrasonic because
> timing-critical sensing belongs on a microcontroller, not on an operating
> system."

### Step 1 Ã¢â‚¬â€ obstacle detection (30 s)

```bash
python -m smartcane --verbose
```

Wave a hand in front of the ultrasonic sensor.

> "It announces only when the situation changes, not continuously. Watch the
> log: `state=watch` means it is tracking silently, `advisory` means it has
> started guiding."

Point at the log line `serial format detected: kv` Ã¢â‚¬â€ that is the Pi reading the
Arduino.

### Step 2 Ã¢â‚¬â€ object recognition (60 s)

Hold a person, chair or bottle in front of the phone camera.

> "YOLO runs on the Pi at 320 pixels Ã¢â‚¬â€ that is the sweet spot. At 640 it drops
> to 3 frames per second; at 320 we get 8 to 12, which is what makes tracking
> usable."

Show the log line `>> Person ahead, about a metre and a half. Walk straight one step.`

### Step 3 Ã¢â‚¬â€ voice commands (60 s)

Say clearly: **"what is ahead"** Ã¢â‚¬Â¦ **"how many steps"** Ã¢â‚¬Â¦ **"stop"**.

> "The vocabulary is deliberately restricted to about seventy phrases. That
> turns speech recognition from 'transcribe English' into 'classify seventy
> things', which is far more reliable and much faster on a Pi."

If asked about false triggers:

> "Bare direction words are rejected on purpose. 'left' on its own is a
> preposition Ã¢â‚¬â€ you would trigger it in normal conversation. Only 'turn left'
> or 'move left' count. There are seventeen automated tests for exactly this."

### Step 4 Ã¢â‚¬â€ the numbers (30 s)

> "The old version took 1.5 to 2.5 seconds to warn and 2.5 to 4 seconds to
> answer, because inference ran on PyTorch at 640 pixels and speech went
> through a cloud API. Now the ultrasonic-to-earcon path is about 60 ms, and a
> spoken answer is 500 to 900 ms."

---

## 3. If something fails on the day

| Symptom | Do this | Say this |
|---|---|---|
| **No microphone** | The system prints `Falling back to KEYBOARD commands`. Just type `what is ahead` and press Enter | "Voice input needs a USB microphone; the headset we have is output-only on the 3.5 mm jack. The command layer is identical Ã¢â‚¬â€ let me demonstrate by typing." |
| **Camera not found** | `python -m smartcane --camera scan --verbose` | "It discovers the phone on the network automatically." |
| **Detection slow** | Nothing to do live Ã¢â‚¬â€ mention it | "We are still on PyTorch weights; the ncnn export is a one-command optimisation that triples the frame rate." |
| **Arduino not found** | `ls /dev/ttyACM*` Ã¢â‚¬â€ reseat the USB | "The ultrasonic is on a separate microcontroller; without it the camera still drives detection." |
| **Everything fails** | `python -m smartcane --mock --verbose` | "This is the full pipeline against synthetic data Ã¢â‚¬â€ the same code path, no hardware." |
| **Speech sounds robotic** | It is espeak Ã¢â‚¬â€ Piper did not install | "The neural voice needs a 60 MB model download; espeak is the offline fallback." |

**`--mock` is your safety net.** It runs the entire state machine, guidance and
speech with no hardware at all. It has never failed.

---

## 4. Questions they will ask

**"How accurate is it?"**
> "We use ADE20K semantic segmentation rather than COCO detection, because
> COCO has no door, wall, floor, stairs or sidewalk. Segmentation labels every
> pixel as walkable or not, so the cane measures free space instead of only
> naming objects. The ultrasonic is still the safety layer â€” it needs no model
> at all and cannot be fooled by an unusual object."

**"Why not just use a phone app?"**
> "A phone needs a hand and gives no continuous feedback. This is hands-free,
> head-mounted audio, and works with the cane the user already trusts."

**"What happens if the Pi crashes?"**
> "The Arduino keeps sensing independently and drives the onboard LED. The
> architecture keeps the timing-critical path off the operating system."

**"Is it safe to rely on?"**
> "No, and we do not claim it is. It is a student prototype. The safety
> decisions are conservative: if a reading is corrupt or out of range we
> discard it rather than guess, and we never tell the user a path is clear
> when the sensor is not responding."

**"How fast is it really?"**
> Show the log. Every line has a timestamp. `infer=280ms` is the honest number.

---

## 5. One-minute version

If you get one minute:

```bash
python -m smartcane --mock --verbose
```

> "Obstacle detection, step-by-step guidance and speech, running the same code
> that drives the hardware. The state machine moves clear Ã¢â€ â€™ watch Ã¢â€ â€™ advisory Ã¢â€ â€™
> urgent Ã¢â€ â€™ stop, and it only speaks when the state changes."

That demonstrates the entire decision layer without touching a cable.

## SOS button — demo step

Run with the demo flag so the alarm narrates the finished behaviour:

```bash
python -m smartcane --camera "http://<phone-ip>:8080/video" --mic 1 --demo
```

Startup prints a banner saying the alarm is simulated. Then either press the
button (GPIO 17 to GND) or say **"sos"**.

What the audience hears, once per press:

> "Emergency! S O S button pressed. Your live location has been shared."

Press again to cancel - it says "Emergency alarm cancelled." and goes quiet.

Say it once, then explain the honest position:

> "This build has no GPS module, so this is a simulation of the alert flow.
> The logic and the wiring are real; the coordinates are the part that is
> still missing. Adding a NEO-6M module would make the same button send a
> real position, and we have already left the message honest for the case
> where no fix is available."

Without `--demo` the same button says:

> "Emergency! S O S button pressed. I need help."

It makes no claim about location either way, so nothing said in either mode is
false. To repeat the alarm every few seconds, set
`SMARTCANE_SOS_REPEAT=6` - it is off by default.

If a judge asks which is which: **`--demo` simulates, the default does not.**
