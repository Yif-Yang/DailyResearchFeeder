#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/runtime/daily_digest_daemon.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Daily digest daemon is not running"
  exit 0
fi

daemon_pid="$(cat "$PID_FILE" 2>/dev/null || true)"

if [[ -z "$daemon_pid" ]]; then
  rm -f "$PID_FILE"
  echo "Removed empty pid file"
  exit 0
fi

if kill -0 "$daemon_pid" 2>/dev/null; then
  kill "$daemon_pid"
  echo "Stopped daily digest daemon pid $daemon_pid"
else
  echo "Process $daemon_pid was not running; cleaning up pid file"
fi

rm -f "$PID_FILE"