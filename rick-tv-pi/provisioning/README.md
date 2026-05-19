# Raspberry Pi SD-card recovery and display files

This directory contains files that can be copied to a Raspberry Pi boot partition
when the Pi is only accessible through the SD card.

Target hardware:

- Raspberry Pi Zero W
- Waveshare 2.8inch DPI LCD, 480x640
- Wi-Fi on 2.4 GHz
- SSH password login for initial recovery

Do not commit real Wi-Fi passwords, API tokens, or private keys. Replace the
`YOUR_*` placeholders on the SD card before booting.

## Boot partition paths

- Raspberry Pi OS Bookworm/Trixie mounts the FAT boot partition as
  `/boot/firmware` when running.
- When the card is inserted into another machine, the same partition is usually
  shown as `bootfs`, `boot`, or `system-boot`.

## Wi-Fi and SSH recovery

Use one of these approaches:

1. `bootfs/custom.toml.example` before the first boot of a fresh Raspberry Pi OS
   image.
2. `bootfs/firstrun.sh` plus a one-line edit to `cmdline.txt` when the card may
   already have booted and first-boot customization may not run again.
3. `ubuntu/network-config.example.yaml` only for Ubuntu/cloud-init images that
   have a `network-config` file on the boot partition.

The old `wpa_supplicant.conf` file on the boot partition is intentionally not
used here because it is unreliable on current Raspberry Pi OS Bookworm/Trixie.

## Waveshare display

Copy the DTBO files from `vendor/waveshare-28dpi/overlays/` to the boot
partition `overlays/` directory, then append one of the snippets under
`display/` to `config.txt`.

For Raspberry Pi OS Bookworm/Trixie, use:

- `display/config.txt.waveshare-28dpi-bookworm`

For older Buster/Bullseye-style legacy DPI setups, use:

- `display/config.txt.waveshare-28dpi-legacy`

If the panel shows early boot and then becomes black after userspace starts, the
first thing to try is removing/commenting `dtoverlay=vc4-kms-v3d` and using the
legacy DPI block. Keep a backup of the original `config.txt`.
