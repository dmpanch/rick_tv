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

[[ -n "$ROOTFS" ]] || die "--rootfs is required"
[[ -n "$BOOTFS" ]] || die "--bootfs is required"
[[ -d "$ROOT_DIR" ]] || die "source root path not found: $ROOT_DIR"
[[ -d "$ROOTFS" ]] || die "rootfs path not found: $ROOTFS"
[[ -d "$BOOTFS" ]] || die "bootfs path not found: $BOOTFS"
[[ -f "$FIRSTBOOT_DIR/rick-tv-firstboot.sh" ]] || die "missing firstboot script"
[[ -f "$FIRSTBOOT_DIR/rick-tv-firstboot.service" ]] || die "missing firstboot service"
[[ -f "$FIRSTBOOT_EXAMPLE" ]] || die "missing firstboot env example"
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
