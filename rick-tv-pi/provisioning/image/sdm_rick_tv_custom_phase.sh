#!/usr/bin/env bash
set -euo pipefail

phase="${1:-}"

log() {
  if declare -F logtoboth >/dev/null 2>&1; then
    logtoboth "* rick-tv-sdm: $*"
  else
    printf '* rick-tv-sdm: %s\n' "$*"
  fi
}

die() {
  log "error: $*"
  exit 1
}

load_sdm_params() {
  if [[ -n "${SDMPT:-}" && -f "$SDMPT/etc/sdm/sdm-readparams" ]]; then
    # shellcheck disable=SC1091
    source "$SDMPT/etc/sdm/sdm-readparams"
  elif [[ -f /etc/sdm/sdm-readparams ]]; then
    # shellcheck disable=SC1091
    source /etc/sdm/sdm-readparams
  fi
}

find_bootfs() {
  local rootfs="$1"
  local candidate

  for candidate in "$rootfs/boot" "$rootfs/boot/firmware"; do
    if [[ -d "$candidate" && ( -f "$candidate/cmdline.txt" || -f "$candidate/config.txt" ) ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  for candidate in "$rootfs/boot" "$rootfs/boot/firmware"; do
    if [[ -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

run_phase0() {
  local source_root="${csrc:-${RICK_TV_SOURCE_ROOT:-}}"
  local boot_config="${custom1:-}"
  local rootfs="${SDMPT:-}"
  local bootfs
  local installer

  [[ -n "$rootfs" ]] || die "SDMPT is not set for Phase 0"
  [[ -d "$rootfs" ]] || die "SDMPT rootfs does not exist: $rootfs"
  [[ -n "$source_root" ]] || die "sdm --csrc is required"
  [[ -d "$source_root" ]] || die "source root not found: $source_root"

  bootfs="$(find_bootfs "$rootfs")" || die "boot partition mount not found under $rootfs"
  installer="$source_root/rick-tv-pi/provisioning/image/install_packaged_image_payload.sh"
  [[ -x "$installer" ]] || die "payload installer not found or not executable: $installer"

  if [[ -n "$boot_config" ]]; then
    "$installer" --source-root "$source_root" --rootfs "$rootfs" --bootfs "$bootfs" --boot-config "$boot_config"
  else
    "$installer" --source-root "$source_root" --rootfs "$rootfs" --bootfs "$bootfs"
  fi
}

load_sdm_params

case "$phase" in
  0)
    log "Phase 0 staging started"
    run_phase0
    log "Phase 0 staging completed"
    ;;
  1)
    log "Phase 1 skipped; Rick TV does not install secrets or packages here"
    ;;
  post-install)
    log "post-install skipped; firstboot applies runtime configuration"
    ;;
  *)
    die "unknown sdm phase: $phase"
    ;;
esac
