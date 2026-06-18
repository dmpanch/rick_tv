# Packaged Rick TV Pi Image Plan

## Summary
Подготовить будущий flashable Raspberry Pi image, в котором уже установлены
Rick TV Pi runtime, legacy videolooper dependencies, Waveshare display setup,
systemd service, supervisor config, and pinned Rick TV videolooper overrides.
Пользователь после записи образа должен положить один config file на boot
partition, и first boot должен применить Wi-Fi/API/token/password/env variables settings.

## Key Changes
- [x] Выбрать image build path: reproducible sdm builder based on the
  `videolooper.de` v2.11 base image archive.
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
- `rick-tv-pi/provisioning/image/build_packaged_image.sh` is the documented
  sdm-based builder. It accepts either a local `videolooper.de` image/archive or
  `--base-image-url https://videolooper.de/video_looper_v2.11.zip`, copies the
  extracted base image to the requested output path, runs
  `sdm --customize --batch --apt-options none` with Rick TV's custom phase
  script, and writes an image `.sha256`.
- `rick-tv-pi/provisioning/image/sdm_rick_tv_custom_phase.sh` runs during sdm
  Phase 0. It uses `$SDMPT`, `--csrc`, and optional `--custom1` boot config to
  stage Rick TV without installing secrets or running package upgrades inside
  the legacy videolooper image.
- `rick-tv-pi/provisioning/image/install_packaged_image_payload.sh` stages the
  repository into `/opt/rick-tv-src`, installs
  `/usr/local/sbin/rick-tv-firstboot`, enables `rick-tv-firstboot.service`,
  writes the canonical `rick-tv-pi/provisioning/rick-tv.env.example` to the boot
  partition, and can copy a private filled `rick-tv.env` only when explicitly
  requested with `--boot-config`.
- The same payload installer applies the Waveshare 2.8inch DPI LCD boot config:
  it copies vendor DTBO files to boot `overlays/`, comments out conflicting
  `vc4-*kms-v3d` overlays, and appends the Rick TV legacy DPI display block to
  `config.txt`.
- The payload installer also writes Rick TV's `/boot/video_looper.ini` settings
  during image customization so the clean image starts in directory/playlist
  mode before firstboot repeats the same idempotent config.
- `rick-tv-pi/provisioning/firstboot/rick-tv-firstboot.sh` reads
  `rick-tv.env` from the boot partition, writes `/etc/rick-tv-pi.env`,
  configures Wi-Fi/SSH/hostname, installs Rick TV service/videolooper assets and
  overrides, enables `rick-tv-pi.service`, and writes
  `/var/lib/rick-tv-pi/firstboot.done`.
- `rick-tv-pi/provisioning/rick-tv.env.example` is the only human-facing Pi env
  example. It includes Wi-Fi/SSH/hostname and Pi runtime values; firstboot and
  deploy write only the `RICK_TV_*` subset to `/etc/rick-tv-pi.env`.
- The first-boot script supports dry-run/rootfs/bootfs overrides for tests and
  preserves an existing `/etc/rick-tv-pi.env` unless
  `RICK_TV_OVERWRITE_ENV=true` is explicitly set.

## Test Plan
- [x] Build image artifact in CI or documented local builder.
- [x] Mount image boot partition and verify placeholder first-boot config exists.
- [ ] Boot on a spare Pi from a config file only; verify Wi-Fi, SSH, display,
  `video_looper`, `rick-tv-pi.service`, `/api/v1/channels` sync, media download,
  and Telegram remote channel switch.
- [x] Reboot twice and verify first-boot setup is idempotent and does not overwrite
  user-edited `/etc/rick-tv-pi.env`.

## Assumptions
- The initial target remains the known working legacy videolooper image because
  it is the current stable playback solution.
- A full spare-Pi boot validation remains follow-up verification work; this
  change adds the local image builder, payload installer, and first-boot
  mechanism.
