#!/usr/bin/env bash
set -euo pipefail

ROOT="${RICK_TV_FIRSTBOOT_ROOT:-}"
BOOT_OVERRIDE="${RICK_TV_FIRSTBOOT_BOOT:-}"
DRY_RUN="${RICK_TV_FIRSTBOOT_DRY_RUN:-0}"

target_path() {
  printf '%s%s\n' "$ROOT" "$1"
}

log() {
  printf '[rick-tv-firstboot] %s\n' "$*"
}

run_cmd() {
  if [[ "$DRY_RUN" == "1" ]]; then
    log "dry-run: $*"
    return 0
  fi
  "$@"
}

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

find_boot_config() {
  local candidate
  if [[ -n "$BOOT_OVERRIDE" ]]; then
    candidate="$BOOT_OVERRIDE/rick-tv.env"
    [[ -f "$candidate" ]] && printf '%s\n' "$candidate"
    return 0
  fi

  for candidate in \
    "$(target_path /boot/rick-tv.env)" \
    "$(target_path /boot/firmware/rick-tv.env)"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
}

write_runtime_env() {
  local env_file tmp name value
  env_file="$(target_path /etc/rick-tv-pi.env)"
  tmp="$(mktemp)"
  local names=(
    RICK_TV_SERVER_URL
    RICK_TV_API_TOKEN
    RICK_TV_MEDIA_ROOT
    RICK_TV_METADATA_PATH
    RICK_TV_POLL_INTERVAL_SECONDS
    RICK_TV_REMOTE_POLL_INTERVAL_SECONDS
    RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT
    RICK_TV_VIDEOLOOPER_COMMAND_PATH
    RICK_TV_CHANNEL_SHUFFLE_SECONDS
    RICK_TV_TOUCH_SCREEN_WIDTH
    RICK_TV_TOUCH_SCREEN_HEIGHT
    RICK_TV_TOUCH_SWAP_AXES
    RICK_TV_TOUCH_GESTURE_HORIZONTAL_AXIS
    RICK_TV_TOUCH_INVERT_X
    RICK_TV_TOUCH_INVERT_Y
    RICK_TV_TOUCH_DEVICE
    RICK_TV_RUNTIME_TICK_SECONDS
  )

  for name in "${names[@]}"; do
    if [[ -v "$name" ]]; then
      value="${!name}"
      printf '%s=%s\n' "$name" "$value" >> "$tmp"
    fi
  done

  if [[ ! -s "$tmp" ]]; then
    rm -f "$tmp"
    log "no RICK_TV_* runtime values in boot config"
    return 0
  fi

  mkdir -p "$(dirname "$env_file")"
  if [[ -f "$env_file" && "${RICK_TV_OVERWRITE_ENV:-false}" != "true" ]]; then
    rm -f "$tmp"
    log "$env_file exists; preserving it"
    return 0
  fi

  install -m 0600 "$tmp" "$env_file"
  rm -f "$tmp"
  log "wrote $env_file"
}

configure_wifi() {
  if [[ -z "${WIFI_SSID:-}" || -z "${WIFI_PSK:-}" ]]; then
    log "Wi-Fi credentials not provided"
    return 0
  fi

  local wifi_file
  wifi_file="$(target_path /etc/wpa_supplicant/wpa_supplicant.conf)"
  mkdir -p "$(dirname "$wifi_file")"
  cat > "$wifi_file" <<EOF
country=${WIFI_COUNTRY:-UA}
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="${WIFI_SSID}"
    psk="${WIFI_PSK}"
    key_mgmt=WPA-PSK
}
EOF
  chmod 0600 "$wifi_file"
  log "wrote Wi-Fi config"
}

configure_hostname() {
  if [[ -z "${RICK_TV_HOSTNAME:-}" ]]; then
    return 0
  fi

  printf '%s\n' "$RICK_TV_HOSTNAME" > "$(target_path /etc/hostname)"
  if [[ -f "$(target_path /etc/hosts)" ]]; then
    sed -i "s/127\\.0\\.1\\.1.*/127.0.1.1\t${RICK_TV_HOSTNAME}/" "$(target_path /etc/hosts)"
  fi
  run_cmd hostnamectl set-hostname "$RICK_TV_HOSTNAME"
  log "configured hostname $RICK_TV_HOSTNAME"
}

