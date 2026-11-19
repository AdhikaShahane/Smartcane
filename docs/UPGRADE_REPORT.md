# SmartCane upgrade — risk engine, navigation and explained STOPs

Implementation report for the intelligent navigation upgrade. Everything
below was run; the numbers are measured, not estimated.

Commit: `e28c058`

---

## 1. Problems identified

| # | Problem | Evidence |
|---|---|---|
| 1 | Objects were named but never graded. A chair 3 m to the side and a chair 50 cm in the path produced the same class of response. | `guidance.assess()` bucketed purely on distance thresholds |
| 2 | A person at 2 m filled half the frame and was classed as a stop. | found by scenario 4 during this work |
| 3 | "How many steps" gave a count but never a direction, so a blocked corridor produced no usable guidance. | `steps_to_walk()` had no turn branch |
| 4 | `best_direction()` existed but the advisory phrase still hardcoded "Step to your right". | `_phrase()` |
| 5 | STOP was a bare `"Stop."` — no object, no distance, no reason. | `_phrase()` |
| 6 | Step length was the hardcoded `STEP_DEFAULT = 0.65 m`; the Weinberg gait function was written but never called. | `Guidance.__init__` |
| 7 | "What is in front of me" reported only the single nearest corridor object, so a chair beside a person was never mentioned. | `describe()` |
| 8 | No conversation memory: a follow-up question started from scratch. | no context store |
| 9 | Intent classification cost 9.15 ms per utterance, ~30 ms on a Pi 4. | `tools/benchmark.py` |

## 2. Root causes

1. **Risk was a distance threshold, not a judgement.** `assess()` compared
   `dist_m` against four constants. Motion, trajectory and time-to-collision
   were not inputs at all, because the tracker discarded the per-frame
   distance it would have needed to compute them.
2. **Frame-filling double-counted with distance.** Both rules could fire, and
   the size rule fired first, so any close object became critical regardless
   of how far away it actually was.
3. **Direction was computed but not wired in.** `best_direction()` was added
   for bypass guidance and never used by the announcement path.
4. **No motion state reached the decision layer.** `TrackedObject.history`
   stored `(x, y, box_h, time)` — distance was recomputed per frame and
   thrown away, so closing speed was unrecoverable.
5. **The planner had no object-level API.** Guidance only knew about a single
   aggregate "nearest thing", so "reach it" and "have I passed it" had nothing
   to refer to.

## 3. Files

**New**

| File | Purpose |
|---|---|
| `smartcane/risk.py` | three-level risk engine |
| `tests/scenarios.py` | the twelve specified scenarios, 35 checks |
| `tools/calibrate_stride.py` | per-user stride measurement |
| `tools/benchmark.py` | CPU-side timing |

**Modified**

| File | Change |
|---|---|
| `smartcane/vision.py` | history keeps distance; `closing_speed`, `time_to_collision`; motion prefers distance over box growth |
| `smartcane/guidance.py` | `assess()` delegates to the risk engine; new `reach_object`, `bypass`, `clearance`, `describe_all`, `_stop_text`; `_phrase` uses `best_direction` |
| `smartcane/intent.py` | 7 new intents; pre-sorted phrase tokens and a shared-word filter |
| `smartcane/__main__.py` | conversation context; handlers for the new intents |
| `smartcane/config.py` | motion, TTC, risk, stride and clearance tunables; `load_stride()` |
| `README.md` | architecture, risk table, command table |
| `tests/smoke_test.py` | STOP assertion updated for explained alerts |

No existing module was removed and no second detection pipeline was added.
`Detector`, `Scene`, the tracker, the serial link, the audio arbiter and the
ASR are unchanged in behaviour.

## 4. Three-level risk classification

`risk.assess_object()` returns a level **and the reason it fired**, so the
spoken warning can explain itself.

| Level | Rules (first match wins) |
|---|---|
| **CRITICAL** | TTC ≤ 1.5 s on a confident detection · distance ≤ 0.4 m · in corridor at ≤ 0.8 m · frame-filling with no distance estimate |
| **MEDIUM** | TTC ≤ 4 s · in corridor at ≤ 1.6 m · closing at ≤ 2.4 m · partly filling with no distance |
| **LOW** | everything else that is confirmed visible |

