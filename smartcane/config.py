"""Central configuration for Sahayak Drishti.

Every hardware pin, port, threshold and tunable lives here. Nothing else in the
package hard-codes a magic number, so the whole system can be retuned from one
file on the Pi.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models"

# ============================================================================
# ARDUINO LINK
# ============================================================================
SERIAL_PORT = os.getenv("SMARTCANE_SERIAL", "")   # "" -> auto-detect
SERIAL_BAUD = int(os.getenv("SMARTCANE_BAUD", "115200"))
SERIAL_TIMEOUT = 0.05
# If no valid frame arrives for this long, the sensor is treated as DEAD and the
# system falls back to camera-only.  Never silently assume "path is clear".
SERIAL_STALE_SEC = 1.0

# ============================================================================
# CAMERA
# ============================================================================
# auto | 0 | 1 | picamera2 | <url>
CAMERA_SOURCE = os.getenv("SMARTCANE_CAMERA", "auto")
CAM_WIDTH = 640
CAM_HEIGHT = 480
CAM_FPS = 30
CAM_STALE_SEC = 1.0
# The phone's IP changes on DHCP after every reboot, so remember the last URL
# that worked and re-discover it automatically when it stops responding.
CAMERA_CACHE = Path.home() / ".smartcane_camera"
CAMERA_SCAN_PORT = 8080
CAMERA_SCAN_TIMEOUT = 0.25

# ============================================================================
# VISION
# ============================================================================
YOLO_IMGSZ = 320          # 320 is ~4x faster than 640 on a Pi 4. Do not raise.
YOLO_CONF = 0.35          # lower = catches more objects, more false positives
YOLO_IOU = 0.45
DETECT_FPS = 8            # inference target; tracking fills the gaps

# Pinhole focal length in pixels for the captured width (Pi Camera v1.3 OV5647,
# 3.6 mm lens, 3.76 mm sensor width -> f_px = 3.6/3.76 * 640 ~= 613).
# Calibrate with tools/calibrate_distance.py if distances look wrong.
FOCAL_PX = float(os.getenv("SMARTCANE_FOCAL", "615"))

# ---------------------------------------------------------------------------
# ADE20K taxonomic model  (replaces COCO)
# ---------------------------------------------------------------------------
# COCO has no door, wall, floor, stairs, sidewalk or path - the classes a blind
# pedestrian actually collides with. ADE20K is a scene-parsing dataset with 150
# classes including all of them, so the cane can reason about *where it can
# walk* instead of only naming objects.
#
# IDs below are the official ADE20K train IDs from object150_info.csv.

# Ground you can walk on. This is the single most useful output of the whole
# system: "is the floor here" answers "can I step here" without needing to
# recognise what is in the way.
WALKABLE_IDS = {
    4,    # floor;flooring
    7,    # road;route
    10,   # grass
    12,   # sidewalk;pavement
    14,   # earth;ground
    29,   # rug;carpet  (indoor floor covering)
    53,   # path
    95,   # land;ground;soil
}

# Walkable, but a trip hazard. Treated as an obstacle that also gets named.
STAIR_IDS = {
    54,   # stairs;steps
    60,   # stairway;staircase
    97,   # escalator;moving staircase
    122,  # step;stair
}

# Things that physically stop you, and looking up they tell you where the walls
# are. Doors are here because a closed door is a wall you can walk through.
BARRIER_IDS = {
    1,    # wall
    9,    # windowpane;window
    15,   # door;double door
    33,   # fence;fencing
    39,   # railing;rail
    43,   # column;pillar
    59,   # screen door
}

# Objects that move through the world and can hit you.
MOVER_IDS = {
    13,   # person
    21,   # car
    81,   # bus
    84,   # truck
    103,  # van
    127,  # animal
    128,  # bicycle
}

# Furniture and street clutter worth avoiding.
CLUTTER_IDS = {
    11, 16, 18, 20, 25, 31, 34, 42, 44, 46, 51, 56, 63, 65, 70, 71,
    76, 88, 100, 113, 116, 137, 139,
}

# Everything we are willing to *name* as an obstacle.
HAZARD_IDS = BARRIER_IDS | MOVER_IDS | CLUTTER_IDS | STAIR_IDS

# Classes that count as background and must never be treated as obstacles.
IGNORE_IDS = {2, 3, 5, 6}          # building, sky, tree, ceiling

# ---------------------------------------------------------------------------
# ENVIRONMENT PROFILE
# ---------------------------------------------------------------------------
# A classroom does not contain a jet ski. Naming every class the model can
# possibly emit is how you get "microwave" shouted at a seated person.
#
# The profile only controls what gets NAMED. Anything not on the list is still
# treated as an obstacle - it is physically there - it simply is not named,
# and is spoken as "an obstacle".
#
#   indoor  : classroom, lab, corridor, home
#   outdoor : street, pavement, campus
#   all     : no filtering
ENVIRONMENT = os.getenv("SMARTCANE_ENV", "indoor").strip().lower()

INDOOR_NAMES = {
    "person", "chair", "armchair", "table", "desk", "counter", "countertop",
    "door", "wall", "window", "floor", "rug", "stairs", "stairway", "step",
    "cabinet", "shelf", "bookcase", "box", "bag", "basket", "bin",
    "plant", "bench", "railing", "pillar", "display case", "refrigerator",
    "sidewalk", "path", "bag", "sign",
}

OUTDOOR_NAMES = {
    "person", "car", "bus", "truck", "van", "bicycle", "animal",
    "door", "wall", "fence", "railing", "pillar", "stairs", "stairway",
    "step", "road", "sidewalk", "path", "grass", "ground",
    "traffic light", "street light", "sign", "bench", "bin",
}

# Things worth naming regardless of where you are.
ALWAYS_NAMES = {"person", "car", "bus", "truck", "van", "bicycle", "animal"}

# Height estimation still needs the raw label, so this map stays complete;
# the profile only decides whether the name is *spoken*.


def allowed_names() -> set[str]:
    """Classes this deployment is willing to name out loud."""
    if ENVIRONMENT == "all":
        return set(ADE20K_NAMES.values()) | set(ADE20K_HEIGHTS)
    if ENVIRONMENT == "outdoor":
        return OUTDOOR_NAMES | ALWAYS_NAMES
    return INDOOR_NAMES | ALWAYS_NAMES


# NAMED_NAMES is computed further down, once ADE20K_NAMES exists.

# ---------------------------------------------------------------------------
# HOW MUCH IT TALKS
# ---------------------------------------------------------------------------
#   critical : speak only when it is a stop-level hazard. Everything else is
#              answered on request. This is the default because continuous
#              chatter is how an assistive device gets switched off.
#   medium   : also warn about things blocking the path
#   all      : full chatty behaviour (proactive guidance for everything)
UNSOLICITED_ALERTS = os.getenv("SMARTCANE_ALERTS", "medium").strip().lower()

# In "critical" mode the cane stays silent unless something is this close.
# Speech costs about a second; at 1.4 m/s that is the distance you cover while
# it is still talking, so this is the outer edge of useful.
ALERT_DISTANCE_M = float(os.getenv("SMARTCANE_ALERT_DISTANCE", "1.0"))

# ---------------------------------------------------------------------------
# LABEL STABILITY  (anti-hallucination)
# ---------------------------------------------------------------------------
# A segmentation model flickers between classes on the same object. Naming the
# first frame it sees produces nonsense, so a label must earn the right to be
# spoken: enough votes, and a clear majority.
LABEL_MIN_VOTES = 2
LABEL_MIN_SHARE = 0.60
# A component smaller than this fraction of the frame is noise, not an object.
SEG_MIN_AREA_FRAC = 0.012
ADE20K_NAMES = {
    1: "wall", 4: "floor", 7: "road", 9: "window", 10: "grass",
    12: "sidewalk", 13: "person", 14: "ground", 15: "door",
    16: "table", 18: "plant", 20: "chair", 21: "car", 25: "shelf",
    29: "carpet", 31: "armchair", 33: "fence", 34: "desk", 39: "railing",
    42: "box", 43: "pillar", 44: "sign", 46: "counter", 51: "refrigerator",
    53: "path", 54: "stairs", 56: "display case", 60: "stairway",
    63: "bookcase", 65: "table", 70: "bench", 71: "countertop",
    76: "chair", 81: "bus", 84: "truck", 88: "street light",
    95: "ground", 97: "escalator", 103: "van", 113: "basket",
    116: "bag", 122: "step", 127: "animal", 128: "bicycle",
    137: "traffic light", 139: "bin",
}

# Real-world height (metres) for classes where a monocular estimate is
# meaningful. Stuff classes (wall, floor, path) are deliberately absent: their
# bounding box spans the frame, so a height-based distance would be nonsense.
ADE20K_HEIGHTS = {
    "person": 1.70, "car": 1.50, "bus": 3.00, "truck": 3.00, "van": 1.90,
    "bicycle": 1.00, "animal": 0.60,
    "door": 2.00, "window": 1.20, "fence": 1.20, "railing": 1.00,
    "pillar": 2.50, "wall": 2.50,
    "chair": 0.85, "armchair": 0.90, "table": 0.75, "desk": 0.75,
    "shelf": 1.60, "bookcase": 1.70, "cabinet": 1.20, "bench": 0.45,
    "counter": 0.90, "countertop": 0.95, "refrigerator": 1.70,
    "box": 0.40, "bag": 0.45, "basket": 0.30, "bin": 0.70,
    "sign": 1.00, "street light": 4.00, "traffic light": 1.00,
    "plant": 0.60, "display case": 1.20,
    "stairs": 1.00, "stairway": 2.00, "step": 0.18, "escalator": 1.00,
}

# Computed here because allowed_names() needs ADE20K_NAMES, which is above.
NAMED_NAMES = allowed_names()

# ---------------------------------------------------------------------------
# SEGMENTATION MODEL
# ---------------------------------------------------------------------------
# Tried in order; the first that exists wins. tools/fetch_model.py downloads
# the pretrained ADE20K semantic model, or you train your own with
# tools/train_segmentation.py.
# onnx  : use the ADE20K SegFormer model (accurate, slow on a Pi 4)
# yolo  : use a custom-trained segmentation checkpoint
# off   : never run segmentation; use the COCO/YOLO detector
# auto  : onnx/yolo if a model exists, otherwise the detector
SEG_MODE = os.getenv("SMARTCANE_SEG", "auto").strip().lower()

# If segmentation averages slower than this, the system switches itself to
# the detector and says so. 3.5 s/frame was measured on a Pi 4 with
# SegFormer-B1 at 512x512 - unusable, and the user should not have to read a
# log to discover that.
SEG_MAX_MS = float(os.getenv("SMARTCANE_SEG_MAX_MS", "1200"))
SEG_WARMUP_FRAMES = 3

SEG_MODEL_CANDIDATES = [
    MODEL_DIR / "segformer-ade20k.onnx",      # what fetch_model.py downloads
    MODEL_DIR / "ade20k-seg.onnx",
    MODEL_DIR / "yolo11n-sem-ade20k.pt",
    MODEL_DIR / "smartcane-seg.pt",
]
SEG_IMGSZ = 256           # segmentation is heavier than detection; 256 is the
                          # sweet spot on a Pi 4
# SegFormer is fixed at the resolution it was fine-tuned on.
SEG_INPUT_SIZE = int(os.getenv("SMARTCANE_SEG_SIZE", "256"))
SEG_CONF = 0.30
# A coarse occupancy grid turns the mask into "can I walk here" cheaply.
GRID_W, GRID_H = 15, 12   # 15 divides into three equal 5-column zones
# Fraction of blocked cells that makes a zone unusable.
ZONE_BLOCKED_FRACTION = 0.35
# Minimum walkable fraction for a side to be offered as a way around.
ZONE_USABLE_FRACTION = 0.55

# ---------------------------------------------------------------------------
# Derived name sets (kept in sync with the ID sets above)
# ---------------------------------------------------------------------------
HAZARD_NAMES = {ADE20K_NAMES[i] for i in HAZARD_IDS if i in ADE20K_NAMES}
WALKABLE_NAMES = {ADE20K_NAMES[i] for i in WALKABLE_IDS if i in ADE20K_NAMES}
STAIR_NAMES = {ADE20K_NAMES[i] for i in STAIR_IDS if i in ADE20K_NAMES}
CORRIDOR_LEFT = 0.30
CORRIDOR_RIGHT = 0.70
ZONE_HYSTERESIS = 0.04    # deadband so objects do not flicker left/right

# Tracker
TRACK_MAX_AGE = 3.0       # seconds before an unmatched track is dropped
TRACK_MAX_DIST = 180      # px, max centroid jump to be considered the same object
TRACK_MIN_HITS = 2        # frames a track must exist before it may be announced
# A very confident first sighting is announced immediately instead of waiting
# for a second frame. At ~3 detections/sec, waiting costs ~330 ms of delay on
# exactly the case that matters most: someone stepping into the path.
FAST_CONFIRM_CONF = 0.65

# ---------------------------------------------------------------------------
# MOTION / TIME-TO-COLLISION
# ---------------------------------------------------------------------------
# Motion is measured from the track history, so it needs a real time span.
MOTION_MIN_SPAN = 0.30    # s of history required before trusting a speed
MOTION_MIN_CHANGE_M = 0.25  # distance change that counts as approaching/leaving
CLOSING_MIN_SPEED = 0.25  # m/s below which "closing" is just noise
# Nothing in a corridor closes faster than this. Anything above it is a
# monocular-estimation artefact, not real motion, and must not trigger a stop.
MAX_PLAUSIBLE_CLOSING = 6.0
# Time to collision thresholds. These are what turn a stationary classification
# into a real risk: a car 6 m away doing 2 m/s is 3 s from you.
TTC_CRITICAL_SEC = 1.5
TTC_MEDIUM_SEC = 4.0

# ---------------------------------------------------------------------------
# SERIAL TRUST  (fighting corruption on a noisy link)
# ---------------------------------------------------------------------------
# A corrupt byte inside the number field turns "150.4 cm" into "19.4 cm". That
# is still a plausible distance, so it sails past the range check and becomes a
# false STOP. Two defences:
#
# 1. a reading that jumps further than this from the recent median is held back
#    until a second reading agrees with it, so genuine changes still land
OUTLIER_JUMP_M = 1.00
# 2. if fewer than this fraction of frames are readable, the link is not usable
#    and the ultrasonic is ignored entirely rather than occasionally believed
MIN_LINK_RELIABILITY = 0.05
LINK_RELIABILITY_WINDOW = 40

# ---------------------------------------------------------------------------
# RISK ESCALATION
# ---------------------------------------------------------------------------
# A detection this weak is not trusted to escalate risk on its own; it is
# downgraded and reported as "unidentified".
RISK_MIN_CONFIDENCE = 0.45
# How much of the frame height an object must fill to count as blocking.
RISK_BLOCKING_SIZE = 0.45
# Corridor overlap above which an object counts as partially in the path.
RISK_PATH_OVERLAP = 0.15

# ---------------------------------------------------------------------------
# STRIDE / STEP LENGTH
# ---------------------------------------------------------------------------
# User stride is calibrated, not assumed. tools/calibrate_stride.py writes
# this file; STEP_DEFAULT is only a starting guess until that has been run.
STRIDE_FILE = Path.home() / ".smartcane_stride"


# ============================================================================
# DISTANCE / STATE THRESHOLDS  (metres)
# ============================================================================
STOP_METERS = 0.40        # < this  -> STOP state, earcon + "Stop"
URGENT_METERS = 0.80      # < this  -> URGENT, announce immediately
ADVISORY_METERS = 1.60    # < this  -> ADVISORY, announce once
WATCH_METERS = 2.40       # < this  -> WATCH, silent tracking
SENSOR_HORIZON = 2.00     # what we actually trust for step guidance
STOP_MARGIN = 0.50        # body clearance subtracted before counting steps

# ============================================================================
# STEP LENGTH   SL = K * (a_max - a_min) ** 0.25   (Weinberg)
# ============================================================================
STEP_K = float(os.getenv("SMARTCANE_STEP_K", "0.45"))
STEP_MIN, STEP_MAX = 0.30, 1.10
STEP_DEFAULT = 0.65


def load_stride() -> float:
    """Read the calibrated stride, or fall back to the population default.

    Step counts are only meaningful if the stride is the user's own, so this
    is deliberately a file the calibration tool writes rather than a constant.
    """
    try:
        value = float(STRIDE_FILE.read_text(encoding="utf-8").strip())
    except Exception:                                   # noqa: BLE001
        return STEP_DEFAULT
    if STEP_MIN <= value <= STEP_MAX:
        return value
    return STEP_DEFAULT


STEP_M = load_stride()
MAX_STEPS_TO_ANNOUNCE = 3     # guidance: never promise more path than verified
MAX_STEPS_TO_REACH = 12       # reaching a named object may be further away
# A side counts as usable only if nothing is detected closer than this.
CLEARANCE_MIN_M = 1.2
# How long a mentioned object stays "the thing we were talking about", so a
# follow-up like "how do I reach it" refers back to it.
CONTEXT_TTL_SEC = 30.0

# ============================================================================
# ANNOUNCEMENT POLICY
# ============================================================================
ANNOUNCE_COOLDOWN_SEC = 3.0     # per-obstacle silence between repeats
GLOBAL_COOLDOWN_SEC = 1.2       # minimum gap between any two utterances
URGENT_MIN_GAP_SEC = 0.8        # URGENT/STOP bypass the cooldown, but not this
SPEAK_CLEAR_AFTER_SEC = 6.0     # say "path clear" only after this much silence
# A hazard that just sits there must be restated now and then, otherwise the
# user is warned once and then walks into it in silence. Announcements fire on
# change, so this is the maximum silence for an unchanged situation.
REPEAT_AFTER_SEC = 8.0

# ============================================================================
# AUDIO
# ============================================================================
AUDIO_RATE = 48000        # one rate end-to-end. TTS output is resampled to this.
AUDIO_BLOCK = 480         # 10 ms at 48 kHz
MIC_RATE = 16000          # what Vosk expects
MIC_BLOCK = 800           # 50 ms
PREROLL_SEC = 0.60        # ring buffer kept before VAD fires (never clip a word)
VAD_FRAME = 512           # samples @16 kHz = 32 ms (Silero)
VAD_END_SILENCE = 0.35    # trailing silence that ends an utterance
TTS_VOLUME = 0.70         # capped: loud TTS leaks into the inline mic

# espeak fallback voice. Defaults are shrill; a female variant at a lower
# pitch and slower rate is much easier to listen to for long periods.
ESPEAK_VOICE = os.getenv("SMARTCANE_ESPEAK_VOICE", "en-us+f3")
ESPEAK_RATE = int(os.getenv("SMARTCANE_ESPEAK_RATE", "150"))
ESPEAK_PITCH = int(os.getenv("SMARTCANE_ESPEAK_PITCH", "45"))


def _audio_device(env_name: str):
    """Resolve a device from the environment: '' -> system default,
    '3' -> index 3, 'Jabra' -> first device whose name contains 'Jabra'."""
    value = os.getenv(env_name, "").strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


# e.g. SMARTCANE_MIC=Jabra  SMARTCANE_SPEAKER=Jabra
AUDIO_INPUT_DEVICE = _audio_device("SMARTCANE_MIC")
AUDIO_OUTPUT_DEVICE = _audio_device("SMARTCANE_SPEAKER")

# ============================================================================
# PATHS
# ============================================================================
VOSK_MODEL = Path(os.getenv(
    "SMARTCANE_VOSK", str(MODEL_DIR / "vosk-model-small-en-us-0.15")))
# Tried in order; first one that exists wins.
YOLO_CANDIDATES = [
    MODEL_DIR / "yolov8n_ncnn_model",   # fastest on ARM
    MODEL_DIR / "yolov8n.onnx",         # medium
    MODEL_DIR / "yolov8n.pt",           # slowest but always works
]

# ============================================================================
# MISC
# ============================================================================
LOG_LEVEL = os.getenv("SMARTCANE_LOG", "INFO")
STARTUP_GREETING = "Sahayak Drishti ready."

# ---------------------------------------------------------------------------
# SOS BUTTON
# ---------------------------------------------------------------------------
# Wiring: one leg of the button to GPIO 17 (pin 11), the other leg to any GND
# (pin 9 or 14). No resistor needed - the internal pull-up is enabled in
# software, so the pin reads HIGH when idle and LOW when pressed.
#
# Change the pin here, or with SMARTCANE_SOS_PIN, without touching the code.
SOS_ENABLED = os.getenv("SMARTCANE_SOS", "1").strip() not in ("0", "off", "no")
SOS_PIN = int(os.getenv("SMARTCANE_SOS_PIN", "17"))
SOS_BOUNCE_SEC = 0.06        # ignore contact chatter from a cheap button
# 0 (the default) means say it ONCE per press and then stay quiet. Set this to
# a number of seconds only if you want a repeating siren.
SOS_REPEAT_SEC = float(os.getenv("SMARTCANE_SOS_REPEAT", "0"))
# Hold the button this long to cancel the alarm.
SOS_CANCEL_HOLD_SEC = 1.5
# Two presses closer together than this are treated as one. Without it, a
# bouncy button fires twice and the second press CANCELS the alarm it just
# raised - the worst possible failure for a panic button.
SOS_DEBOUNCE_SEC = 0.8

# The alarm text. {location} is replaced by the real location sentence, which
# is honest: without a GPS fix it says so rather than claiming anything was
# sent. Override the whole line with SMARTCANE_SOS_MESSAGE if you have your own
# notification system wired up.
# {location} may be used if you fit a GPS module, but it is deliberately NOT
# in the default sentence: announcing "my location is unknown" adds words and
# tells the user nothing they can act on.
SOS_MESSAGE = os.getenv(
    "SMARTCANE_SOS_MESSAGE",
    "Emergency! S O S button pressed. I need help.")

# ---------------------------------------------------------------------------
# DEMO MODE
# ---------------------------------------------------------------------------
# With no GPS fitted, the honest alarm says "my location is unknown". That is
# correct but it does not demonstrate the intended product, so the demo can
# instead *simulate* the finished behaviour.
#
# This is a presentation switch, nothing more. In demo mode no coordinates are
# read, computed or transmitted; the sentence is simply spoken as if a real
# alert had gone out. It is worth knowing that, because a demo of a safety
# feature is exactly the kind of thing that gets shown to a real user later.
DEMO_MODE = os.getenv("SMARTCANE_DEMO", "0").strip().lower() not in (
    "", "0", "off", "no", "false")

SOS_DEMO_MESSAGE = os.getenv(
    "SMARTCANE_SOS_DEMO_MESSAGE",
    "Emergency! S O S button pressed. Your live location has been shared.")