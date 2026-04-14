#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
TARGET_EMAIL="${DAILY_FEEDER_EMAIL_TO:-${EMAIL_TO:-}}"
LOOKBACK_DAYS="${DAILY_FEEDER_DAYS:-2}"
DRY_RUN="${DAILY_FEEDER_DRY_RUN:-0}"
RUN_MODE="${DAILY_FEEDER_MODE:-digest}"
LLM_PROVIDER_DEFAULT="${DAILY_FEEDER_LLM_PROVIDER:-${LLM_PROVIDER:-copilot_cli}}"
EMAIL_PROVIDER_DEFAULT="${DAILY_FEEDER_EMAIL_PROVIDER:-${EMAIL_PROVIDER:-gmail_smtp}}"

export LLM_PROVIDER="${DAILY_FEEDER_LLM_PROVIDER:-${LLM_PROVIDER:-$LLM_PROVIDER_DEFAULT}}"
export EMAIL_PROVIDER="${DAILY_FEEDER_EMAIL_PROVIDER:-${EMAIL_PROVIDER:-$EMAIL_PROVIDER_DEFAULT}}"
export EMAIL_TO="$TARGET_EMAIL"

if [[ "$DRY_RUN" != "1" && -z "$TARGET_EMAIL" ]]; then
  echo "EMAIL_TO or DAILY_FEEDER_EMAIL_TO is required for a real send." >&2
  exit 1
fi

cd "$ROOT_DIR"

cmd=("$PYTHON_BIN" main.py --mode "$RUN_MODE" --days "$LOOKBACK_DAYS" --email-to "$TARGET_EMAIL" --llm-provider "$LLM_PROVIDER")
cmd+=(--email-provider "$EMAIL_PROVIDER")
if [[ "$DRY_RUN" == "1" ]]; then
  cmd+=(--dry-run)
fi

"${cmd[@]}"