#!/usr/bin/env bash
set -euo pipefail

SESSION_ID=""
LOCAL_FILE=""
FAMS_HOST=""
FAMS_USER=""
REMOTE_PATH=""
SSH_KEY_PATH="${FAMS_SSH_KEY_PATH:-}"
RSYNC_EXECUTABLE="${RSYNC_EXECUTABLE:-rsync}"
SSH_EXECUTABLE="${SSH_EXECUTABLE:-ssh}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-id)
      SESSION_ID="$2"
      shift 2
      ;;
    --local-file)
      LOCAL_FILE="$2"
      shift 2
      ;;
    --fams-host)
      FAMS_HOST="$2"
      shift 2
      ;;
    --fams-user)
      FAMS_USER="$2"
      shift 2
      ;;
    --remote-path)
      REMOTE_PATH="$2"
      shift 2
      ;;
    --ssh-key-path)
      SSH_KEY_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$SESSION_ID" || -z "$LOCAL_FILE" || -z "$FAMS_HOST" || -z "$FAMS_USER" || -z "$REMOTE_PATH" ]]; then
  echo "Usage: upload_to_fams.sh --session-id ID --local-file FILE --fams-host HOST --fams-user USER --remote-path PATH [--ssh-key-path KEY]" >&2
  exit 2
fi

if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "Local file not found: $LOCAL_FILE" >&2
  exit 1
fi

LOCAL_CHECKSUM="$(sha256sum "$LOCAL_FILE" | awk '{print $1}')"
echo "[phase12] Local checksum: $LOCAL_CHECKSUM"

SSH_TARGET="${FAMS_USER}@${FAMS_HOST}"
REMOTE_DIR="$(dirname "$REMOTE_PATH")"

SSH_ARGS=()
if [[ -n "$SSH_KEY_PATH" ]]; then
  SSH_ARGS+=("-i" "$SSH_KEY_PATH")
fi

SSH_COMMAND="$SSH_EXECUTABLE ${SSH_ARGS[*]}"

"$RSYNC_EXECUTABLE" \
  -avzP \
  --partial \
  --append-verify \
  -e "$SSH_COMMAND" \
  "$LOCAL_FILE" \
  "$SSH_TARGET:$REMOTE_PATH"

"$SSH_EXECUTABLE" "${SSH_ARGS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_DIR'" >/dev/null
REMOTE_CHECKSUM="$($SSH_EXECUTABLE "${SSH_ARGS[@]}" "$SSH_TARGET" "sha256sum '$REMOTE_PATH' | awk '{print \\$1}'")"

if [[ "$REMOTE_CHECKSUM" != "$LOCAL_CHECKSUM" ]]; then
  echo "Checksum mismatch. local=$LOCAL_CHECKSUM remote=$REMOTE_CHECKSUM" >&2
  exit 1
fi

echo "[phase12] Upload OK for session $SESSION_ID"
echo "[phase12] Remote path: $REMOTE_PATH"
echo "[phase12] Checksum verified: $LOCAL_CHECKSUM"
