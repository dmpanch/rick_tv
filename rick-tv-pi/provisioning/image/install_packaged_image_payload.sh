#!/usr/bin/env bash
set -euo pipefail

DEFAULT_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  install_packaged_image_payload.sh --rootfs /mnt/rick-tv-root --bootfs /mnt/rick-tv-boot [--source-root /path/to/repo] [--boot-config rick-tv.env]

Stages Rick TV source, first-boot service, and rick-tv.env.example into a
mounted known-good Raspberry Pi OS Legacy/videolooper image.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

ROOTFS=""
BOOTFS=""
ROOT_DIR="$DEFAULT_ROOT_DIR"
BOOT_CONFIG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rootfs) ROOTFS="${2:-}"; shift 2 ;;
    --bootfs) BOOTFS="${2:-}"; shift 2 ;;
    --source-root) ROOT_DIR="${2:-}"; shift 2 ;;
    --boot-config) BOOT_CONFIG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

PROVISIONING_DIR="$ROOT_DIR/rick-tv-pi/provisioning"
FIRSTBOOT_DIR="$PROVISIONING_DIR/firstboot"
FIRSTBOOT_EXAMPLE="$PROVISIONING_DIR/rick-tv.env.example"
DISPLAY_CONFIG="$PROVISIONING_DIR/display/config.txt.waveshare-28dpi-legacy"
DISPLAY_OVERLAY_DIR="$PROVISIONING_DIR/vendor/waveshare-28dpi/overlays"
DISPLAY_CONFIG_MARKER="# Rick TV Waveshare 2.8inch DPI LCD"
RICK_TV_SERVICE="$ROOT_DIR/rick-tv-pi/systemd/rick-tv-pi.service"
VIDEOLOOPER_CONFIGURER="$PROVISIONING_DIR/videolooper/configure_rick_tv_videolooper.py"
VIDEOLOOPER_PATCHER="$PROVISIONING_DIR/videolooper/rick_tv_fifo_patch.py"
VIDEOLOOPER_PLAYLIST_GENERATOR="$PROVISIONING_DIR/videolooper/generate_channel_playlists.py"
VIDEOLOOPER_ASSET_DIR="$PROVISIONING_DIR/videolooper/assets"
VIDEOLOOPER_EGG="$ROOTFS/usr/local/lib/python3.7/dist-packages/Adafruit_Video_Looper-1.0.21-py3.7.egg"
RECOVERY_SCRIPT="$PROVISIONING_DIR/scripts/configure-pi-recovery.sh"
LOGGING_SCRIPT="$PROVISIONING_DIR/scripts/configure-pi-logging.sh"

