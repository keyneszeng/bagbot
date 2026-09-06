#!/usr/bin/env bash
# BagBot — install as a systemd user service (Linux).
#
#   bash scripts/install_systemd.sh                # install + enable + start
#   bash scripts/install_systemd.sh uninstall      # stop + disable + remove

set -euo pipefail

SERVICE_NAME="bagbot"
SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"
LOG_DIR="$HOME/.local/share/bagbot/logs"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"

mkdir -p "$(dirname "$SERVICE_FILE")" "$LOG_DIR" "$PROJECT_ROOT/data"

if [[ ! -x "$VENV_PY" ]]; then
  echo "✗ Virtualenv not found at $VENV_PY"
  echo "  python3.10 -m venv $PROJECT_ROOT/.venv && $VENV_PY -m pip install -r $PROJECT_ROOT/requirements.txt"
  exit 1
fi
if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
  echo "✗ No .env at $PROJECT_ROOT/.env — copy from .env.example first."
  exit 1
fi

uninstall() {
  systemctl --user disable --now "$SERVICE_NAME" 2>/dev/null || true
  rm -f "$SERVICE_FILE"
  systemctl --user daemon-reload
  echo "✓ Removed $SERVICE_FILE"
}

if [[ "${1:-}" == "uninstall" ]]; then
  uninstall
  exit 0
fi

cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=BagBot — self-funding, self-healing AI daemon for Orbio
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_ROOT}
ExecStart=${VENV_PY} -m bagbot.cli run
Restart=on-failure
RestartSec=10
Environment=TZ=Asia/Shanghai

StandardOutput=append:${LOG_DIR}/out.log
StandardError=append:${LOG_DIR}/err.log

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"
sleep 1
systemctl --user status "$SERVICE_NAME" --no-pager || true

echo "✓ Installed & started: $SERVICE_NAME"
echo "  Logs:    journalctl --user -u $SERVICE_NAME -f"
echo "          $LOG_DIR/out.log"
echo "  Stop:    systemctl --user stop $SERVICE_NAME"
echo "  Remove:  bash $0 uninstall"
