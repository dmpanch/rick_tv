# Rick TV Pi

`rick-tv-pi` runs directly on the Raspberry Pi, not in Docker.

## Hardware

The Phase 1 runtime assumes the existing Raspberry Pi TV hardware remains in place:

- Raspberry Pi Zero W.
- Waveshare 2.8inch DPI LCD.
- GPIO19 audio/PWM.
- GPIO26 power button.
- Existing GPIO18 amplifier/backlight wiring.

## SD-card and videolooper setup

Rick TV Pi targets Raspberry Pi Zero W running the prebuilt Video Looper image
from <https://videolooper.de/>. The supported base is the `videolooper.de`
SD-card image, not a manually assembled Raspberry Pi OS image. Rick TV deploys
its own playlist/FIFO overrides on top of the already-installed Video Looper
runtime.

### Fresh Pi Zero W base image

1. Download the Video Looper image zip from <https://videolooper.de/>. Choose a
   release that supports Raspberry Pi Zero W.

2. Open Raspberry Pi Imager, choose `Use custom`, select the downloaded
   Video Looper image zip, choose the SD card, and write it. Keep the Linux user
   as `pi`; the current Rick TV provisioning paths assume `/home/pi`.

3. Boot the Pi. The current lab image uses:

```text
user: pi
password: video
```

4. SSH into the Pi and verify that the Video Looper runtime is present:

```sh
ssh pi@<pi-ip>
sudo supervisorctl status video_looper
ls /usr/local/lib/python3.7/dist-packages/Adafruit_Video_Looper-*.egg
```

The Rick TV deploy script currently expects the legacy Python 3.7 Video Looper
layout used by the `videolooper.de` image. Do not run `apt upgrade` on the Pi as
part of Rick TV setup.

5. From the repository root on your workstation, create one full Pi config:

```sh
mkdir -p dist
cp rick-tv-pi/provisioning/rick-tv.env.example dist/rick-tv.env
nano dist/rick-tv.env
```

Fill in at least the server URL, shared API token, media root, playlist root,
and videolooper FIFO path. For first boot from a freshly written SD card, also
fill in Wi-Fi and SSH values. `dist/` is ignored so local filled configs are not
committed.

6. Deploy Rick TV:

```sh
PI_HOST=pi@<pi-ip> PI_PASSWORD=<pi-password> \
  rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy --config dist/rick-tv.env
```

7. Reboot once for boot-level panic/watchdog settings, then verify both services:

```sh
ssh pi@<pi-ip> 'sudo reboot'
ssh pi@<pi-ip> 'systemctl is-active rick-tv-pi.service && sudo supervisorctl status video_looper'
```

### Packaged image path

The preferred fresh-install path is an sdm-built Rick TV image made from the
`videolooper.de` v2.11 base archive. Install `sdm` on the build machine:

```sh
curl -L https://raw.githubusercontent.com/gitbls/sdm/master/install-sdm | bash
```

```sh
sudo rick-tv-pi/provisioning/image/build_packaged_image.sh \
  --base-image-url https://videolooper.de/video_looper_v2.11.zip \
  --output-image dist/rick-tv-pi.img
```

The builder copies the Video Looper base image, runs `sdm --customize` with Rick
TV's custom phase script, stages Rick TV, and writes a `.sha256` file beside the
output. The image customization also copies the Waveshare 2.8inch DPI LCD DTBO
files to the boot partition, appends Rick TV's legacy DPI display config to
`config.txt`, writes Rick TV's `/boot/video_looper.ini` settings, patches the
Video Looper egg, installs placeholder assets, creates the empty playlist tree,
installs panic/watchdog recovery config, installs `rick-tv-pi.service`, and
builds `/opt/rick-tv-pi/.venv`. You can pass
`--boot-config /path/to/rick-tv.env` to include a filled first-boot config in a
private generated image, but filled configs must stay out of git and are not
required for distribution.

Before first boot, copy `rick-tv.env.example` from the boot partition to
`rick-tv.env`, fill in Wi-Fi, SSH, API token, hostname, server URL, and Rick TV
runtime values, and boot the Pi. The first boot service creates
`/etc/rick-tv-pi.env`, configures Wi-Fi/SSH, re-applies the same idempotent
runtime checks, starts `rick-tv-pi.service`, restarts `video_looper`, and writes
a completion marker so later boots do not overwrite local edits. Telegram bot
token and allowed user IDs are server-side settings and must not be placed in
the Pi image or `rick-tv.env`.

For updating the current lab Pi over SSH, the supported provisioning entrypoint
remains:

```sh
rick-tv-pi/provisioning/deploy_videolooper_image.sh
```

Use `deploy_videolooper_image.sh wifi --boot /path/to/boot --ssid ... --psk ...`
before first boot when the image has Wi-Fi disabled. Use
`deploy_videolooper_image.sh deploy` once the Pi is reachable over SSH.

Legacy display files and Waveshare DTBO overlays are kept under
`rick-tv-pi/provisioning/display/` and `rick-tv-pi/provisioning/vendor/`.
The packaged image builder applies them automatically; manual copying is only
for lab repair of an already-written boot partition.

## Environment

