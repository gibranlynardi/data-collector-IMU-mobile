#!/usr/bin/env bash
set -euo pipefail

MODE="native"
START_FLUTTER=1

usage() {
  echo "Usage: start_all.sh [--mode native|docker] [--with-flutter|--no-flutter]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --with-flutter)
      START_FLUTTER=1
      shift
      ;;
    --no-flutter)
      START_FLUTTER=0
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

if [[ "$MODE" != "native" && "$MODE" != "docker" ]]; then
  echo "Invalid mode: $MODE (use native or docker)" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

if [[ "$MODE" == "docker" ]]; then
  cd "$repo_root"
  echo "Starting backend + dashboard via Docker Compose..."
  docker compose up -d --build
  echo "Dashboard: http://127.0.0.1:3000"
  echo "Backend:   http://127.0.0.1:8000"
  if [[ "$START_FLUTTER" -eq 1 ]]; then
    echo "Flutter is not started in docker mode. Use scripts/start_mobile.sh instead."
  fi
  exit 0
fi

run_dir="$repo_root/.run"
log_dir="$run_dir/logs"
pid_file="$run_dir/web_be_fe.pids"
mkdir -p "$log_dir"

if [[ -f "$pid_file" ]]; then
  echo "Found existing PID file at $pid_file. Stop it before starting again." >&2
  exit 1
fi

backend_log="$log_dir/backend.log"
dashboard_log="$log_dir/dashboard.log"
flutter_log="$log_dir/flutter.log"

backend_reload_arg=""
if [[ "${BACKEND_RELOAD:-0}" == "1" ]]; then
  backend_reload_arg="--reload"
fi

dashboard_mode="${DASHBOARD_MODE:-dev}"
dashboard_port="${DASHBOARD_PORT:-3000}"

export BACKEND_PORT="${BACKEND_PORT:-${BACKEND_REST_PORT:-8000}}"

("$script_dir/start_backend.sh" ${backend_reload_arg:+$backend_reload_arg}) > "$backend_log" 2>&1 &
backend_pid=$!

("$script_dir/start_dashboard.sh" --mode "$dashboard_mode" --port "$dashboard_port") > "$dashboard_log" 2>&1 &
dashboard_pid=$!

if [[ "$START_FLUTTER" -eq 1 ]]; then
  if ! command -v flutter >/dev/null 2>&1; then
    echo "flutter not found in PATH. Install Flutter or run with --no-flutter." >&2
    exit 1
  fi
  flutter_device="${FLUTTER_DEVICE:-chrome}"
  flutter_args="${FLUTTER_ARGS:-}"

  (cd "$repo_root/mobile-app" && flutter run -d "$flutter_device" $flutter_args) > "$flutter_log" 2>&1 &
  flutter_pid=$!
fi

{
  echo "backend $backend_pid"
  echo "dashboard $dashboard_pid"
  if [[ "$START_FLUTTER" -eq 1 ]]; then
    echo "flutter $flutter_pid"
  fi
} > "$pid_file"

echo "Started backend and dashboard in background."
if [[ "$START_FLUTTER" -eq 1 ]]; then
  echo "Flutter: running on device ${FLUTTER_DEVICE:-chrome}"
fi
echo "Dashboard: http://127.0.0.1:$dashboard_port"
echo "Backend:   http://127.0.0.1:${BACKEND_REST_PORT:-8000}"
echo "Logs:"
echo "- $backend_log"
echo "- $dashboard_log"
if [[ "$START_FLUTTER" -eq 1 ]]; then
  echo "- $flutter_log"
fi