Inputs actually used: estimated distance, closing speed, time to collision,
corridor overlap (box geometry, not just the zone label), frame-filling ratio,
and detection confidence.

Deliberate design choices:

- **Category is not an input.** A car is graded exactly like a chair; only its
  distance, motion and position matter.
- **Weak detections cannot escalate on motion alone.** Below
  `RISK_MIN_CONFIDENCE = 0.45` the TTC and frame-filling rules are disabled, so
  a 30 % blob cannot trigger a stop. Distance-based rules still apply, because
  the ultrasonic is independent evidence.
- **The ultrasonic is graded separately.** It sees walls, doors and steps COCO
  cannot name. A close reading with no matching camera object becomes an
  "unidentified obstacle" at the appropriate level.

## 5. Navigation and step calculation

```
steps = floor( (min(distance, SENSOR_HORIZON) - STOP_MARGIN) / stride )
        clamped to [0, MAX_STEPS_TO_ANNOUNCE]
```

- `stride` is the user's calibrated value from `~/.smartcane_stride`, written
  by `tools/calibrate_stride.py`. It falls back to 0.65 m only until the tool
  has been run.
- `SENSOR_HORIZON = 2.0 m` caps what we are willing to promise, because the
  ultrasonic verifies roughly 2 m of corridor in a ~15° cone.
- `STOP_MARGIN = 0.5 m` is body clearance, so "two steps" never lands the user
  against the object.

`reach_object()` uses the full estimated distance (up to 12 steps) because the
user asked how far away a *specific named object* is, not how far they can
safely walk blind.

Verified: at 2.2 m a 0.55 m stride says four steps, a 0.80 m stride says three.

## 6. Obstacle avoidance

`Guidance.bypass()`:

1. If the state is STOP or URGENT → refuse to route around it, tell the user
   to stop. Never plan a path past something 40 cm away.
2. If clear → "Nothing is blocking your path."
3. Otherwise `best_direction()` compares the nearest hazard in the left and
   right zones. A side is only offered if it has ≥ 1.0 m of detected clearance;
   if both are tight, it returns None and the cane says so instead of guessing.
4. The step count for the chosen side comes from the same formula, capped at 3.

**Honest limitation:** clearance on the sides is *inferred from camera
detections only*. A single forward-facing ultrasonic cannot measure the sides,
so "the left appears clearer" means "nothing was detected there", which is why
the wording never claims a side is safe. When both sides are occupied the cane
stops rather than inventing a route.

## 7. STOP alert mechanism

```
Stop! <object> is <where><distance>. <why>
```

Examples produced by the code:

- `Stop! A car is directly in front of you at approximately three metres. Collision risk.`
- `Stop! A chair is directly in front of you at approximately 35 centimetres. Do not move forward.`
- `Stop! A person is directly in front of you at approximately 90 centimetres. Do not move forward.`

- Fired at `Priority.REFLEX`, the highest in the arbiter, so it preempts any
  speech in progress. The command is never delayed for classification: the
  phrase is built from whatever is already known, and an unrecognised object
  becomes "An unidentified obstacle" rather than waiting for the detector.
- Under 1 m the distance is spoken in centimetres, which is what a user needs
  when they are about to walk into something.

## 8. Test results

`python tests/scenarios.py` — 35/35 checks.

