#!/bin/sh
set -eu

# Copy Waveshare 2.8inch DPI LCD vendor DTBO files to a mounted boot partition.
# Usage: ./copy-waveshare-overlays.sh /path/to/bootfs

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/bootfs" >&2
  exit 2
fi

BOOTFS="$1"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../vendor/waveshare-28dpi/overlays"

if [ ! -d "$BOOTFS" ]; then
  echo "Boot partition path not found: $BOOTFS" >&2
  exit 1
fi

mkdir -p "$BOOTFS/overlays"
cp "$SRC_DIR"/*.dtbo "$BOOTFS/overlays/"

echo "Copied Waveshare DTBO files to $BOOTFS/overlays"