apply_waveshare_display_boot_config() {
  local config_file="$BOOTFS/config.txt"

  [[ -f "$DISPLAY_CONFIG" ]] || die "missing Waveshare display config"
  [[ -d "$DISPLAY_OVERLAY_DIR" ]] || die "missing Waveshare overlay directory"

  mkdir -p "$BOOTFS/overlays"
  cp "$DISPLAY_OVERLAY_DIR"/*.dtbo "$BOOTFS/overlays/"

  touch "$config_file"
  sed -i -E \
    -e 's/^([[:space:]]*)dtoverlay=vc4-kms-v3d([[:space:]]*)$/# \1dtoverlay=vc4-kms-v3d\2 # disabled by Rick TV Waveshare DPI config/' \
    -e 's/^([[:space:]]*)dtoverlay=vc4-fkms-v3d([[:space:]]*)$/# \1dtoverlay=vc4-fkms-v3d\2 # disabled by Rick TV Waveshare DPI config/' \
    "$config_file"

  if ! grep -qxF "$DISPLAY_CONFIG_MARKER" "$config_file"; then
    {
      printf '\n%s\n' "$DISPLAY_CONFIG_MARKER"
      cat "$DISPLAY_CONFIG"
      printf '# End Rick TV Waveshare 2.8inch DPI LCD\n'
    } >> "$config_file"
  fi
}

apply_videolooper_boot_config() {
  local config_file="$BOOTFS/video_looper.ini"

  [[ -f "$VIDEOLOOPER_CONFIGURER" ]] || die "missing videolooper config script"
  touch "$config_file"
  RICK_TV_VIDEOLOOPER_CONFIG_PATH="$config_file" python3 "$VIDEOLOOPER_CONFIGURER"
}

stage_rick_tv_runtime_payload() {
  mkdir -p \
    "$ROOTFS/etc/systemd/system" \
    "$ROOTFS/home/pi/rick-tv/media" \
    "$ROOTFS/home/pi/rick-tv/playlists" \
    "$ROOTFS/home/pi/rick-tv/system" \
    "$ROOTFS/home/pi/rick-tv/config"

  install -m 0644 "$RICK_TV_SERVICE" "$ROOTFS/etc/systemd/system/rick-tv-pi.service"
  install -m 0644 \
    "$VIDEOLOOPER_ASSET_DIR/transition-placeholder.fb" \
    "$ROOTFS/home/pi/rick-tv/system/transition-placeholder.fb"
  install -m 0644 \
    "$VIDEOLOOPER_ASSET_DIR/interstitial-ad.fb" \
    "$ROOTFS/home/pi/rick-tv/system/interstitial-ad.fb"

  if [[ -f "$VIDEOLOOPER_EGG" ]]; then
    RICK_TV_VIDEOLOOPER_EGG_PATH="$VIDEOLOOPER_EGG" python3 "$VIDEOLOOPER_PATCHER"
  else
    echo "warning: pi_video_looper egg not found in image; skipping patch: $VIDEOLOOPER_EGG" >&2
  fi

  RICK_TV_MEDIA_ROOT="$ROOTFS/home/pi/rick-tv/media" \
    RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT="$ROOTFS/home/pi/rick-tv/playlists" \
    python3 "$VIDEOLOOPER_PLAYLIST_GENERATOR"

  RICK_TV_RECOVERY_ROOT="$ROOTFS" \
    RICK_TV_RECOVERY_BOOT="$BOOTFS" \
    bash "$RECOVERY_SCRIPT"

  RICK_TV_LOGGING_ROOT="$ROOTFS" \
    bash "$LOGGING_SCRIPT"

  chown -R 1000:1000 "$ROOTFS/home/pi/rick-tv" 2>/dev/null || true
}

[[ -n "$ROOTFS" ]] || die "--rootfs is required"
[[ -n "$BOOTFS" ]] || die "--bootfs is required"
[[ -d "$ROOT_DIR" ]] || die "source root path not found: $ROOT_DIR"
[[ -d "$ROOTFS" ]] || die "rootfs path not found: $ROOTFS"
[[ -d "$BOOTFS" ]] || die "bootfs path not found: $BOOTFS"
[[ -f "$FIRSTBOOT_DIR/rick-tv-firstboot.sh" ]] || die "missing firstboot script"
[[ -f "$FIRSTBOOT_DIR/rick-tv-firstboot.service" ]] || die "missing firstboot service"
[[ -f "$FIRSTBOOT_EXAMPLE" ]] || die "missing firstboot env example"
[[ -f "$DISPLAY_CONFIG" ]] || die "missing Waveshare display config"
[[ -d "$DISPLAY_OVERLAY_DIR" ]] || die "missing Waveshare overlay directory"
[[ -f "$RICK_TV_SERVICE" ]] || die "missing Rick TV service unit"
[[ -f "$VIDEOLOOPER_CONFIGURER" ]] || die "missing videolooper config script"
[[ -f "$VIDEOLOOPER_PATCHER" ]] || die "missing videolooper patcher"
[[ -f "$VIDEOLOOPER_PLAYLIST_GENERATOR" ]] || die "missing playlist generator"
[[ -f "$VIDEOLOOPER_ASSET_DIR/transition-placeholder.fb" ]] || die "missing transition placeholder"
[[ -f "$VIDEOLOOPER_ASSET_DIR/interstitial-ad.fb" ]] || die "missing interstitial placeholder"
[[ -f "$RECOVERY_SCRIPT" ]] || die "missing recovery config script"
[[ -f "$LOGGING_SCRIPT" ]] || die "missing SD-safe logging config script"
if [[ -n "$BOOT_CONFIG" && ! -f "$BOOT_CONFIG" ]]; then
  die "boot config not found: $BOOT_CONFIG"
fi

mkdir -p \
  "$ROOTFS/usr/local/sbin" \
  "$ROOTFS/etc/systemd/system/multi-user.target.wants" \
  "$ROOTFS/opt/rick-tv-src" \
  "$BOOTFS"

install -m 0755 "$FIRSTBOOT_DIR/rick-tv-firstboot.sh" "$ROOTFS/usr/local/sbin/rick-tv-firstboot"
install -m 0644 "$FIRSTBOOT_DIR/rick-tv-firstboot.service" "$ROOTFS/etc/systemd/system/rick-tv-firstboot.service"
ln -sfn ../rick-tv-firstboot.service \
  "$ROOTFS/etc/systemd/system/multi-user.target.wants/rick-tv-firstboot.service"
install -m 0644 "$FIRSTBOOT_EXAMPLE" "$BOOTFS/rick-tv.env.example"
if [[ -n "$BOOT_CONFIG" ]]; then
  install -m 0600 "$BOOT_CONFIG" "$BOOTFS/rick-tv.env"
fi
apply_waveshare_display_boot_config
apply_videolooper_boot_config
stage_rick_tv_runtime_payload

tar \
  --exclude=".git" \
  --exclude=".venv" \
  --exclude=".env" \
  --exclude="**/.env" \
  --exclude="**/*.sqlite3" \
  --exclude=".pytest_cache" \
  --exclude=".mypy_cache" \
  --exclude=".ruff_cache" \
  --exclude="dist" \
  --exclude="*.img" \
  --exclude="*.zip" \
  --exclude="**/__pycache__" \
  --exclude="**/.DS_Store" \
  --exclude="rick-tv-server/.env" \
  --exclude="rick-tv-server/data" \
  --exclude="rick-tv-server/media" \
  --exclude="rick-tv-server/config" \
  --exclude="rick-tv-server/state" \
  --exclude="manual-test-videos" \
  -cf - \
  -C "$ROOT_DIR" \
  . | tar -xf - -C "$ROOTFS/opt/rick-tv-src"

echo "Rick TV packaged-image payload staged."
echo "Copy $BOOTFS/rick-tv.env.example to $BOOTFS/rick-tv.env and fill in secrets before first boot."
