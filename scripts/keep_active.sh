#!/usr/bin/env bash
# BagBot keep_active — a simple, dependency-free watchdog for the daemon.
#
# What it does:
#   1. Verifies the BagBot daemon is running (via launchd on macOS, or
#      pgrep on Linux).  If not, it (re)launches it.
#   2. Every N minutes, it pings the dashboard /api/state endpoint.
#      If the endpoint is down OR the last tick is older than 2× the
#      poll interval, it restarts the daemon.
#   3. Logs everything to stdout (which you can redirect).
#
# Use it from cron, launchd, or just run it in a terminal while you
# develop.  It is a *companion* to the BagBot daemon itself — the
# daemon has its own launchd/systemd unit, so most users won't need
# this script.  It exists for the same reason keep_active.py exists
# in the technocore community:  belt + suspenders.
#
# Usage:
#   ./scripts/keep_active.sh                 # default: 5 min check, 24h max age
#   CHECK_INTERVAL=60 ./scripts/keep_active.sh
#   ./scripts/keep_active.sh status         # print what we see, don't act

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"
LOG="$PROJECT_ROOT/data/keep_active.log"
DASHBOARD_URL="http://127.0.0.1:8765/api/state"
CHECK_INTERVAL="${CHECK_INTERVAL:-300}"     # 5 min
MAX_AGE_SEC="${MAX_AGE_SEC:-900}"            # 2.5× the default POLL_INTERVAL

mkdir -p "$(dirname "$LOG")"

ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

is_macos() { [[ "$(uname -s)" == "Darwin" ]]; }

daemon_running() {
  if is_macos; then
    launchctl list 2>/dev/null | grep -q "com.keyneszeng.bagbot"
  else
    pgrep -f "bagbot.cli run" >/dev/null 2>&1
  fi
}

daemon_start() {
  log "starting BagBot daemon…"
  if is_macos; then
    launchctl load "$HOME/Library/LaunchAgents/com.keyneszeng.bagbot.plist" 2>&1 \
      | tee -a "$LOG" || true
  else
    systemctl --user start bagbot 2>&1 | tee -a "$LOG" || true
  fi
}

daemon_stop() {
  log "stopping BagBot daemon…"
  if is_macos; then
    launchctl unload "$HOME/Library/LaunchAgents/com.keyneszeng.bagbot.plist" 2>&1 \
      | tee -a "$LOG" || true
  else
    systemctl --user stop bagbot 2>&1 | tee -a "$LOG" || true
  fi
}

last_tick_age() {
  # Hits the dashboard.  Returns the age in seconds, or -1 on error.
  if ! command -v curl >/dev/null 2>&1; then
    echo "-1"
    return
  fi
  local resp
  resp="$(curl -fsS --max-time 5 "$DASHBOARD_URL" 2>/dev/null)" || { echo "-1"; return; }
  local now ts age
  now="$(date +%s)"
  ts="$(echo "$resp" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("ts",0))' 2>/dev/null)" || { echo "-1"; return; }
  if [[ -z "$ts" || "$ts" == "0" ]]; then echo "-1"; return; fi
  age=$(( now - ${ts%.*} ))
  echo "$age"
}

cmd_status() {
  if daemon_running; then
    log "status: BagBot daemon is RUNNING"
  else
    log "status: BagBot daemon is DOWN"
  fi
  local age
  age="$(last_tick_age)"
  if [[ "$age" == "-1" ]]; then
    log "status: dashboard unreachable at $DASHBOARD_URL"
  else
    log "status: last tick ${age}s ago (max ${MAX_AGE_SEC}s)"
  fi
}

if [[ "${1:-}" == "status" ]]; then
  cmd_status
  exit 0
fi

log "BagBot keep_active started (CHECK_INTERVAL=${CHECK_INTERVAL}s, MAX_AGE=${MAX_AGE_SEC}s)"

trap 'log "keep_active stopping (signal)"; exit 0' INT TERM

while true; do
  if ! daemon_running; then
    log "daemon is DOWN — launching"
    daemon_start
    sleep 5
  fi
  age="$(last_tick_age)"
  if [[ "$age" == "-1" ]]; then
    log "dashboard unreachable (no daemon / not started yet)"
  elif (( age > MAX_AGE_SEC )); then
    log "last tick ${age}s ago > max ${MAX_AGE_SEC}s — restarting daemon"
    daemon_stop
    sleep 2
    daemon_start
    sleep 5
  else
    log "healthy — last tick ${age}s ago"
  fi
  sleep "$CHECK_INTERVAL"
done
