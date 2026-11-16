#!/usr/bin/env bash
# One-shot health check for Sahayak Drishti on the Raspberry Pi.
#
# Runs every layer in order and prints PASS/FAIL for each, so a remote
# debugging session starts from facts instead of guesses.
#
# Usage:  bash tools/healthcheck.sh
#         bash tools/healthcheck.sh --no-mic-test    (skip the 4 s recording)

set -u
SKIP_MIC_TEST=0
[ "${1:-}" = "--no-mic-test" ] && SKIP_MIC_TEST=1

PASS=0
FAIL=0
declare -a FAILED

ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); FAILED+=("$1"); }
info() { echo "         $1"; }

cd "$(dirname "$0")/.." 2>/dev/null || cd "${0%/*}/.." || {
  echo "cannot locate the repository root from $0"; exit 2; }
if [ ! -f smartcane/__main__.py ]; then
  echo "cannot find smartcane/ - run this from the repo:"
  echo "  bash tools/healthcheck.sh"
  exit 2
fi
PY=${PYTHON:-python}

echo "============================================================"
echo " Sahayak Drishti - health check"
echo " $(date)"
echo "============================================================"

echo
echo "-- 1. code version ------------------------------------------"
HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "  HEAD = $HEAD"
if [ -f smartcane/__main__.py ]; then ok "smartcane package present"
else bad "smartcane package missing - wrong directory?"; fi

echo
echo "-- 2. unit tests --------------------------------------------"
if $PY tests/smoke_test.py >/tmp/smoke.log 2>&1; then
  COUNT=$(grep -c '\[ok  \]' /tmp/smoke.log)
  ok "smoke tests ($COUNT checks)"
else
  bad "smoke tests failed - see /tmp/smoke.log"
  tail -5 /tmp/smoke.log | sed 's/^/         /'
fi

echo
echo "-- 3. audio devices -----------------------------------------"
$PY -m smartcane --list-audio >/tmp/audio.log 2>&1
if grep -q "capture devices: 0" /tmp/audio.log; then
  bad "no microphone exists on this system"
  info "plug a USB headset in; the 3.5mm jack is output-only"
elif grep -q "capture devices:" /tmp/audio.log; then
  ok "microphone device found"
  grep -E '^\s+\[[0-9]+\] IN' /tmp/audio.log | sed 's/^/         /'
else
  bad "could not query audio devices"
  tail -3 /tmp/audio.log | sed 's/^/         /'
fi

echo
echo "-- 4. microphone signal -------------------------------------"
if [ "$SKIP_MIC_TEST" = "1" ]; then
  info "skipped (--no-mic-test)"
elif grep -q "capture devices: 0" /tmp/audio.log; then
  info "skipped - no capture device"
else
  echo "         >>> SPEAK NOW: count one two three four <<<"
  if $PY -m smartcane --test-mic >/tmp/mic.log 2>&1; then
    ok "microphone hears you"
    grep -E 'peak =|RESULT' /tmp/mic.log | sed 's/^/         /'
  else
    bad "microphone did not produce usable audio"
    grep -E 'peak =|RESULT|NO CAPTURE' /tmp/mic.log | sed 's/^/         /'
  fi
fi

echo
echo "-- 5. Arduino / ultrasonic ----------------------------------"
if ls /dev/ttyACM* >/dev/null 2>&1 || ls /dev/ttyUSB* >/dev/null 2>&1; then
  ok "Arduino serial device present"
  ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | sed 's/^/         /'
  echo "         (run 'SMARTCANE_BAUD=9600 $PY -m smartcane --dump-serial'"
  echo "          and wave your hand to confirm numbers change)"
else
  bad "no /dev/ttyACM* - Arduino not connected or not permitted"
  info "check the USB cable, and: sudo usermod -aG dialout \$USER (then reboot)"
fi

echo
echo "-- 6. camera -------------------------------------------------"
$PY - <<'PY' >/tmp/cam.log 2>&1
from smartcane.camera import discover_ip_webcams
from smartcane import config
cached = None
try:
    cached = config.CAMERA_CACHE.read_text().strip()
except Exception:
    pass
print("cached:", cached or "(none)")
found = discover_ip_webcams()
print("discovered:", found[:3] if found else "(none)")
PY
if grep -q "discovered: \[" /tmp/cam.log; then
  ok "found a network camera"
  grep "discovered:" /tmp/cam.log | sed 's/^/         /'
elif grep -q "cached: http" /tmp/cam.log; then
  ok "a camera URL is remembered"
  grep "cached:" /tmp/cam.log | sed 's/^/         /'
  info "if it is stale, run: $PY -m smartcane --camera scan --verbose"
else
  bad "no camera found (no cached URL, nothing on the network)"
  info "start IP Webcam on the phone, same Wi-Fi, then:"
  info "  $PY -m smartcane --camera scan --verbose"
fi

echo
echo "-- 7. speech output -----------------------------------------"
$PY - <<'PY' >/tmp/tts.log 2>&1
from smartcane.audio_out import TtsEngine
e = TtsEngine()
print("backend:", e.backend)
PY
BACKEND=$(grep "backend:" /tmp/tts.log | awk '{print $2}')
case "$BACKEND" in
  piper)  ok "natural voice (piper) installed" ;;
  espeak) bad "robotic voice (espeak) - run: bash tools/install_piper.sh" ;;
  none)   bad "no speech engine at all - sudo apt install -y espeak-ng" ;;
  *)      bad "unknown TTS state" ;;
esac

echo
echo "-- 8. object detector ---------------------------------------"
if [ -d models/yolov8n_ncnn_model ]; then
  ok "ncnn model present (fast path)"
elif [ -f models/yolov8n.onnx ]; then
  ok "ONNX model present"
elif [ -f models/yolov8n.pt ]; then
  bad "only PyTorch weights - detection will be ~300 ms/frame"
  info "run: $PY tools/optimize_model.py   (about 4x faster)"
else
  bad "no YOLO model in models/"
fi

echo
echo "============================================================"
echo " RESULT: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo " Failed:"
  for f in "${FAILED[@]}"; do echo "   - $f"; done
fi
echo "============================================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
