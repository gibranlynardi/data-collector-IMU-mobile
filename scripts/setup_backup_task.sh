#!/usr/bin/env bash
set -euo pipefail

TASK_NAME="IMUCollectorDailyBackup"
RUN_AT="02:00"

usage() {
  echo "Usage: setup_backup_task.sh [--task-name NAME] [--run-at HH:MM]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-name)
      TASK_NAME="$2"
      shift 2
      ;;
    --run-at)
      RUN_AT="$2"
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

if [[ ! "$RUN_AT" =~ ^[0-9]{2}:[0-9]{2}$ ]]; then
  echo "Invalid time format: $RUN_AT (expected HH:MM)" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script_path="$script_dir/backup_data.sh"

if [[ ! -f "$script_path" ]]; then
  echo "Backup script not found: $script_path" >&2
  exit 1
fi

hour="${RUN_AT%:*}"
minute="${RUN_AT#*:}"

cron_comment="# $TASK_NAME"
cron_line="$minute $hour * * * bash \"$script_path\""

current_cron="$(crontab -l 2>/dev/null || true)"
filtered_cron="$(echo "$current_cron" | grep -v "$TASK_NAME" | grep -v "$script_path" || true)"

{
  if [[ -n "$filtered_cron" ]]; then
    echo "$filtered_cron"
  fi
  echo "$cron_comment"
  echo "$cron_line"
} | crontab -

echo "Cron backup task registered: $TASK_NAME (runs at $RUN_AT)"
