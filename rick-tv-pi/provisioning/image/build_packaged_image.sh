#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
IMAGE_DIR="$ROOT_DIR/rick-tv-pi/provisioning/image"
PAYLOAD_INSTALLER="$IMAGE_DIR/install_packaged_image_payload.sh"
DRY_RUN="${RICK_TV_IMAGE_BUILDER_DRY_RUN:-0}"

usage() {
  cat <<'EOF'
Usage:
  build_packaged_image.sh --base-image base.img --output-image rick-tv.img [--boot-config rick-tv.env]

Copies a known-good Raspberry Pi OS Legacy/videolooper base image, mounts its
boot/root partitions through a loop device, stages Rick TV's packaged-image
payload, and writes rick-tv.img.sha256 next to the output image.

The optional --boot-config copies a local filled rick-tv.env onto the output
image boot partition. Do not commit filled config files.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

log() {
  printf '%s\n' "$*"
}

BASE_IMAGE=""
OUTPUT_IMAGE=""
BOOT_CONFIG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-image) BASE_IMAGE="${2:-}"; shift 2 ;;
    --output-image) OUTPUT_IMAGE="${2:-}"; shift 2 ;;
    --boot-config) BOOT_CONFIG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -n "$BASE_IMAGE" ]] || die "--base-image is required"
[[ -n "$OUTPUT_IMAGE" ]] || die "--output-image is required"
[[ -f "$BASE_IMAGE" ]] || die "base image not found: $BASE_IMAGE"
[[ -f "$PAYLOAD_INSTALLER" ]] || die "payload installer not found: $PAYLOAD_INSTALLER"
if [[ -n "$BOOT_CONFIG" && ! -f "$BOOT_CONFIG" ]]; then
  die "boot config not found: $BOOT_CONFIG"
fi

loop_device=""
work_dir=""
root_mount=""
boot_mount=""

cleanup() {
  local status=$?
  set +e
  if [[ -n "$boot_mount" && -d "$boot_mount" ]]; then
    mountpoint -q "$boot_mount" && umount "$boot_mount"
  fi
  if [[ -n "$root_mount" && -d "$root_mount" ]]; then
    mountpoint -q "$root_mount" && umount "$root_mount"
  fi
  if [[ -n "$loop_device" ]]; then
    losetup -d "$loop_device" >/dev/null 2>&1 || true
  fi
  if [[ -n "$work_dir" && -d "$work_dir" ]]; then
    rm -rf "$work_dir"
  fi
  exit "$status"
}
trap cleanup EXIT

mkdir -p "$(dirname "$OUTPUT_IMAGE")"
cp "$BASE_IMAGE" "$OUTPUT_IMAGE"
log "Copied $BASE_IMAGE to $OUTPUT_IMAGE"

if [[ "$DRY_RUN" == "1" ]]; then
  log "dry-run: would attach loop device with partitions using losetup --find --partscan --show $OUTPUT_IMAGE"
  log "dry-run: would mount root partition at a temporary rootfs directory"
  log "dry-run: would mount boot partition at a temporary bootfs directory"
  log "dry-run: would run install_packaged_image_payload.sh against mounted partitions"
  if [[ -n "$BOOT_CONFIG" ]]; then
    log "dry-run: would copy $BOOT_CONFIG to boot partition as rick-tv.env"
  fi
  sha256sum "$OUTPUT_IMAGE" > "$OUTPUT_IMAGE.sha256"
  log "Wrote $OUTPUT_IMAGE.sha256"
  exit 0
fi

for command in losetup mount umount sha256sum; do
  command -v "$command" >/dev/null 2>&1 || die "missing command: $command"
done

work_dir="$(mktemp -d)"
root_mount="$work_dir/rootfs"
boot_mount="$work_dir/bootfs"
mkdir -p "$root_mount" "$boot_mount"

loop_device="$(losetup --find --partscan --show "$OUTPUT_IMAGE")"
for _ in 1 2 3 4 5; do
  [[ -b "${loop_device}p1" && -b "${loop_device}p2" ]] && break
  sleep 1
done
[[ -b "${loop_device}p1" ]] || die "boot partition not found: ${loop_device}p1"
[[ -b "${loop_device}p2" ]] || die "root partition not found: ${loop_device}p2"

mount "${loop_device}p2" "$root_mount"
mount "${loop_device}p1" "$boot_mount"

"$PAYLOAD_INSTALLER" --rootfs "$root_mount" --bootfs "$boot_mount"
if [[ -n "$BOOT_CONFIG" ]]; then
  install -m 0600 "$BOOT_CONFIG" "$boot_mount/rick-tv.env"
fi

sync
umount "$boot_mount"
umount "$root_mount"
losetup -d "$loop_device"
loop_device=""

sha256sum "$OUTPUT_IMAGE" > "$OUTPUT_IMAGE.sha256"
log "Built $OUTPUT_IMAGE"
log "Wrote $OUTPUT_IMAGE.sha256"
