#!/usr/bin/env bash
set -euo pipefail

BIND_HOST="0.0.0.0"
PORT="8000"
RELOAD=0

usage() {
  echo "Usage: start_backend.sh [--host HOST] [--port PORT] [--reload]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      BIND_HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --reload)
      RELOAD=1
      shift
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

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
backend_root="$repo_root/backend"

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

: "${DATA_ROOT:=$repo_root/data}"
: "${BACKEND_HOST:=$BIND_HOST}"
: "${BACKEND_REST_PORT:=$PORT}"
: "${BACKEND_WS_PORT:=$BACKEND_REST_PORT}"

python_exe="$repo_root/.venv/bin/python"
if [[ ! -x "$python_exe" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python_exe="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    python_exe="$(command -v python)"
  else
    echo "Python not found. Create .venv or install Python." >&2
    exit 1
  fi
fi

if [[ "${DATABASE_URL:-}" == postgresql* ]]; then
  if ! "$python_exe" - <<'PY'
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec('psycopg2') else 1)
PY
  then
    echo "Warning: DATABASE_URL is PostgreSQL but psycopg2 is missing. Falling back to SQLite." >&2
    unset DATABASE_URL
  fi
fi

uvicorn_args=("-m" "uvicorn" "app.main:app" "--host" "$BACKEND_HOST" "--port" "$BACKEND_REST_PORT")
if [[ "$RELOAD" -eq 1 ]]; then
  uvicorn_args+=("--reload")
fi

echo "Starting backend at http://$BACKEND_HOST:$BACKEND_REST_PORT"
cd "$backend_root"
DATA_ROOT="$DATA_ROOT" BACKEND_HOST="$BACKEND_HOST" BACKEND_REST_PORT="$BACKEND_REST_PORT" BACKEND_WS_PORT="$BACKEND_WS_PORT" \
  exec "$python_exe" "${uvicorn_args[@]}"
