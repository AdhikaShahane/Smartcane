#!/usr/bin/env bash
# Install Sahayak Drishti as a systemd service so it starts on power-up.
#
#   bash tools/install_service.sh --camera "http://10.126.242.147:8080/video" --mic 1
#
# Then it starts automatically every time the Pi gets power. No login needed,
# no terminal, no manually typing the command.
#
# Remove it again with:
#   sudo systemctl disable --now smartcane && sudo rm /etc/systemd/system/smartcane.service
set -euo pipefail

SERVICE_NAME="smartcane"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
CAMERA=""
MIC=""
EXTRA=""
DEMO="1"

usage() {
    cat <<'USAGE'
Install Sahayak Drishti as a systemd service so it starts on power-up.

  bash tools/install_service.sh --mic 1
  bash tools/install_service.sh --camera "http://10.126.242.147:8080/video" --mic 1

Options:
  --camera URL     network camera URL. OMIT THIS unless the phone has a
                   static IP: the cane finds a cached or discovered camera
                   by itself, and a hardcoded DHCP address breaks at boot.
  --mic INDEX      microphone device index (default: auto)
  --no-demo        start with the honest alarm instead of the demo one
  --extra "..."    any other flags to pass to smartcane
USAGE
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --camera) CAMERA="${2:-}"; shift 2 ;;
        --mic)    MIC="${2:-}";    shift 2 ;;
        --no-demo) DEMO="0"; shift ;;
        --extra)  EXTRA="${2:-}";  shift 2 ;;
        -h|--help) usage ;;
        *) echo "unknown option: $1"; usage ;;
    esac
done

# -- work out where everything actually lives --------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"

# Use the virtualenv's python if we are inside one, otherwise the system one.
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
elif [ -x "${REPO_DIR}/../cane/bin/python" ]; then
    PYTHON="$(cd "${REPO_DIR}/../cane/bin" && pwd)/python"
else
    PYTHON="$(command -v python3)"
fi

if [ ! -x "$PYTHON" ]; then
    echo "!! could not find a python interpreter. Activate the venv first:"
    echo "     source ~/cane/bin/activate"
    exit 1
fi

echo "=============================================================="
echo " Installing ${SERVICE_NAME} as a boot service"
echo "=============================================================="
echo " repo    : ${REPO_DIR}"
echo " python  : ${PYTHON}"
echo " user    : ${RUN_USER}"
echo " camera  : ${CAMERA:-<none>}"
echo " mic     : ${MIC:-auto}"
echo " demo    : ${DEMO}"
echo

# Sanity check: does the module actually import with this interpreter?
# (cd first: the check must not depend on which directory the user ran this from)
if ! ( cd "$REPO_DIR" && "$PYTHON" -c "import smartcane" ) 2>/dev/null < /dev/null; then
    echo "!! this interpreter cannot import smartcane from ${REPO_DIR}"
    echo "   run it from the repo root, with the venv active."
    exit 1
fi

# -- build the command line --------------------------------------------------
# Written as if/fi rather than `test && VAR=...`: under `set -e` a false test in
# an AND-list aborts the script, so omitting an option would silently kill the
# installer.
EXEC_ARGS=""
if [ -n "$CAMERA" ]; then
    EXEC_ARGS="${EXEC_ARGS} --camera \"${CAMERA}\""
fi
if [ -n "$MIC" ]; then
    EXEC_ARGS="${EXEC_ARGS} --mic ${MIC}"
fi
if [ "$DEMO" = "1" ]; then
    EXEC_ARGS="${EXEC_ARGS} --demo"
fi
if [ -n "$EXTRA" ]; then
    EXEC_ARGS="${EXEC_ARGS} ${EXTRA}"
fi

# Only request groups that exist. systemd refuses to start a unit whose
# Group= or SupplementaryGroups= names a group the system does not have, and
# reports it as the cryptic "status=216/GROUP", which looks like a code fault.
#
# Group= is left OUT entirely: systemd then uses the user's primary group,
# which is always correct. Naming a group explicitly only adds a way to break.
GROUPS_LIST=""
for g in audio video gpio dialout plugdev; do
    if getent group "$g" > /dev/null 2>&1; then
        if [ -z "$GROUPS_LIST" ]; then
            GROUPS_LIST="$g"
        else
            GROUPS_LIST="${GROUPS_LIST},$g"
        fi
    fi
done
if [ -n "$GROUPS_LIST" ]; then
    GROUPS_LINE="SupplementaryGroups=${GROUPS_LIST}"
else
    GROUPS_LINE=""
fi

# -- write the unit ----------------------------------------------------------
sudo tee "$UNIT_PATH" > /dev/null << UNIT
[Unit]
Description=Sahayak Drishti smart cane
# The camera is usually a phone on the network, so wait for networking.
Wants=network-online.target sound.target
After=network-online.target sound.target
StartLimitBurst=5
StartLimitIntervalSec=120

[Service]
Type=simple
User=${RUN_USER}
${GROUPS_LINE}
WorkingDirectory=${REPO_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=SMARTCANE_BAUD=9600
Environment=SMARTCANE_DEMO=${DEMO}
Environment=HOME=/home/${RUN_USER}
ExecStart=${PYTHON} -m smartcane${EXEC_ARGS}
Restart=always
RestartSec=5
# Give up cleanly rather than looping forever if it can never start.
TimeoutStartSec=60
KillSignal=SIGINT
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" > /dev/null 2>&1

echo "--------------------------------------------------------------"
echo " Installed: ${UNIT_PATH}"
echo " Enabled  : starts automatically at every boot"
echo
echo " Start it now without rebooting:"
echo "   sudo systemctl start ${SERVICE_NAME}"
echo
echo " Watch the live log:"
echo "   journalctl -u ${SERVICE_NAME} -f"
echo
echo " Stop it:"
echo "   sudo systemctl stop ${SERVICE_NAME}"
echo
echo " Make it permanent OFF (survives reboot):"
echo "   sudo systemctl disable --now ${SERVICE_NAME}"
echo "--------------------------------------------------------------"
