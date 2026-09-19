#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if logs=$(python3 "$SCRIPT_DIR/read_logs.py"); then
  printf '%s\n' "$logs" | python3 "$SCRIPT_DIR/detect_errors.py"
else
  printf '%s\n' "$logs" >&2
  printf '%s\n' "Log collection failed. Detection was not performed." >&2
  exit 1
fi
