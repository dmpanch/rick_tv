#!/usr/bin/env bash
set -euo pipefail

ROOT="${RICK_TV_RECOVERY_ROOT:-}"
BOOT="${RICK_TV_RECOVERY_BOOT:-}"
DRY_RUN="${RICK_TV_RECOVERY_DRY_RUN:-0}"

target_path() {
  printf '%s%s\n' "$ROOT" "$1"
}

log() {
  printf '[rick-tv-recovery] %s\n' "$*"
}

find_command() {
  local candidate
  for candidate in "$@"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

boot_file() {
  local name="$1"
  local candidate

  if [[ -n "$BOOT" ]]; then
    printf '%s/%s\n' "${BOOT%/}" "$name"
    return 0
  fi

  for candidate in "$(target_path /boot/$name)" "$(target_path /boot/firmware/$name)"; do
    if [[ -e "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  printf '%s\n' "$(target_path /boot/$name)"
}

write_panic_sysctl() {
  local path
  path="$(target_path /etc/sysctl.d/99-rick-tv-panic.conf)"
  mkdir -p "$(dirname "$path")"
  cat > "$path" <<'EOF'
kernel.panic=10
kernel.panic_on_oops=1
EOF
  log "installed panic sysctl config: $path"
}

write_systemd_watchdog() {
  local path
  path="$(target_path /etc/systemd/system.conf.d/10-rick-tv-watchdog.conf)"
  mkdir -p "$(dirname "$path")"
  cat > "$path" <<'EOF'
[Manager]
RuntimeWatchdogSec=15s
ShutdownWatchdogSec=2min
EOF
  log "installed systemd watchdog config: $path"
}

ensure_cmdline_panic() {
  local path content
  path="$(boot_file cmdline.txt)"
  mkdir -p "$(dirname "$path")"

  if [[ -f "$path" ]]; then
    content="$(tr '\n' ' ' < "$path" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"
  else
    content=""
  fi

  if [[ " $content " != *" panic=10 "* ]]; then
    if [[ -n "$content" ]]; then
      content="$content panic=10"
    else
      content="panic=10"
    fi
  fi

  printf '%s\n' "$content" > "$path"
  log "ensured panic=10 in $path"
}

ensure_watchdog_dtparam() {
  local path
  path="$(boot_file config.txt)"
  mkdir -p "$(dirname "$path")"
  touch "$path"

  if grep -qxF "dtparam=watchdog=on" "$path"; then
    log "watchdog dtparam already present in $path"
    return 0
  fi

  if [[ -s "$path" && "$(tail -c 1 "$path")" != "" ]]; then
    printf '\n' >> "$path"
  fi
  printf '\n# Rick TV recovery watchdog\ndtparam=watchdog=on\n' >> "$path"
  log "enabled watchdog dtparam in $path"
}

apply_live_config() {
  local sysctl_cmd systemctl_cmd

  if [[ -n "$ROOT" || "$DRY_RUN" == "1" ]]; then
    log "skipping live sysctl/systemd apply for offline or dry-run root"
    return 0
  fi

  if sysctl_cmd="$(find_command sysctl /sbin/sysctl /usr/sbin/sysctl)"; then
    "$sysctl_cmd" --system >/dev/null || log "sysctl --system failed; settings will apply after reboot"
  fi
  if systemctl_cmd="$(find_command systemctl /bin/systemctl /usr/bin/systemctl)"; then
    "$systemctl_cmd" daemon-reexec || log "systemctl daemon-reexec failed; watchdog manager config will apply after reboot"
  fi
}

main() {
  write_panic_sysctl
  ensure_cmdline_panic
  ensure_watchdog_dtparam
  write_systemd_watchdog
  apply_live_config
  log "one controlled reboot is required for boot-level panic/watchdog settings"
}

main "$@"
