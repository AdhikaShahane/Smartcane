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

# Real-world height (metres) used for monocular distance estimation.
OBJ_HEIGHTS = {
    "person": 1.70, "bicycle": 1.00, "motorcycle": 1.10, "car": 1.50,
    "bus": 3.00, "truck": 3.00, "dog": 0.50, "chair": 0.85,
    "dining table": 0.75, "bench": 0.45, "backpack": 0.50,
    "potted plant": 0.60, "couch": 0.80, "bed": 0.50, "toilet": 0.70,
}

# Only these COCO classes are allowed to trigger an announcement.
OBSTACLE_CLASSES = {
    "person", "bicycle", "motorcycle", "car", "bus", "truck", "dog",
    "chair", "dining table", "bench", "couch", "bed", "toilet",
    "backpack", "suitcase", "potted plant",
}

# Walking corridor as a fraction of frame width (left, right).
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
