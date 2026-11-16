#!/usr/bin/env bash
# Install a natural-sounding voice for Sahayak Drishti on the Raspberry Pi.
#
# espeak-ng is instant but sounds robotic. Piper is a small neural TTS that
# runs on the Pi 4 at about half real time and sounds human. This script
# installs piper and downloads one English voice (~60 MB).
#
# Usage:  bash tools/install_piper.sh
set -e

VOICE="en_US-lessac-medium"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
DEST="$(cd "$(dirname "$0")/.." && pwd)/models"

echo "==> installing piper-tts"
pip install --upgrade piper-tts

echo "==> downloading voice: $VOICE"
mkdir -p "$DEST"
cd "$DEST"

if [ ! -f "${VOICE}.onnx" ]; then
  curl -L --fail -o "${VOICE}.onnx"      "${BASE}/${VOICE}.onnx"
  curl -L --fail -o "${VOICE}.onnx.json" "${BASE}/${VOICE}.onnx.json"
else
  echo "    already present"
fi

echo
echo "==> checking it works"
echo "Sahayak Drishti voice test." | piper --model "$DEST/${VOICE}.onnx" --output-raw \
  | aplay -r 22050 -f S16_LE -t raw -q - 2>/dev/null \
  && echo "    OK - you should have just heard a natural voice" \
  || echo "    playback failed; check aplay -l"

echo
echo "Done. Restart smartcane; the log should now say:  TTS: piper"
