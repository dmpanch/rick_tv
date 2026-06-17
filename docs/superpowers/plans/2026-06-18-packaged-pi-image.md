# Packaged Rick TV Pi Image Plan

## Summary
Подготовить будущий flashable Raspberry Pi image, в котором уже установлены
Rick TV Pi runtime, legacy videolooper dependencies, Waveshare display setup,
systemd service, supervisor config, and pinned Rick TV videolooper overrides.
Пользователь после записи образа должен положить один config file на boot
partition, и first boot должен применить Wi-Fi/API/token/password settings.

## Key Changes
- Выбрать image build path: reproducible builder based on Raspberry Pi OS
  Legacy/Buster or a captured known-good legacy videolooper base image.
- Добавить first-boot config reader on boot partition, например
  `rick-tv.env`, with Wi-Fi SSID/PSK/country, API URL/token, optional SSH
  password/key, hostname, and Rick TV runtime env values.
- First boot creates `/etc/rick-tv-pi.env`, configures Wi-Fi/SSH, installs or
  verifies videolooper overrides/assets, enables `rick-tv-pi.service`, and then
  marks first-boot setup complete.
- Keep secrets out of the committed image and repository. Only examples with
  placeholders are committed.
- Existing `deploy_videolooper_image.sh` remains useful for updating a running
  lab Pi, but the packaged image becomes the preferred install path.

## Test Plan
- Build image artifact in CI or documented local builder.
- Mount image boot partition and verify placeholder first-boot config exists.
- Boot on a spare Pi from a config file only; verify Wi-Fi, SSH, display,
  `video_looper`, `rick-tv-pi.service`, `/api/v1/channels` sync, media download,
  and Telegram remote channel switch.
- Reboot twice and verify first-boot setup is idempotent and does not overwrite
  user-edited `/etc/rick-tv-pi.env`.

## Assumptions
- This plan is documentation only for now; no image builder is implemented in the
  current Pi UI / Telegram remote change.
- The initial target remains the known working legacy videolooper image because
  it is the current stable playback solution.
