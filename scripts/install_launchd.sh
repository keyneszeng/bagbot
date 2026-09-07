#!/usr/bin/env bash
# BagBot — install as a macOS launchd user agent.
#
# Installs a per-user LaunchAgent that runs BagBot on login and restarts
# it on crash.  Logs go to ~/Library/Logs/bagbot.{out,err}.log
#
# Usage:
#   bash scripts/install_launchd.sh                # install + load
#   bash scripts/install_launchd.sh uninstall     # remove + unload

set -euo pipefail

PLIST_LABEL="com.keyneszeng.bagbot"
PLIST_NAME="${PLIST_LABEL}.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"

mkdir -p "$LAUNCH_AGENTS" "$LOG_DIR" "$PROJECT_ROOT/data"

# Sanity checks.
if [[ ! -x "$VENV_PY" ]]; then
  echo "✗ Virtualenv not found at $VENV_PY"
  echo "  Create one first:  python3.10 -m venv $PROJECT_ROOT/.venv"
  echo "  Then:              $VENV_PY -m pip install -r $PROJECT_ROOT/requirements.txt"
  exit 1
fi

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
  echo "✗ No .env at $PROJECT_ROOT/.env"
  echo "  Copy from .env.example and fill in ORBIO_MCP_TOKEN + ORBIO_WALLET."
  exit 1
fi

uninstall() {
  if launchctl list | grep -q "$PLIST_LABEL"; then
    launchctl unload "$LAUNCH_AGENTS/$PLIST_NAME" 2>/dev/null || true
    echo "✓ Unloaded $PLIST_LABEL"
  fi
  rm -f "$LAUNCH_AGENTS/$PLIST_NAME"
  echo "✓ Removed $LAUNCH_AGENTS/$PLIST_NAME"
}

if [[ "${1:-}" == "uninstall" ]]; then
  uninstall
  exit 0
fi

# Build the plist.
cat > "$LAUNCH_AGENTS/$PLIST_NAME" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PY}</string>
        <string>-m</string>
        <string>bagbot.cli</string>
        <string>run</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>TZ</key>
        <string>Asia/Shanghai</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/bagbot.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/bagbot.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
PLIST

# Load it.
launchctl unload "$LAUNCH_AGENTS/$PLIST_NAME" 2>/dev/null || true
launchctl load "$LAUNCH_AGENTS/$PLIST_NAME"
sleep 1

echo "✓ Installed & loaded: $PLIST_LABEL"
echo "  Logs:    $LOG_DIR/bagbot.out.log"
echo "          $LOG_DIR/bagbot.err.log"
echo "  Stop:    launchctl unload $LAUNCH_AGENTS/$PLIST_NAME"
echo "  Remove:  bash $0 uninstall"
