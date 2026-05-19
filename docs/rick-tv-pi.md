# Rick TV Pi

`rick-tv-pi` runs directly on the Raspberry Pi, not in Docker.

## Hardware

The Phase 1 runtime assumes the existing Raspberry Pi TV hardware remains in place:

- Raspberry Pi Zero W.
- Waveshare 2.8inch DPI LCD.
- GPIO19 audio/PWM.
- GPIO26 power button.
- Existing GPIO18 amplifier/backlight wiring.

## SD-card recovery and display setup

Boot-partition recovery files, Waveshare 2.8inch DPI LCD `config.txt` snippets,
and vendor DTBO overlay files are kept in
`rick-tv-pi/provisioning/`.

Use these when the Pi is only accessible through the SD card:

- `rick-tv-pi/provisioning/bootfs/custom.toml.example` for a fresh first boot.
- `rick-tv-pi/provisioning/bootfs/firstrun.sh` for forced recovery after an
  unknown/failed first boot.
- `rick-tv-pi/provisioning/ubuntu/network-config.example.yaml` for Ubuntu
  cloud-init images with a boot-partition `network-config` file.
- `rick-tv-pi/provisioning/display/config.txt.waveshare-28dpi-trixie` for
  Raspberry Pi OS Trixie.
- `rick-tv-pi/provisioning/vendor/waveshare-28dpi/overlays/*.dtbo` copied from
  Waveshare's 2.8inch DPI LCD vendor package.

## Environment

Create `/etc/rick-tv-pi.env` for the systemd service:

```text
RICK_TV_SERVER_URL=https://rick-tv.example
RICK_TV_API_TOKEN=replace-me
RICK_TV_MEDIA_ROOT=/home/pi/Videos/rick_tv_channels
RICK_TV_METADATA_PATH=/etc/rick-tv/channels.yml
```

`RICK_TV_METADATA_PATH` is optional. `RICK_TV_POLL_INTERVAL_SECONDS` is optional and defaults to `60`.

## Runtime

The Pi discovers channel directories under `RICK_TV_MEDIA_ROOT`, polls the server for ready media, downloads and validates files, atomically places them into channel directories, and acknowledges only after placement succeeds. Empty channels stay selectable and are rescanned during the polling loop.

The Pi exposes no inbound Rick TV ports. Delivery is initiated by authenticated outbound polling to the server.

## Service

Install the package into the Python environment used by systemd, copy `rick-tv-pi/systemd/rick-tv-pi.service` to `/etc/systemd/system/rick-tv-pi.service`, then enable it with:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now rick-tv-pi.service
```

The service writes stdout and stderr to the journal. Rick TV delivery state remains server-authoritative; the Pi does not maintain durable delivery logs.
