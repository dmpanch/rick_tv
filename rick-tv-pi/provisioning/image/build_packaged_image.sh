#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
IMAGE_DIR="$ROOT_DIR/rick-tv-pi/provisioning/image"
SDM_PHASE_SCRIPT="$IMAGE_DIR/sdm_rick_tv_custom_phase.sh"
DRY_RUN="${RICK_TV_IMAGE_BUILDER_DRY_RUN:-0}"
DEFAULT_BASE_IMAGE_URL="https://videolooper.de/video_looper_v2.11.zip"

usage() {
  cat <<'EOF'
Usage:
  build_packaged_image.sh --base-image base.img --output-image rick-tv.img [--boot-config rick-tv.env]
  build_packaged_image.sh --base-image-url https://videolooper.de/video_looper_v2.11.zip --output-image rick-tv.img [--boot-config rick-tv.env]

Builds a Rick TV Raspberry Pi image from the videolooper.de base image using
gitbls/sdm. The generated image contains Rick TV software and placeholder
first-boot config only. Keep filled rick-tv.env files out of git.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

log() {
  printf '%s\n' "$*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

write_sha256() {
  local image="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$image" > "$image.sha256"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$image" > "$image.sha256"
  else
    die "missing command: sha256sum or shasum"
  fi
}

find_sdm() {
  if [[ -n "${RICK_TV_SDM_BIN:-}" ]]; then
    printf '%s\n' "$RICK_TV_SDM_BIN"
    return 0
  fi
  if command -v sdm >/dev/null 2>&1; then
    command -v sdm
    return 0
  fi
  if [[ -x /usr/local/sdm/sdm ]]; then
    printf '%s\n' /usr/local/sdm/sdm
    return 0
  fi
  return 1
}

is_zip() {
  case "$1" in
    *.[zZ][iI][pP]) return 0 ;;
    *) return 1 ;;
  esac
}

extract_base_image() {
  local archive="$1"
  local dest="$2"
  local found

  require_cmd unzip
  mkdir -p "$dest"
  unzip -q "$archive" -d "$dest"
  found="$(find "$dest" -type f -name '*.img' | sort | head -n 1)"
  [[ -n "$found" ]] || die "no .img found in archive: $archive"
  printf '%s\n' "$found"
}

copy_base_image() {
  local source_image="$1"
  local output_image="$2"

  mkdir -p "$(dirname "$output_image")"
  cp "$source_image" "$output_image"
  log "Copied $source_image to $output_image"
}

build_sdm_command_for_log() {
  local output_image="$1"
  local boot_config="$2"
  local boot_arg=""

  if [[ -n "$boot_config" ]]; then
    boot_arg=" --custom1 $boot_config"
  fi

  printf 'sudo sdm --customize --batch --redo-customize --apt-options none --cscript %s --csrc %s%s %s' \
    "$SDM_PHASE_SCRIPT" \
    "$ROOT_DIR" \
    "$boot_arg" \
    "$output_image"
}

run_sdm_customize() {
  local output_image="$1"
  local boot_config="$2"
  local sdm_bin
  local sudo_prefix=()
  local sdm_args=()

  sdm_bin="$(find_sdm)" || die "sdm not found; install with: curl -L https://raw.githubusercontent.com/gitbls/sdm/master/install-sdm | bash"
  if [[ "$(id -u)" != "0" ]]; then
    require_cmd sudo
    sudo_prefix=(sudo)
  fi

  sdm_args=(
    --customize
    --batch
    --redo-customize
    --apt-options none
    --cscript "$SDM_PHASE_SCRIPT"
    --csrc "$ROOT_DIR"
  )
  if [[ -n "$boot_config" ]]; then
    sdm_args+=(--custom1 "$boot_config")
  fi
  sdm_args+=("$output_image")

  "${sudo_prefix[@]}" "$sdm_bin" "${sdm_args[@]}"
}

