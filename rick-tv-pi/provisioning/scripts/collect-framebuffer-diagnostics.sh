#!/usr/bin/env bash
set -euo pipefail

DRY_RUN="${RICK_TV_DIAGNOSTICS_DRY_RUN:-0}"
HOST="${PI_HOST:-pi@192.168.1.68}"
OUTPUT_DIR=""
SINCE="today"
IDENTITY_FILE="${PI_IDENTITY_FILE:-}"

usage() {
  cat <<'EOF'
Usage:
  collect-framebuffer-diagnostics.sh [--host pi@192.168.1.68] [--identity-file ~/.ssh/key] [--output-dir diagnostics/pi] [--since "2026-06-18 00:00:00"]

Collects Rick TV Pi framebuffer placeholder evidence over SSH:
service logs, supervisor logs, dmesg, fb0 metadata, playback command lines, and
installed videolooper override markers. The output is packaged as a local
rick-tv-framebuffer-diagnostics-*.tar.gz archive.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="${2:-}"; shift 2 ;;
    --identity-file) IDENTITY_FILE="${2:-}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --since) SINCE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

timestamp="$(date +%Y%m%d-%H%M%S)"
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="rick-tv-framebuffer-diagnostics-$timestamp"
fi
mkdir -p "$OUTPUT_DIR"
COMMANDS_FILE="$OUTPUT_DIR/commands.txt"
: > "$COMMANDS_FILE"

ssh_base=(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8)
if [[ -n "$IDENTITY_FILE" ]]; then
  ssh_base+=(-i "$IDENTITY_FILE")
fi
ssh_base+=("$HOST")

record_command() {
  local label="$1"
  local command="$2"
  printf '## %s\n%s\n\n' "$label" "$command" >> "$COMMANDS_FILE"
}

run_remote() {
  local label="$1"
  local output="$2"
  local command="$3"

  record_command "$label" "$command"
  if [[ "$DRY_RUN" == "1" ]]; then
    printf 'dry-run: %s\n' "$command" > "$OUTPUT_DIR/$output"
    return 0
  fi

  "${ssh_base[@]}" "$command" > "$OUTPUT_DIR/$output" 2>&1 || true
}

run_remote "host" "host.txt" \
  'hostname; date -Is; uptime; uname -a; who -b || true'
run_remote "rick-tv-pi service" "rick-tv-pi.service.txt" \
  "systemctl status rick-tv-pi.service --no-pager; journalctl -u rick-tv-pi.service --no-pager --since '$SINCE'"
run_remote "video_looper supervisor" "video-looper-supervisor.txt" \
  'sudo supervisorctl status video_looper; timeout 8 sudo supervisorctl tail -500 video_looper stdout || true; timeout 8 sudo supervisorctl tail -500 video_looper stderr || true'
run_remote "kernel messages" "dmesg.txt" \
  'sudo dmesg --ctime || sudo dmesg'
run_remote "framebuffer metadata" "fb0.txt" \
  'for path in /sys/class/graphics/fb0/virtual_size /sys/class/graphics/fb0/stride /sys/class/graphics/fb0/bits_per_pixel /sys/class/graphics/fb0/modes /sys/class/graphics/fb0/name; do printf "%s=" "$path"; cat "$path" 2>/dev/null || true; done'
run_remote "playback process command lines" "processes.txt" \
  'ps -ef | grep -E "omxplayer|video_looper|rick_tv_pi" | grep -v grep || true; for pid in $(pgrep -f "omxplayer|video_looper|rick_tv_pi" || true); do printf "\n/proc/%s/cmdline: " "$pid"; tr "\0" " " < "/proc/$pid/cmdline" 2>/dev/null || true; done'
run_remote "installed videolooper override markers" "videolooper-override.txt" \
  'python3 - <<'"'"'PY'"'"'
import zipfile
path = "/usr/local/lib/python3.7/dist-packages/Adafruit_Video_Looper-1.0.21-py3.7.egg"
markers = [
    "Rick TV FIFO command received",
    "Rick TV same-channel playlist refresh; transition placeholder suppressed",
    "Rick TV showing transition placeholder",
    "Rick TV showing interstitial ad",
    "if self._osd and pygame.get_init():",
]
try:
    with zipfile.ZipFile(path) as egg:
        source = egg.read("Adafruit_Video_Looper/video_looper.py").decode("utf-8")
except Exception as exc:
    print(f"cannot read {path}: {exc}")
else:
    print(path)
    for marker in markers:
        print(f"{marker}: {marker in source}")
PY'
run_remote "sanitized pi env" "rick-tv-pi-env.redacted.txt" \
  "if [ -f /etc/rick-tv-pi.env ]; then sudo sed -E 's/(TOKEN|PASSWORD|PSK|KEY)=.*/\\1=<redacted>/' /etc/rick-tv-pi.env; fi"

archive="$OUTPUT_DIR.tar.gz"
tar -czf "$archive" -C "$(dirname "$OUTPUT_DIR")" "$(basename "$OUTPUT_DIR")"
printf 'Wrote %s\n' "$archive"