Use `rick-tv-pi/provisioning/rick-tv.env.example` as the single human-facing Pi
config template. It includes Wi-Fi, SSH, hostname, and all Pi `RICK_TV_*`
runtime values. Firstboot reads `rick-tv.env` from the boot partition and writes
only the `RICK_TV_*` subset to `/etc/rick-tv-pi.env`; SSH deploy can do the same
from `deploy --config dist/rick-tv.env` if the runtime file does not already
exist.

The generated `/etc/rick-tv-pi.env` used by systemd contains values like:

```text
RICK_TV_SERVER_URL=https://rick-tv.example
RICK_TV_API_TOKEN=replace-me
RICK_TV_MEDIA_ROOT=/home/pi/rick-tv/media
RICK_TV_METADATA_PATH=/home/pi/rick-tv/config/channels.json
RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT=/home/pi/rick-tv/playlists
RICK_TV_VIDEOLOOPER_COMMAND_PATH=/tmp/rick-tv-videolooper.fifo
RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=false
RICK_TV_CHANNEL_SHUFFLE_SECONDS=3600
RICK_TV_REMOTE_POLL_INTERVAL_SECONDS=2
```

Telegram bot token and allowed user IDs are server-side settings and must not be
placed in `rick-tv.env` or `/etc/rick-tv-pi.env`.

`RICK_TV_METADATA_PATH` is optional, but it should be set when the Pi is expected
to receive the first file for a registry channel that does not yet exist locally.
The Pi downloads `/api/v1/channels` JSON to this path and uses registry channel
IDs for delivery polling. `RICK_TV_POLL_INTERVAL_SECONDS` is optional and
defaults to `60`. `RICK_TV_REMOTE_POLL_INTERVAL_SECONDS` controls the faster
Telegram remote-control command poll and defaults to `2`. `RICK_TV_CHANNEL_SHUFFLE_SECONDS`
controls how often files inside each channel playlist are reshuffled; the
default is `3600` seconds.

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

The Pi discovers playable channel directories under `RICK_TV_MEDIA_ROOT`,
polls the server for ready media, downloads server-validated files, verifies
`sha256` when the server provides it, atomically places files into channel
directories, and acknowledges only after placement succeeds. The Pi runtime does
not require `ffmpeg` or `ffprobe`; media-profile conversion and validation are
server responsibilities. The same poll response can also include deletion
commands. For each deletion, the Pi removes
`RICK_TV_MEDIA_ROOT/<channel_id>/<filename>` if it exists and then acknowledges
`/api/v1/delete-ack/{item_id}`; a missing local file is treated as already
deleted.

The Pi also polls `/api/v1/commands` on the faster remote interval. The current
command type is `select_channel`, queued by the Telegram bot. If the requested
channel is playable locally, the Pi selects it through the existing
videolooper playlist/FIFO path and acknowledges the command. If the channel is
not locally playable yet, the Pi logs that fact and still acknowledges the
command so it does not remain pending forever.

A directory is a navigation/playback channel only when it contains at least one
playable `.mp4`. Empty directories are ignored by navigation and generated
playlists until a playable `.mp4` appears. When `RICK_TV_METADATA_PATH` is set,
the Pi polls delivery with registry channel IDs from server-synced
`channels.json`, so the first media item can create a local channel directory.
If the synced server registry is empty, the Pi polls no channels and does not
fallback to local playable folders until the server has at least one channel.

Runtime playback is built around the prepared `videolooper.de` Video Looper
installation. Rick TV writes per-channel playlists plus a master playlist, then
switches channels through the videolooper FIFO command path. This videolooper
integration is the stable Pi playback path for the legacy image.
Channel titles are shown through the original videolooper/omxplayer subtitle
path. The legacy `omxplayer` build accepts external UTF-8 SRT subtitles, so Rick
TV keeps the standard SRT title overlay and lets the image's omxplayer
configuration control placement.

Rick TV still uses raw framebuffer `.fb` cards for switch/interstitial
placeholders on the legacy image. The current override logs FIFO commands,
playlist reloads, raw framebuffer draws, and `player.play(...)` boundaries.
A real channel switch draws only `transition-placeholder.fb` and suppresses the
next interstitial. A same-channel playlist refresh suppresses the transition
placeholder and lets the normal in-channel path draw `interstitial-ad.fb` before
the next playback. For A/B hardware investigation only,
`RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true` disables both regular raw
`/dev/fb0` placeholder writes, clears any stale framebuffer image to black once
at startup, and leaves videolooper switching/playback behavior in place. For
hardware investigation, collect:

```sh
rick-tv-pi/provisioning/scripts/collect-framebuffer-diagnostics.sh \
  --host pi@192.168.1.68 \
  --identity-file ~/.ssh/rick_tv_pi_ed25519 \
  --since "2026-06-18 00:00:00"
```

The diagnostics bundle includes `journalctl`, supervisor status/tails, `dmesg`,
`/sys/class/graphics/fb0/*`, playback process command lines, installed
videolooper override markers, and a redacted `/etc/rick-tv-pi.env`.

Provisioning installs Pi recovery hardening for appliance freezes:
`kernel.panic=10`, `kernel.panic_on_oops=1`, `panic=10` in the boot cmdline,
`dtparam=watchdog=on`, and a systemd manager watchdog drop-in with
`RuntimeWatchdogSec=15s` and `ShutdownWatchdogSec=2min`. These settings help the
Pi reboot after kernel panic or full-system hang, but they do not change
videolooper rendering and are not a root-cause fix. Reboot once after deployment
to activate the boot-level settings.

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
