#!/bin/bash
set -euo pipefail

# Forced first-run recovery for Raspberry Pi OS Bookworm/Trixie.
# Copy this file to bootfs/firstrun.sh, replace placeholders below, then append
# these tokens to the single line in bootfs/cmdline.txt:
#
# systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target
#
# The script enables SSH, creates/updates user pi, writes a NetworkManager Wi-Fi
# profile, removes itself from cmdline.txt, then reboots.

PI_USER="pi"
PI_PASSWORD='YOUR_PI_PASSWORD'
HOSTNAME_VALUE="pi"
WIFI_SSID='Panch_2.4'
WIFI_PASSWORD_OR_PSK='YOUR_WIFI_PASSWORD_OR_64_HEX_PSK'
WIFI_COUNTRY='UA'

log() {
  echo "[rick-tv firstrun] $*"
}

log "setting hostname"
echo "$HOSTNAME_VALUE" > /etc/hostname
if grep -q '^127\.0\.1\.1' /etc/hosts; then
  sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t${HOSTNAME_VALUE}/" /etc/hosts
else
  printf '127.0.1.1\t%s\n' "$HOSTNAME_VALUE" >> /etc/hosts
fi

log "enabling ssh"
if command -v systemctl >/dev/null 2>&1; then
  systemctl enable ssh || systemctl enable ssh.service || true
fi

log "creating/updating user"
if id "$PI_USER" >/dev/null 2>&1; then
  echo "${PI_USER}:${PI_PASSWORD}" | chpasswd
else
  useradd -m -s /bin/bash -G sudo,adm,dialout,cdrom,audio,video,plugdev,games,users,input,render,netdev,gpio,i2c,spi "$PI_USER"
  echo "${PI_USER}:${PI_PASSWORD}" | chpasswd
fi
install -d -m 0700 -o "$PI_USER" -g "$PI_USER" "/home/${PI_USER}/.ssh"

log "allowing ssh password auth"
install -d /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/10-rick-tv-recovery.conf <<'SSHCONF'
PasswordAuthentication yes
PermitRootLogin no
SSHCONF

log "setting wlan regulatory country"
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_wifi_country "$WIFI_COUNTRY" || true
fi

log "writing NetworkManager Wi-Fi profile"
install -d -m 0755 /etc/NetworkManager/system-connections
UUID_VALUE="$(cat /proc/sys/kernel/random/uuid)"
cat >/etc/NetworkManager/system-connections/rick-tv-wifi.nmconnection <<EOF
[connection]
id=rick-tv-wifi
uuid=${UUID_VALUE}
type=wifi
autoconnect=true

[wifi]
mode=infrastructure
ssid=${WIFI_SSID}

[wifi-security]
key-mgmt=wpa-psk
psk=${WIFI_PASSWORD_OR_PSK}

[ipv4]
method=auto

[ipv6]
method=auto
EOF
chmod 600 /etc/NetworkManager/system-connections/rick-tv-wifi.nmconnection
chown root:root /etc/NetworkManager/system-connections/rick-tv-wifi.nmconnection

if command -v systemctl >/dev/null 2>&1; then
  systemctl enable NetworkManager || true
fi

log "reducing SD-card journal writes"
install -d /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/volatile-rick-tv.conf <<'JOURNAL'
[Journal]
Storage=volatile
RuntimeMaxUse=32M
JOURNAL

log "removing firstrun hook from cmdline"
CMDLINE=/boot/firmware/cmdline.txt
if [ -f "$CMDLINE" ]; then
  sed -i 's# systemd.run=/boot/firmware/firstrun.sh##; s# systemd.run_success_action=reboot##; s# systemd.unit=kernel-command-line.target##' "$CMDLINE"
fi
rm -f /boot/firmware/firstrun.sh

log "done"
