# Raspberry Pi SD-card recovery and display files

This directory contains files that can be copied to a Raspberry Pi boot partition
when the Pi is only accessible through the SD card.

Target hardware:

- Raspberry Pi Zero W
- Waveshare 2.8inch DPI LCD, 480x640
- Wi-Fi on 2.4 GHz
- SSH password login for initial recovery

Default test credentials for the current lab Pi:

- `ssh pi@192.168.1.68`
- `password: video`

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
partition `overlays/` directory, then use the Trixie `config.txt` example under
`display/`.

For Raspberry Pi OS Trixie, use:

- `display/config.txt.waveshare-28dpi-trixie`

For Raspberry Pi OS Legacy/Buster, use:

- `display/config.txt.waveshare-28dpi-legacy`

Keep a backup of the original `config.txt` before replacing it.
