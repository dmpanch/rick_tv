#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PI_HOST="${PI_HOST:-pi@192.168.1.68}"
PI_PASSWORD="${PI_PASSWORD:-video}"
REMOTE_SRC="/opt/rick-tv-src"
REMOTE_VENV="/opt/rick-tv-pi/.venv"
REMOTE_TMP="/tmp/rick-tv-deploy"
PI_PROVISIONING="rick-tv-pi/provisioning"
VIDEOLOOPER_PROVISIONING="$PI_PROVISIONING/videolooper"
VIDEOLOOPER_OVERRIDES="$VIDEOLOOPER_PROVISIONING/overrides"
VIDEOLOOPER_INSTALLER="$VIDEOLOOPER_PROVISIONING/rick_tv_fifo_patch.py"
TRANSITION_FRAME="$VIDEOLOOPER_PROVISIONING/assets/transition-placeholder.fb"
INTERSTITIAL_FRAME="$VIDEOLOOPER_PROVISIONING/assets/interstitial-ad.fb"

usage() {
  cat <<'EOF'
Usage:
  deploy_videolooper_image.sh deploy [--host pi@192.168.1.68] [--password video]
  deploy_videolooper_image.sh wifi --boot /Volumes/boot --ssid WIFI_SSID --psk WIFI_PASSWORD [--country UA]

Environment:
  PI_HOST       SSH target for deploy mode. Default: pi@192.168.1.68
  PI_PASSWORD   SSH password for deploy mode. Default: video

Notes:
  - Target image is the prepared Buster/videolooper image.
  - Deploy installs packages only; it does not run apt upgrade.
  - Wi-Fi mode writes wpa_supplicant.conf to the mounted FAT boot partition.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

ssh_pi() {
  sshpass -p "$PI_PASSWORD" ssh -o StrictHostKeyChecking=no "$PI_HOST" "$@"
}

scp_pi() {
  sshpass -p "$PI_PASSWORD" scp -o StrictHostKeyChecking=no "$@"
}

write_wifi_bootstrap() {
  local boot_dir=""
  local ssid=""
  local psk=""
  local country="UA"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --boot) boot_dir="${2:-}"; shift 2 ;;
      --ssid) ssid="${2:-}"; shift 2 ;;
      --psk) psk="${2:-}"; shift 2 ;;
      --country) country="${2:-}"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown wifi option: $1" ;;
    esac
  done

  [[ -n "$boot_dir" ]] || die "--boot is required"
  [[ -n "$ssid" ]] || die "--ssid is required"
  [[ -n "$psk" ]] || die "--psk is required"
  [[ -d "$boot_dir" ]] || die "boot partition not found: $boot_dir"

  cat > "$boot_dir/wpa_supplicant.conf" <<EOF
country=${country}
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="${ssid}"
    psk="${psk}"
    key_mgmt=WPA-PSK
}
EOF

  touch "$boot_dir/ssh"
  echo "Wrote $boot_dir/wpa_supplicant.conf and enabled SSH marker."
}

package_project() {
  local archive="$1"
  tar \
    --exclude=".git" \
    --exclude=".venv" \
    --exclude="**/__pycache__" \
    --exclude="**/.DS_Store" \
    -czf "$archive" \
    -C "$ROOT_DIR" \
    .
}

validate_deploy_payload() {
  local required_paths=(
    "$VIDEOLOOPER_INSTALLER"
    "$VIDEOLOOPER_OVERRIDES/video_looper.py"
    "$VIDEOLOOPER_OVERRIDES/omxplayer.py"
    "$TRANSITION_FRAME"
    "$INTERSTITIAL_FRAME"
    "rick-tv-pi/systemd/rick-tv-pi.service"
    "rick-tv-pi/provisioning/rick-tv-pi.env.example"
  )

  local path
  for path in "${required_paths[@]}"; do
    [[ -f "$ROOT_DIR/$path" ]] || die "missing deploy payload file: $path"
  done
}

deploy() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --host) PI_HOST="${2:-}"; shift 2 ;;
      --password) PI_PASSWORD="${2:-}"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown deploy option: $1" ;;
    esac
  done

  require_cmd sshpass
  require_cmd scp
  require_cmd ssh
  require_cmd tar
  validate_deploy_payload

  local archive
  archive="$(mktemp -t rick-tv-src.XXXXXX.tar.gz)"
  package_project "$archive"

  ssh_pi "mkdir -p '$REMOTE_TMP'"
  scp_pi "$archive" "$PI_HOST:$REMOTE_TMP/rick-tv-src.tar.gz"
  rm -f "$archive"

  ssh_pi "cat > '$REMOTE_TMP/install.sh' <<'REMOTE'
set -euo pipefail

apt-get update
apt-get install -y --no-install-recommends python3-venv python3-pip python3-evdev

rm -rf /opt/rick-tv-src
mkdir -p /opt/rick-tv-src /home/pi/rick-tv/media /home/pi/rick-tv/playlists /home/pi/rick-tv/system
tar -xzf /tmp/rick-tv-deploy/rick-tv-src.tar.gz -C /opt/rick-tv-src
chown -R pi:pi /home/pi/rick-tv

python3 -m venv --system-site-packages /opt/rick-tv-pi/.venv
/opt/rick-tv-pi/.venv/bin/pip install --upgrade pip setuptools
/opt/rick-tv-pi/.venv/bin/pip install /opt/rick-tv-src/rick-tv-pi

if [ ! -f /etc/rick-tv-pi.env ]; then
  cp /opt/rick-tv-src/rick-tv-pi/provisioning/rick-tv-pi.env.example /etc/rick-tv-pi.env
fi

cp /opt/rick-tv-src/rick-tv-pi/systemd/rick-tv-pi.service /etc/systemd/system/rick-tv-pi.service
python3 /opt/rick-tv-src/rick-tv-pi/provisioning/videolooper/configure_rick_tv_videolooper.py
echo "Installing pinned Rick TV pi_video_looper overrides"
python3 /opt/rick-tv-src/rick-tv-pi/provisioning/videolooper/rick_tv_fifo_patch.py
cp /opt/rick-tv-src/rick-tv-pi/provisioning/videolooper/assets/transition-placeholder.fb /home/pi/rick-tv/system/transition-placeholder.fb
cp /opt/rick-tv-src/rick-tv-pi/provisioning/videolooper/assets/interstitial-ad.fb /home/pi/rick-tv/system/interstitial-ad.fb
python3 /opt/rick-tv-src/rick-tv-pi/provisioning/videolooper/generate_channel_playlists.py || true

systemctl daemon-reload
systemctl enable rick-tv-pi.service
supervisorctl restart video_looper
systemctl restart rick-tv-pi.service
REMOTE
printf '%s\n' '$PI_PASSWORD' | sudo -S bash '$REMOTE_TMP/install.sh'"
}

main() {
  local command="${1:-}"
  case "$command" in
    deploy) shift; deploy "$@" ;;
    wifi) shift; write_wifi_bootstrap "$@" ;;
    -h|--help|"") usage ;;
    *) die "unknown command: $command" ;;
  esac
}

main "$@"