configure_ssh() {
  if truthy "${SSH_ENABLE:-false}"; then
    run_cmd systemctl enable --now ssh
  fi

  if [[ -n "${SSH_AUTHORIZED_KEY:-}" ]]; then
    local ssh_dir auth_keys
    ssh_dir="$(target_path /home/pi/.ssh)"
    auth_keys="$ssh_dir/authorized_keys"
    mkdir -p "$ssh_dir"
    touch "$auth_keys"
    grep -qxF "$SSH_AUTHORIZED_KEY" "$auth_keys" || printf '%s\n' "$SSH_AUTHORIZED_KEY" >> "$auth_keys"
    chmod 0700 "$ssh_dir"
    chmod 0600 "$auth_keys"
    if [[ "$DRY_RUN" != "1" ]]; then
      chown -R pi:pi "$ssh_dir"
    fi
    log "installed SSH authorized key"
  fi

  if [[ -n "${SSH_PASSWORD:-${PI_PASSWORD:-}}" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      log "dry-run: would set pi password"
    else
      printf 'pi:%s\n' "${SSH_PASSWORD:-${PI_PASSWORD:-}}" | chpasswd
    fi
  fi
}

install_rick_tv_runtime() {
  local source_root
  source_root="${RICK_TV_SOURCE_ROOT:-$(target_path /opt/rick-tv-src)}"

  mkdir -p \
    "$(target_path /home/pi/rick-tv/media)" \
    "$(target_path /home/pi/rick-tv/playlists)" \
    "$(target_path /home/pi/rick-tv/system)" \
    "$(target_path /home/pi/rick-tv/config)"

  if [[ -f "$source_root/rick-tv-pi/systemd/rick-tv-pi.service" ]]; then
    install -m 0644 \
      "$source_root/rick-tv-pi/systemd/rick-tv-pi.service" \
      "$(target_path /etc/systemd/system/rick-tv-pi.service)"
  fi

  if [[ -d "$source_root/rick-tv-pi/provisioning/videolooper/assets" ]]; then
    install -m 0644 \
      "$source_root/rick-tv-pi/provisioning/videolooper/assets/transition-placeholder.fb" \
      "$(target_path /home/pi/rick-tv/system/transition-placeholder.fb)"
    install -m 0644 \
      "$source_root/rick-tv-pi/provisioning/videolooper/assets/interstitial-ad.fb" \
      "$(target_path /home/pi/rick-tv/system/interstitial-ad.fb)"
  fi

  if [[ "$DRY_RUN" != "1" && -f "$source_root/rick-tv-pi/provisioning/videolooper/configure_rick_tv_videolooper.py" ]]; then
    python3 "$source_root/rick-tv-pi/provisioning/videolooper/configure_rick_tv_videolooper.py"
    python3 "$source_root/rick-tv-pi/provisioning/videolooper/rick_tv_fifo_patch.py"
    python3 "$source_root/rick-tv-pi/provisioning/videolooper/generate_channel_playlists.py" || true
  fi

  if [[ "$DRY_RUN" != "1" ]]; then
    chown -R pi:pi "$(target_path /home/pi/rick-tv)"
  fi

  run_cmd systemctl daemon-reload
  run_cmd systemctl enable rick-tv-pi.service
  run_cmd supervisorctl restart video_looper
  log "Rick TV runtime verified"
}

main() {
  local state_dir marker config
  state_dir="$(target_path /var/lib/rick-tv-pi)"
  marker="$state_dir/firstboot.done"

  if [[ -f "$marker" ]]; then
    log "first boot already applied"
    return 0
  fi

  config="$(find_boot_config || true)"
  if [[ -z "$config" ]]; then
    log "no boot config found; add rick-tv.env to the boot partition"
    return 0
  fi

  set -a
  # shellcheck disable=SC1090
  . "$config"
  set +a

  write_runtime_env
  configure_wifi
  configure_hostname
  configure_ssh
  install_rick_tv_runtime

  mkdir -p "$state_dir"
  date -u +'%Y-%m-%dT%H:%M:%SZ' > "$marker"
  log "first boot setup complete"
}

main "$@"
