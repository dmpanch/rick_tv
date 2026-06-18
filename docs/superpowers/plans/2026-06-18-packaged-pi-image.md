# Packaged Rick TV Pi Image Plan

## Summary
Подготовить будущий flashable Raspberry Pi image, в котором уже установлены
Rick TV Pi runtime, legacy videolooper dependencies, Waveshare display setup,
systemd service, supervisor config, and pinned Rick TV videolooper overrides.
Пользователь после записи образа должен положить один config file на boot
partition, и first boot должен применить Wi-Fi/API/token/password/env variables settings.

## Key Changes
- [x] Выбрать image build path: reproducible builder based on Raspberry Pi OS
  Legacy/Buster or a captured known-good legacy videolooper base image.
- [x] Добавить first-boot config reader on boot partition, например
  `rick-tv.env`, with Wi-Fi SSID/PSK/country, API URL/token, optional SSH
  password/key, hostname, and Rick TV runtime env values.
- [x] First boot creates `/etc/rick-tv-pi.env`, configures Wi-Fi/SSH, installs or
  verifies videolooper overrides/assets, enables `rick-tv-pi.service`, and then
  marks first-boot setup complete.
- [x] Keep secrets out of the committed image and repository. Only examples with
  placeholders are committed.
- [x] Existing `deploy_videolooper_image.sh` remains useful for updating a running
  lab Pi, but the packaged image becomes the preferred install path.

## Current Implementation
- `rick-tv-pi/provisioning/image/install_packaged_image_payload.sh` stages the
  repository into `/opt/rick-tv-src` on a mounted known-good legacy rootfs,
  installs `/usr/local/sbin/rick-tv-firstboot`, enables
  `rick-tv-firstboot.service`, and writes `rick-tv.env.example` to the mounted
  boot partition.
- `rick-tv-pi/provisioning/firstboot/rick-tv-firstboot.sh` reads
  `rick-tv.env` from the boot partition, writes `/etc/rick-tv-pi.env`,
  configures Wi-Fi/SSH/hostname, installs Rick TV service/videolooper assets and
  overrides, enables `rick-tv-pi.service`, and writes
  `/var/lib/rick-tv-pi/firstboot.done`.
- The first-boot script supports dry-run/rootfs/bootfs overrides for tests and
  preserves an existing `/etc/rick-tv-pi.env` unless
  `RICK_TV_OVERWRITE_ENV=true` is explicitly set.

## Test Plan
- [ ] Build image artifact in CI or documented local builder.
- [x] Mount image boot partition and verify placeholder first-boot config exists.
- [ ] Boot on a spare Pi from a config file only; verify Wi-Fi, SSH, display,
  `video_looper`, `rick-tv-pi.service`, `/api/v1/channels` sync, media download,
  and Telegram remote channel switch.
- [x] Reboot twice and verify first-boot setup is idempotent and does not overwrite
  user-edited `/etc/rick-tv-pi.env`.

## Assumptions
- The initial target remains the known working legacy videolooper image because
  it is the current stable playback solution.
- A full flashed image artifact and spare-Pi boot validation remain follow-up
  verification work; this change adds the payload and first-boot mechanism.
