#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FIRSTBOOT_DIR="$ROOT_DIR/rick-tv-pi/provisioning/firstboot"

usage() {
  cat <<'EOF'
Usage:
  install_packaged_image_payload.sh --rootfs /mnt/rick-tv-root --bootfs /mnt/rick-tv-boot

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
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rootfs) ROOTFS="${2:-}"; shift 2 ;;
    --bootfs) BOOTFS="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -n "$ROOTFS" ]] || die "--rootfs is required"
[[ -n "$BOOTFS" ]] || die "--bootfs is required"
[[ -d "$ROOTFS" ]] || die "rootfs path not found: $ROOTFS"
[[ -d "$BOOTFS" ]] || die "bootfs path not found: $BOOTFS"
[[ -f "$FIRSTBOOT_DIR/rick-tv-firstboot.sh" ]] || die "missing firstboot script"
[[ -f "$FIRSTBOOT_DIR/rick-tv-firstboot.service" ]] || die "missing firstboot service"
[[ -f "$FIRSTBOOT_DIR/rick-tv.env.example" ]] || die "missing firstboot env example"

mkdir -p \
  "$ROOTFS/usr/local/sbin" \
  "$ROOTFS/etc/systemd/system/multi-user.target.wants" \
  "$ROOTFS/opt/rick-tv-src" \
  "$BOOTFS"

install -m 0755 "$FIRSTBOOT_DIR/rick-tv-firstboot.sh" "$ROOTFS/usr/local/sbin/rick-tv-firstboot"
install -m 0644 "$FIRSTBOOT_DIR/rick-tv-firstboot.service" "$ROOTFS/etc/systemd/system/rick-tv-firstboot.service"
ln -sfn ../rick-tv-firstboot.service \
  "$ROOTFS/etc/systemd/system/multi-user.target.wants/rick-tv-firstboot.service"
install -m 0644 "$FIRSTBOOT_DIR/rick-tv.env.example" "$BOOTFS/rick-tv.env.example"

tar \
  --exclude=".git" \
  --exclude=".venv" \
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
