#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL=""
WS_BASE_URL=""
MODE="dev"
PORT="3000"

usage() {
  echo "Usage: start_dashboard.sh [--api-base-url URL] [--ws-base-url URL] [--mode dev|prod] [--port PORT]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base-url)
      API_BASE_URL="$2"
      shift 2
      ;;
    --ws-base-url)
      WS_BASE_URL="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "$MODE" != "dev" && "$MODE" != "prod" ]]; then
  echo "Invalid mode: $MODE (use dev or prod)" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
dashboard_root="$repo_root/web-dashboard"

dotenv_path="$repo_root/.env"
load_dotenv() {
  local env_path="$1"
  if [[ ! -f "$env_path" ]]; then
    return
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line%%$'\r'}"
    [[ -z "$line" ]] && continue
    if [[ "$line" == *=* ]]; then
      local key="${line%%=*}"
      local value="${line#*=}"
      key="$(echo "$key" | xargs)"
      value="$(echo "$value" | xargs)"
      value="${value%\"}"
      value="${value#\"}"
      if [[ -n "$key" ]]; then
        export "$key"="$value"
      fi
    fi
  done < "$env_path"
}

load_dotenv "$dotenv_path"

backend_port="${BACKEND_PORT:-8000}"
if [[ -z "$API_BASE_URL" ]]; then
  API_BASE_URL="http://127.0.0.1:$backend_port"
fi
if [[ -z "$WS_BASE_URL" ]]; then
  WS_BASE_URL="ws://127.0.0.1:$backend_port"
fi

export NEXT_PUBLIC_API_BASE_URL="$API_BASE_URL"
export NEXT_PUBLIC_WS_BASE_URL="$WS_BASE_URL"

cd "$dashboard_root"
if [[ "$MODE" == "prod" ]]; then
  echo "Building dashboard for production..."
  npm run build
  echo "Starting dashboard (prod) at http://127.0.0.1:$PORT"
  exec npm run start -- -p "$PORT"
else
  echo "Starting dashboard (dev) at http://127.0.0.1:$PORT"
  exec npm run dev -- -p "$PORT"
fi
