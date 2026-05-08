#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
run_dir="$repo_root/.run"
log_dir="$run_dir/logs"
pid_file="$run_dir/mobile_be_fe.pids"

mkdir -p "$log_dir"

if [[ -f "$pid_file" ]]; then
  echo "Found existing PID file at $pid_file. Run scripts/stop_mobile.sh first."
  exit 1
fi

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

load_dotenv "$repo_root/.env"

: "${DATA_ROOT:=$repo_root/data}"
: "${BACKEND_HOST:=0.0.0.0}"
: "${BACKEND_REST_PORT:=8000}"
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

"$python_exe" - <<'PY'
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec('uvicorn') else 1)
PY
if [[ $? -ne 0 ]]; then
  echo "uvicorn not installed. Run: $python_exe -m pip install -e backend" >&2
  exit 1
fi

backend_log="$log_dir/backend.log"
flutter_log="$log_dir/flutter.log"

backend_args=("-m" "uvicorn" "app.main:app" "--host" "$BACKEND_HOST" "--port" "$BACKEND_REST_PORT")
if [[ "${BACKEND_RELOAD:-0}" == "1" ]]; then
  backend_args+=("--reload")
fi

echo "Starting backend on http://$BACKEND_HOST:$BACKEND_REST_PORT"
(
  cd "$repo_root/backend"
  DATA_ROOT="$DATA_ROOT" BACKEND_HOST="$BACKEND_HOST" BACKEND_REST_PORT="$BACKEND_REST_PORT" BACKEND_WS_PORT="$BACKEND_WS_PORT" \
    "$python_exe" "${backend_args[@]}"
) > "$backend_log" 2>&1 &
backend_pid=$!

flutter_device="${FLUTTER_DEVICE:-chrome}"
flutter_args=()
if [[ -n "${FLUTTER_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  flutter_args=($FLUTTER_ARGS)
fi

echo "Starting Flutter on device: $flutter_device"
(
  cd "$repo_root/mobile-app"
  flutter run -d "$flutter_device" "${flutter_args[@]}"
) > "$flutter_log" 2>&1 &
flutter_pid=$!

{
  echo "backend $backend_pid"
  echo "flutter $flutter_pid"
} > "$pid_file"

echo "Logs:"
echo "- $backend_log"
echo "- $flutter_log"
echo "Stop with: scripts/stop_mobile.sh"
