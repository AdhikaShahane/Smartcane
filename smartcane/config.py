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
# COCO classes
# ---------------------------------------------------------------------------
# Everything the detector can NAME. The model was trained on these 80 classes
# and nothing else, so this is the honest ceiling: it cannot see a door, a
# stair, a curb or a pole, because COCO does not contain them.
OBSTACLE_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
}

# The subset worth WARNING about while walking. Everything else can still be
# named when asked ("what is in front of me") but must not fill the air with
# "cup ahead, cup ahead" while the user is trying to cross a road.
HAZARD_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "bus", "train", "truck",
    "boat", "bench", "chair", "couch", "dining table", "bed", "toilet",
    "refrigerator", "oven", "potted plant", "dog", "horse", "cow", "sheep",
    "suitcase", "backpack", "fire hydrant", "stop sign", "traffic light",
    "parking meter", "tv", "vase", "teddy bear",
}

# Real-world height (metres) used for monocular distance estimation.
# Anything missing here is still detected and named, just without a distance.
OBJ_HEIGHTS = {
    "person": 1.70, "bicycle": 1.00, "car": 1.50, "motorcycle": 1.10,
    "bus": 3.00, "truck": 3.00, "train": 3.50, "boat": 2.00,
    "traffic light": 1.00, "fire hydrant": 0.75, "stop sign": 0.75,
    "parking meter": 1.30, "bench": 0.45,
    "bird": 0.15, "cat": 0.25, "dog": 0.50, "horse": 1.60, "sheep": 0.80,
    "cow": 1.40, "elephant": 2.50, "bear": 1.20, "zebra": 1.40,
    "giraffe": 3.00,
    "backpack": 0.50, "umbrella": 0.90, "handbag": 0.25, "tie": 0.30,
    "suitcase": 0.65, "skis": 1.20, "snowboard": 1.00, "surfboard": 1.20,
    "baseball bat": 0.80, "baseball glove": 0.30, "skateboard": 0.20,
    "tennis racket": 0.60, "kite": 0.50, "frisbee": 0.10,
    "bottle": 0.25, "wine glass": 0.20, "cup": 0.10, "fork": 0.20,
    "knife": 0.25, "spoon": 0.18, "bowl": 0.08,
    "banana": 0.18, "apple": 0.08, "sandwich": 0.10, "orange": 0.08,
    "broccoli": 0.15, "carrot": 0.20, "hot dog": 0.10, "pizza": 0.04,
    "donut": 0.08, "cake": 0.15,
    "chair": 0.85, "couch": 0.80, "potted plant": 0.60, "bed": 0.50,
    "dining table": 0.75, "toilet": 0.70,
    "tv": 0.60, "laptop": 0.25, "mouse": 0.05, "remote": 0.03,
    "keyboard": 0.03, "cell phone": 0.15,
    "microwave": 0.30, "oven": 0.70, "toaster": 0.20, "sink": 0.20,
    "refrigerator": 1.70, "book": 0.25, "clock": 0.30, "vase": 0.30,
    "scissors": 0.18, "teddy bear": 0.30, "hair drier": 0.20,
    "toothbrush": 0.18,
}
CORRIDOR_LEFT = 0.30
CORRIDOR_RIGHT = 0.70
ZONE_HYSTERESIS = 0.04    # deadband so objects do not flicker left/right

# Tracker
TRACK_MAX_AGE = 1.0       # seconds before an unmatched track is dropped
TRACK_MAX_DIST = 140      # px, max centroid jump to be considered the same object
TRACK_MIN_HITS = 2        # frames a track must exist before it may be announced
# A very confident first sighting is announced immediately instead of waiting
# for a second frame. At ~3 detections/sec, waiting costs ~330 ms of delay on
# exactly the case that matters most: someone stepping into the path.
FAST_CONFIRM_CONF = 0.65

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
MAX_STEPS_TO_ANNOUNCE = 3

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
