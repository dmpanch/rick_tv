#!/usr/bin/env bash
set -euo pipefail

ROOT="${RICK_TV_LOGGING_ROOT:-}"
DRY_RUN="${RICK_TV_LOGGING_DRY_RUN:-0}"

target_path() {
  printf '%s%s\n' "$ROOT" "$1"
}

log() {
  printf '[rick-tv-logging] %s\n' "$*"
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

write_journald_volatile_config() {
  local path
  path="$(target_path /etc/systemd/journald.conf.d/99-rick-tv-volatile.conf)"
  mkdir -p "$(dirname "$path")"
  cat > "$path" <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=16M
RuntimeMaxFileSize=4M
ForwardToSyslog=no
EOF
  log "installed volatile journald config: $path"
}

write_tmpfiles_config() {
  local path
  path="$(target_path /etc/tmpfiles.d/rick-tv-logs.conf)"
  mkdir -p "$(dirname "$path")"
  printf 'd /run/rick-tv-logs 0755 root root -\n' > "$path"
  mkdir -p "$(target_path /run/rick-tv-logs)"
  log "installed volatile log tmpfiles config: $path"
}

remove_persistent_journal() {
  rm -rf "$(target_path /var/log/journal)"
  log "removed persistent journal directory"
}

remove_sd_runtime_logs() {
  local log_root
  log_root="$(target_path /var/log)"
  rm -f \
    "$log_root"/auth.log "$log_root"/auth.log.* \
    "$log_root"/daemon.log "$log_root"/daemon.log.* \
    "$log_root"/debug "$log_root"/debug.* \
    "$log_root"/kern.log "$log_root"/kern.log.* \
    "$log_root"/messages "$log_root"/messages.* \
    "$log_root"/syslog "$log_root"/syslog.* \
    "$log_root"/user.log "$log_root"/user.log.* \
    "$log_root"/mail.log "$log_root"/mail.log.* \
    "$log_root"/supervisor/*.log \
    "$log_root"/supervisor/*---supervisor-*.log
  log "removed legacy SD runtime log files"
}

mask_rsyslog_offline() {
  local systemd_dir wants_dir
  systemd_dir="$(target_path /etc/systemd/system)"
  wants_dir="$systemd_dir/multi-user.target.wants"
  mkdir -p "$systemd_dir"
  ln -sfn /dev/null "$systemd_dir/rsyslog.service"
  rm -f "$wants_dir/rsyslog.service" "$wants_dir/syslog.service"
  log "masked rsyslog in offline root"
}

configure_supervisor_logs() {
  local python_cmd
  python_cmd="$(find_command python3 /usr/bin/python3)" || {
    log "python3 not found; skipping supervisor log config"
    return 0
  }

  "$python_cmd" - "$ROOT" <<'PY'
import configparser
import sys
from pathlib import Path

root = Path(sys.argv[1])


def target(path: str) -> Path:
    return root / path.lstrip("/")


def update_config(path: Path, section: str, values: dict[str, str]) -> None:
    if not path.exists():
        return
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    if not parser.has_section(section):
        parser.add_section(section)
    for key, value in values.items():
        parser.set(section, key, value)
    with path.open("w", encoding="utf-8") as config_file:
        parser.write(config_file)


update_config(
    target("/etc/supervisor/supervisord.conf"),
    "supervisord",
    {
        "logfile": "/run/rick-tv-logs/supervisord.log",
        "logfile_maxbytes": "512KB",
        "logfile_backups": "1",
        "childlogdir": "/run/rick-tv-logs",
    },
)
update_config(
    target("/etc/supervisor/conf.d/video_looper.conf"),
    "program:video_looper",
    {
        "stdout_logfile": "/run/rick-tv-logs/video_looper.stdout.log",
        "stdout_logfile_maxbytes": "1MB",
        "stdout_logfile_backups": "1",
        "stderr_logfile": "/run/rick-tv-logs/video_looper.stderr.log",
        "stderr_logfile_maxbytes": "256KB",
        "stderr_logfile_backups": "1",
    },
)
PY
  log "configured supervisor logs under /run/rick-tv-logs"
}

apply_live_config() {
  local systemctl_cmd tmpfiles_cmd

  if [[ -n "$ROOT" || "$DRY_RUN" == "1" ]]; then
    log "skipping live logging apply for offline or dry-run root"
    return 0
  fi

  if tmpfiles_cmd="$(find_command systemd-tmpfiles /bin/systemd-tmpfiles /usr/bin/systemd-tmpfiles)"; then
    "$tmpfiles_cmd" --create /etc/tmpfiles.d/rick-tv-logs.conf || log "systemd-tmpfiles failed; /run/rick-tv-logs will exist after reboot"
  fi

  if systemctl_cmd="$(find_command systemctl /bin/systemctl /usr/bin/systemctl)"; then
    "$systemctl_cmd" disable --now rsyslog.service || log "rsyslog disable failed or rsyslog is absent"
    "$systemctl_cmd" mask rsyslog.service || log "rsyslog mask failed or rsyslog is absent"
    "$systemctl_cmd" restart systemd-journald.service || log "journald restart failed; volatile config will apply after reboot"
    "$systemctl_cmd" restart supervisor.service || log "supervisor restart failed; log paths will apply after reboot"
  fi
}

main() {
  write_journald_volatile_config
  write_tmpfiles_config
  remove_persistent_journal
  remove_sd_runtime_logs
  if [[ -n "$ROOT" || "$DRY_RUN" == "1" ]]; then
    mask_rsyslog_offline
  fi
  configure_supervisor_logs
  apply_live_config
  log "SD-safe volatile logging configured"
}

main "$@"
