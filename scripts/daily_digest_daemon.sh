#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMEZONE="${TIMEZONE:-Asia/Shanghai}"

LOG_DIR="$ROOT_DIR/runtime"
PID_FILE="$LOG_DIR/daily_digest_daemon.pid"
DAEMON_LOG="$LOG_DIR/daily_digest_daemon.log"
RUN_LOG="$LOG_DIR/daily_digest_runs.log"
LOCK_FILE="$LOG_DIR/daily_digest_run.lock"

mkdir -p "$LOG_DIR"
touch "$DAEMON_LOG" "$RUN_LOG"

log() {
  printf '[%s] %s\n' "$(TZ="$TIMEZONE" date '+%Y-%m-%d %H:%M:%S %Z')" "$*" | tee -a "$DAEMON_LOG"
}

ensure_single_instance() {
  if [[ -f "$PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      log "Daemon already running with pid $existing_pid"
      exit 1
    fi
  fi

  echo "$$" > "$PID_FILE"
  trap 'rm -f "$PID_FILE"' EXIT INT TERM
}

load_runtime_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.env"
    set +a
  fi

  PYTHON_BIN="${PYTHON_BIN:-python3}"
  TARGET_EMAIL="${DAILY_FEEDER_EMAIL_TO:-${EMAIL_TO:-}}"
  LOOKBACK_DAYS="${DAILY_FEEDER_DAYS:-2}"
  RUN_ON_START="${DAILY_FEEDER_RUN_ON_START:-0}"
  RUN_ONCE="${DAILY_FEEDER_RUN_ONCE:-0}"
  DRY_RUN="${DAILY_FEEDER_DRY_RUN:-0}"
  RUN_MODE="${DAILY_FEEDER_MODE:-scheduled_day}"
  LLM_PROVIDER_DEFAULT="${DAILY_FEEDER_LLM_PROVIDER:-${LLM_PROVIDER:-copilot_cli}}"
  EMAIL_PROVIDER_DEFAULT="${DAILY_FEEDER_EMAIL_PROVIDER:-${EMAIL_PROVIDER:-gmail_smtp}}"
  PREP_START_HOUR="${DAILY_FEEDER_PREP_START_HOUR:-8}"

  export TZ="$TIMEZONE"
  export LLM_PROVIDER="${DAILY_FEEDER_LLM_PROVIDER:-${LLM_PROVIDER:-$LLM_PROVIDER_DEFAULT}}"
  export EMAIL_PROVIDER="${DAILY_FEEDER_EMAIL_PROVIDER:-${EMAIL_PROVIDER:-$EMAIL_PROVIDER_DEFAULT}}"
  export COPILOT_COMMAND="${COPILOT_COMMAND:-copilot}"
  export EMAIL_TO="$TARGET_EMAIL"
}

missing_required_env() {
  local missing=()

  if [[ "${LLM_PROVIDER:-copilot_cli}" == "copilot_cli" ]]; then
    if ! command -v "$COPILOT_COMMAND" >/dev/null 2>&1; then
      missing+=(COPILOT_COMMAND)
    fi
  elif [[ "${LLM_PROVIDER:-copilot_cli}" == "openai" ]]; then
    [[ -n "${OPENAI_API_KEY:-}" ]] || missing+=(OPENAI_API_KEY)
  elif [[ "${LLM_PROVIDER:-copilot_cli}" == "azure_openai" ]]; then
    [[ -n "${AZURE_OPENAI_API_KEY:-}" ]] || missing+=(AZURE_OPENAI_API_KEY)
    [[ -n "${AZURE_OPENAI_ENDPOINT:-}" ]] || missing+=(AZURE_OPENAI_ENDPOINT)
  fi

  if [[ "$DRY_RUN" != "1" && -z "${EMAIL_TO:-}" ]]; then
    missing+=(EMAIL_TO)
  fi

  if [[ "${EMAIL_PROVIDER:-azure_cli_graph}" == "resend" ]]; then
    [[ -n "${RESEND_API_KEY:-}" ]] || missing+=(RESEND_API_KEY)
  elif [[ "${EMAIL_PROVIDER:-azure_cli_graph}" == "gmail_smtp" || "${EMAIL_PROVIDER:-azure_cli_graph}" == "smtp" ]]; then
    if [[ -z "${SMTP_USERNAME:-${GMAIL_SMTP_USERNAME:-}}" ]]; then
      missing+=(SMTP_USERNAME)
    fi
    if [[ -z "${SMTP_PASSWORD:-${GMAIL_SMTP_PASSWORD:-}}" ]]; then
      missing+=(SMTP_PASSWORD)
    fi
  fi

  if (( ${#missing[@]} > 0 )); then
    log "Skip scheduled send: missing ${missing[*]}. Add them to $ROOT_DIR/.env and keep the daemon running."
    return 0
  fi

  return 1
}

get_next_run_info() {
  TIMEZONE_VALUE="$TIMEZONE" PREP_START_HOUR="$PREP_START_HOUR" "$PYTHON_BIN" - <<'PY'
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

timezone_name = os.environ["TIMEZONE_VALUE"]
now = datetime.now(ZoneInfo(timezone_name))
target_hour = int(os.environ.get("PREP_START_HOUR", "8"))
target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
if now >= target:
    target += timedelta(days=1)

print(f"{int((target - now).total_seconds())}|{target.strftime('%Y-%m-%d %H:%M:%S %Z')}")
PY
}

run_digest_once() {
  load_runtime_env

  if missing_required_env; then
    return 0
  fi

  log "Starting digest run for $EMAIL_TO in mode $RUN_MODE"

  if ! flock -n 9; then
    log "Previous digest run still holds the lock; skipping this trigger."
    return 0
  fi 9>"$LOCK_FILE"

  {
    printf '\n=== %s ===\n' "$(TZ="$TIMEZONE" date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'EMAIL_TO=%s\n' "$EMAIL_TO"
    printf 'DRY_RUN=%s\n' "$DRY_RUN"
  } >> "$RUN_LOG"

  local -a cmd=("$PYTHON_BIN" main.py --mode "$RUN_MODE" --days "$LOOKBACK_DAYS")
  if [[ "$DRY_RUN" == "1" ]]; then
    cmd+=(--dry-run)
  fi

  set +e
  (
    cd "$ROOT_DIR"
    "${cmd[@]}"
  ) >> "$RUN_LOG" 2>&1
  local status=$?
  set -e

  if [[ $status -eq 0 ]]; then
    log "Digest run finished successfully."
  else
    log "Digest run failed with exit code $status. See $RUN_LOG"
  fi

  return $status
}

main() {
  ensure_single_instance
  load_runtime_env
  log "Daemon started. Target email: $EMAIL_TO. Timezone: $TIMEZONE. Python: $PYTHON_BIN. LLM provider: $LLM_PROVIDER. Run mode: $RUN_MODE"

  if [[ "$RUN_ON_START" == "1" ]]; then
    run_digest_once || true
    if [[ "$RUN_ONCE" == "1" ]]; then
      return 0
    fi
  fi

  while true; do
    load_runtime_env
    local next_run_info
    next_run_info="$(get_next_run_info)"
    local sleep_seconds="${next_run_info%%|*}"
    local next_run_label="${next_run_info#*|}"
    log "Sleeping ${sleep_seconds}s until $next_run_label"
    sleep "$sleep_seconds"
    run_digest_once || true

    if [[ "$RUN_ONCE" == "1" ]]; then
      return 0
    fi

    sleep 5
  done
}

main "$@"