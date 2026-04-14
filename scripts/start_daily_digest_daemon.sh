#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAEMON_SCRIPT="$ROOT_DIR/scripts/daily_digest_daemon.sh"
LOG_DIR="$ROOT_DIR/runtime"
PID_FILE="$LOG_DIR/daily_digest_daemon.pid"
NOHUP_LOG="$LOG_DIR/daily_digest_nohup.log"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "Daily digest daemon is already running with pid $existing_pid"
    exit 0
  fi
fi

nohup bash "$DAEMON_SCRIPT" >> "$NOHUP_LOG" 2>&1 &
daemon_pid=$!

sleep 1

if kill -0 "$daemon_pid" 2>/dev/null; then
  echo "Started daily digest daemon with pid $daemon_pid"
  echo "Daemon log: $ROOT_DIR/runtime/daily_digest_daemon.log"
  echo "Run log: $ROOT_DIR/runtime/daily_digest_runs.log"
else
  echo "Failed to start daily digest daemon" >&2
  exit 1
fi