preflight_sdm_customize() {
  find_sdm >/dev/null || die "sdm not found; install with: curl -L https://raw.githubusercontent.com/gitbls/sdm/master/install-sdm | bash"
  if [[ "$(id -u)" != "0" ]]; then
    require_cmd sudo
  fi
}

BASE_IMAGE=""
BASE_IMAGE_URL=""
OUTPUT_IMAGE=""
BOOT_CONFIG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-image) BASE_IMAGE="${2:-}"; shift 2 ;;
    --base-image-url) BASE_IMAGE_URL="${2:-}"; shift 2 ;;
    --output-image) OUTPUT_IMAGE="${2:-}"; shift 2 ;;
    --boot-config) BOOT_CONFIG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -n "$OUTPUT_IMAGE" ]] || die "--output-image is required"
[[ -f "$SDM_PHASE_SCRIPT" ]] || die "sdm custom phase script not found: $SDM_PHASE_SCRIPT"
if [[ -n "$BASE_IMAGE" && -n "$BASE_IMAGE_URL" ]]; then
  die "use only one of --base-image or --base-image-url"
fi
if [[ -z "$BASE_IMAGE" && -z "$BASE_IMAGE_URL" ]]; then
  BASE_IMAGE_URL="$DEFAULT_BASE_IMAGE_URL"
fi
if [[ -n "$BASE_IMAGE" && ! -f "$BASE_IMAGE" ]]; then
  die "base image not found: $BASE_IMAGE"
fi
if [[ -n "$BOOT_CONFIG" && ! -f "$BOOT_CONFIG" ]]; then
  die "boot config not found: $BOOT_CONFIG"
fi
if [[ "$DRY_RUN" != "1" ]]; then
  preflight_sdm_customize
fi

work_dir=""
cleanup() {
  if [[ -n "$work_dir" && -d "$work_dir" ]]; then
    rm -rf "$work_dir"
  fi
}
trap cleanup EXIT

source_image="$BASE_IMAGE"
if [[ -n "$BASE_IMAGE_URL" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    log "dry-run: would download $BASE_IMAGE_URL"
    log "dry-run: would extract downloaded base image archive"
    log "dry-run: would copy extracted base image to $OUTPUT_IMAGE"
    log "dry-run: would run $(build_sdm_command_for_log "$OUTPUT_IMAGE" "$BOOT_CONFIG")"
    exit 0
  fi

  require_cmd curl
  work_dir="$(mktemp -d)"
  archive_path="$work_dir/$(basename "$BASE_IMAGE_URL")"
  log "Downloading $BASE_IMAGE_URL"
  curl -fL "$BASE_IMAGE_URL" -o "$archive_path"
  source_image="$(extract_base_image "$archive_path" "$work_dir/extracted")"
fi

if [[ "$DRY_RUN" == "1" ]]; then
  if is_zip "$source_image"; then
    log "dry-run: would extract local base image archive $source_image"
    log "dry-run: would copy extracted base image to $OUTPUT_IMAGE"
  else
    copy_base_image "$source_image" "$OUTPUT_IMAGE"
    log "dry-run: would copy $source_image to $OUTPUT_IMAGE"
  fi
  log "dry-run: would run $(build_sdm_command_for_log "$OUTPUT_IMAGE" "$BOOT_CONFIG")"
  if [[ -f "$OUTPUT_IMAGE" ]]; then
    write_sha256 "$OUTPUT_IMAGE"
    log "Wrote $OUTPUT_IMAGE.sha256"
  fi
  exit 0
fi

if is_zip "$source_image"; then
  work_dir="${work_dir:-$(mktemp -d)}"
  source_image="$(extract_base_image "$source_image" "$work_dir/extracted-local")"
fi

copy_base_image "$source_image" "$OUTPUT_IMAGE"
run_sdm_customize "$OUTPUT_IMAGE" "$BOOT_CONFIG"
write_sha256 "$OUTPUT_IMAGE"
log "Built $OUTPUT_IMAGE"
log "Wrote $OUTPUT_IMAGE.sha256"
