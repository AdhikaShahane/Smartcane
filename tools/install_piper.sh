#!/usr/bin/env bash
# Install a natural-sounding voice for Sahayak Drishti on the Raspberry Pi.
#
# espeak-ng is instant but sounds robotic. Piper is a small neural TTS that
# runs on the Pi 4 at roughly half real time and sounds human.
#
# NOTE ON VERSIONS: piper-tts 1.8 is source-only (sdist), which needs a full
# toolchain and often fails on a Pi. 1.2.0 ships a pure-Python wheel plus
# aarch64 wheels for its dependencies, so it installs cleanly. We try the
# latest first and fall back to 1.2.0.
#
# Usage:  bash tools/install_piper.sh
set -u

VOICE="en_US-lessac-medium"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
DEST="$(cd "$(dirname "$0")/.." && pwd)/models"

echo "==> installing piper-tts"
if pip install --upgrade piper-tts 2>/dev/null; then
  echo "    installed latest"
elif pip install --upgrade "piper-tts==1.2.0" 2>/dev/null; then
  echo "    installed 1.2.0 (wheel build, ARM friendly)"
else
  echo "    could not install piper-tts."
  echo "    Try:  sudo apt install -y build-essential python3-dev"
  echo "    then re-run this script. Until then espeak-ng is used."
  exit 1
fi

echo "==> downloading voice: $VOICE (~63 MB)"
mkdir -p "$DEST"
cd "$DEST"
if [ ! -f "${VOICE}.onnx" ]; then
  curl -L --fail --progress-bar -o "${VOICE}.onnx"      "${BASE}/${VOICE}.onnx" || {
    echo "    download failed - check the Pi has internet"; exit 1; }
  curl -L --fail --silent -o "${VOICE}.onnx.json" "${BASE}/${VOICE}.onnx.json"
else
  echo "    already present"
fi

echo
echo "==> verifying through the same code path smartcane uses"
python - "$DEST/${VOICE}.onnx" <<'PY'
import sys, wave, io
path = sys.argv[1]
try:
    try:
        from piper import PiperVoice
    except ImportError:
        from piper.voice import PiperVoice
    voice = PiperVoice.load(path)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        if hasattr(voice, "synthesize_wav"):
            voice.synthesize_wav("Sahayak Drishti voice test.", wf)
        else:
            voice.synthesize("Sahayak Drishti voice test.", wf)
    print(f"    piper works - {buf.getbuffer().nbytes} bytes of audio generated")
except Exception as exc:
    print(f"    piper NOT usable: {exc}")
    sys.exit(1)
PY

if [ $? -ne 0 ]; then
  echo
  echo "    piper installed but could not synthesize. smartcane will fall"
  echo "    back to espeak-ng automatically. Send me the error above."
  exit 1
fi

echo
echo "Done. Restart smartcane; the log should now say:  TTS: piper"
