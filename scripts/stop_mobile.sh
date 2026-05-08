#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
run_dir="$repo_root/.run"
pid_file="$run_dir/mobile_be_fe.pids"

if [[ ! -f "$pid_file" ]]; then
  echo "No PID file found at $pid_file. Nothing to stop."
  exit 0
fi

stop_pid() {
  local name="$1"
  local pid="$2"
  if [[ -z "$pid" ]]; then
    return
  fi
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name (pid $pid)"
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  else
    echo "$name (pid $pid) is not running"
  fi
}

while read -r name pid; do
  stop_pid "$name" "$pid"
done < "$pid_file"

rm -f "$pid_file"
