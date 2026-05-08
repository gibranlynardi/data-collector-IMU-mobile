#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR=""
OUTPUT_DIR=""
RETENTION_DAYS=14

usage() {
  echo "Usage: backup_data.sh [--source-dir DIR] [--output-dir DIR] [--retention-days DAYS]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-dir)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --retention-days)
      RETENTION_DAYS="$2"
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

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

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

if [[ -z "$SOURCE_DIR" ]]; then
  SOURCE_DIR="${BACKUP_SOURCE_DIR:-./data}"
fi
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="${BACKUP_OUTPUT_DIR:-./backups}"
fi
if [[ -n "${BACKUP_RETENTION_DAYS:-}" ]]; then
  RETENTION_DAYS="${BACKUP_RETENTION_DAYS}"
fi

if [[ "$RETENTION_DAYS" -lt 0 ]]; then
  RETENTION_DAYS=0
fi

resolved_source="$(cd "$repo_root" && cd "$SOURCE_DIR" 2>/dev/null && pwd -P)"
if [[ -z "$resolved_source" || ! -d "$resolved_source" ]]; then
  echo "Source directory not found: $repo_root/$SOURCE_DIR" >&2
  exit 1
fi

mkdir -p "$repo_root/$OUTPUT_DIR"
resolved_output="$(cd "$repo_root" && cd "$OUTPUT_DIR" && pwd -P)"

timestamp="$(date +"%Y%m%d_%H%M%S")"
archive_name="imu_data_backup_${timestamp}.zip"
archive_path="$resolved_output/$archive_name"
stage_dir="$resolved_output/.stage_${timestamp}"

echo "Creating backup from $resolved_source"
mkdir -p "$stage_dir"

cleanup() {
  rm -rf "$stage_dir" 2>/dev/null || true
}
trap cleanup EXIT

sessions_dir="$resolved_source/sessions"
if [[ -d "$sessions_dir" ]]; then
  cp -R "$sessions_dir" "$stage_dir/sessions"
fi

metadata_db="$resolved_source/metadata.db"
if [[ -f "$metadata_db" ]]; then
  if ! cp "$metadata_db" "$stage_dir/metadata.db" 2>/dev/null; then
    echo "Warning: metadata.db is in use, backup continues without it." >&2
  fi
fi

if [[ -z "$(ls -A "$stage_dir")" ]]; then
  echo "No content to backup from $resolved_source" >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "zip not found. Install zip or adjust the script." >&2
  exit 1
fi

(cd "$stage_dir" && zip -r "$archive_path" . >/dev/null)

trap - EXIT
cleanup

find "$resolved_output" -name "imu_data_backup_*.zip" -type f -mtime +"$RETENTION_DAYS" -print -delete 2>/dev/null || true

echo "Backup complete: $archive_path"