| # | Scenario | Actual output |
|---|---|---|
| 1 | Chair 3 m, right | *"I can see a chair on your right, about three metres away."* → LOW |
| 2 | Chair 1.2 m, centre | *"A chair is blocking your path. Turn slightly left and walk two steps to go around it."* |
| 3 | Car 5→3 m in 0.8 s | closing 2.50 m/s, TTC 1.20 s → CRITICAL, *"Stop! A car is directly in front of you at approximately three metres. Collision risk."* |
| 4 | Person left, 2.5→1.8 m | *"I can see a person on your left, about two metres away."* |
| 5 | Obstacle ahead | 0.9 m → actionable advisory; 0.7 m → *"Stop! A person … 90 centimetres."* |
| 6 | Clear path | *"The path ahead is clear. Walk straight three steps, then ask me again."* |
| 7 | Three obstacles | names all three with sides; bypass picks left (2.0 m vs 1.5 m) |
| 8 | Object at 0.35 m | *"Stop! A chair … 35 centimetres. Do not move forward."* |
| 9 | Step calculation | stride 0.55 → four steps; stride 0.80 → three steps |
| 10 | Bypass request | *"A chair is blocking your path. Turn slightly left and walk two steps…"* |
| 11 | Obstacle passed | object absent from scene → *"The path ahead is clear…"* |
| 12 | Uncertain detection | 30 % confidence, no distance → not critical, *"I cannot estimate the distance. Please move a little closer and ask again."* |
| 13 | Contradiction check | exactly one direction in the instruction |

`python tests/smoke_test.py` — 97/97 checks, including 17 false-trigger guards
(bare "left"/"right" are still rejected) and the corrupted-serial-number cases.

## 9. Performance

Measured with `tools/benchmark.py` (6 objects in scene):

| Stage | Mean | p95 |
|---|---|---|
| intent classification | 3.44 ms | 4.41 ms |
| risk assessment (6 objects) | 0.087 ms | 0.108 ms |
| full situation assessment | 0.102 ms | 0.136 ms |
| announcement phrasing | 0.120 ms | 0.185 ms |
| describe (multi-object) | 0.018 ms | 0.029 ms |
| bypass planning | 0.141 ms | 0.227 ms |
| **decision layer total** | **3.90 ms** | |

Intent classification improved from 9.15 ms to 3.44 ms (2.7×) by pre-sorting
phrase tokens and skipping phrases that share no word with the utterance.

Detection is not included because it needs PyTorch and is measured on the Pi:

| Runtime | Latency | Source |
|---|---|---|
| PyTorch @320 | ~300 ms/frame | measured on the Pi in this project |
| ncnn @320 | ~80–130 ms/frame | after `tools/optimize_model.py` |

At an 8 fps target the frame budget is 125 ms, so **the decision layer is 3 %
of the budget and detection is the whole problem**. That is why
`optimize_model.py` matters more than any further tuning here.

## 10. Limitations and what to do next

**What is genuinely not solved**

1. **Distance is monocular and approximate.** It assumes a known real-world
   height per class and a focal length. A child, a low chair or a tilted camera
   all bias it. The ultrasonic corrects this only in the centre corridor.
2. **Time-to-collision is coarse.** It is derived from a 10-sample history at
   3–8 fps, so it resolves motion over roughly a second. A fast car appearing
   from a side street in under a second will not be caught by TTC — the
   distance rules are what protect against that case.
3. **Side clearance is inferred, not measured.** One forward-facing ultrasonic
   cannot see left or right. The cane says "nothing detected on your left",
   never "your left is safe".
4. **COCO cannot see doors, stairs, curbs or poles.** No amount of logic fixes
   this; it needs a custom-trained model. The ultrasonic detects them as
   unnamed obstacles, which is why "unidentified obstacle" exists.
5. **The new behaviour is validated on synthetic scenes, not real footage.**
   The twelve scenarios construct tracked objects with known distances and
   motion. They prove the decision logic, not the detector's real-world
   accuracy on a walking route.
6. **No field trial.** This has not been walked with a blind user. Until it
   has, it is a prototype.

**Recommended next steps, in order of value**

1. `python tools/optimize_model.py` on the Pi — triples the frame rate.
2. `python tools/calibrate_stride.py` — step counts are wrong for most people
   until this is run.
3. Record a real walking session and replay it through the decision layer to
   measure false-alarm and miss rates against ground truth.
4. Add a second ultrasonic angled to one side, or a wide-angle camera, to turn
   inferred clearance into measured clearance.
5. Train a small custom model for doors, steps and curbs — the classes that
   matter most to a blind pedestrian and are entirely absent from COCO.

## Status

The decision layer is implemented and unit-tested. The hardware path has not
been re-validated since this change, and none of it has been tested with a
real user on a real route. **This is a prototype, not a certified safety
device, and it should not be relied on for independent navigation.**
