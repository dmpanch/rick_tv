# Rick TV Pi

`rick-tv-pi` runs directly on the Raspberry Pi, not in Docker.

## Hardware

The Phase 1 runtime assumes the existing Raspberry Pi TV hardware remains in place:

- Raspberry Pi Zero W.
- Waveshare 2.8inch DPI LCD.
- GPIO19 audio/PWM.
- GPIO26 power button.
- Existing GPIO18 amplifier/backlight wiring.

## SD-card and videolooper image setup

Rick TV Pi currently targets the prepared Raspberry Pi OS Legacy/Buster image
with Adafruit `pi_video_looper` already installed. The supported provisioning
entrypoint is:

```sh
rick-tv-pi/provisioning/deploy_videolooper_image.sh
```

Use `deploy_videolooper_image.sh wifi --boot /path/to/boot --ssid ... --psk ...`
before first boot when the image has Wi-Fi disabled. Use
`deploy_videolooper_image.sh deploy` once the Pi is reachable over SSH.

Legacy display files and Waveshare DTBO overlays are kept under
`rick-tv-pi/provisioning/display/` and `rick-tv-pi/provisioning/vendor/`.

## Environment

Create `/etc/rick-tv-pi.env` for the systemd service:

```text
RICK_TV_SERVER_URL=https://rick-tv.example
RICK_TV_API_TOKEN=replace-me
RICK_TV_MEDIA_ROOT=/home/pi/rick-tv/media
RICK_TV_METADATA_PATH=/home/pi/rick-tv/channels.yml
RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT=/home/pi/rick-tv/playlists
RICK_TV_VIDEOLOOPER_COMMAND_PATH=/tmp/rick-tv-videolooper.fifo
RICK_TV_CHANNEL_SHUFFLE_SECONDS=3600
```

`RICK_TV_METADATA_PATH` is optional. `RICK_TV_POLL_INTERVAL_SECONDS` is optional and defaults to `60`. `RICK_TV_CHANNEL_SHUFFLE_SECONDS` controls how often files inside each channel playlist are reshuffled; the default is `3600` seconds.

Touch gestures also can be tuned for DPI orientation:

```text
RICK_TV_TOUCH_SCREEN_WIDTH=480
RICK_TV_TOUCH_SCREEN_HEIGHT=640
RICK_TV_TOUCH_SWAP_AXES=false
RICK_TV_TOUCH_GESTURE_HORIZONTAL_AXIS=x
RICK_TV_TOUCH_INVERT_X=0
RICK_TV_TOUCH_INVERT_Y=0
RICK_TV_TOUCH_DEVICE=
RICK_TV_RUNTIME_TICK_SECONDS=0.1
```

- `RICK_TV_TOUCH_SWAP_AXES` supports `true|false|auto`; start with `false`.
- `RICK_TV_TOUCH_GESTURE_HORIZONTAL_AXIS` supports `x|y` and selects axis used for left-right detection.
- `RICK_TV_TOUCH_INVERT_X/Y` support `1/0`, `true/false`, `on/off`, `yes/no`.
- `RICK_TV_TOUCH_DEVICE` forces a specific `/dev/input/event*` path.

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

## SSH Access

For the current local test setup:

```text
ssh pi@192.168.1.68
password: video
```

If service/env updates are needed, use sudo on the Pi for writing `/etc/rick-tv-pi.env` and systemd files.
