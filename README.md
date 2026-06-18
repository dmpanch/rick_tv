# Rick TV

Rick TV is a small video-delivery system for a Raspberry Pi TV appliance.

- `rick-tv-server` is the FastAPI service that owns the media library, channel registry, delivery state, and remote-control API.
- `rick-tv-bot` is the Telegram long-polling runner, shipped in the same Docker Compose stack, for channel management, uploads, downloads, deletes, and remote channel switching.
- `rick-tv-pi` is the Raspberry Pi client. It polls the server, downloads server-validated videos, verifies `sha256`, updates local channel playlists, and drives the runtime player.

## What It Does

1. Users upload videos to the server.
2. The server stores the original file, converts it into the Pi playback profile, validates the converted `.mp4`, and tracks it in SQLite.
3. The server exposes the canonical channel registry as JSON at `/api/v1/channels`.
4. The Pi syncs the registry, polls `/api/v1/ready`, downloads new media, applies delete commands, and acknowledges delivery through `/api/v1/ack/{id}` or deletion through `/api/v1/delete-ack/{id}`.
5. The current Pi runtime integration is built around `videolooper` playlists and FIFO commands.
6. The Telegram bot can queue a remote channel switch command. The Pi polls `/api/v1/commands`, applies the command when the channel is locally playable, and acknowledges it with `/api/v1/commands/{id}/ack`.

## Hardware

The repository is currently aimed at this appliance setup:

- Raspberry Pi Zero W
- Waveshare 2.8inch DPI LCD

The Pi also needs network access to the server.

## Requirements

Server:

- Docker and Docker Compose
- Free host port `8080`
- Shared API token in `RICK_TV_API_TOKEN`
- Telegram bot token and allowlisted user IDs if `rick-tv-bot` is enabled

Raspberry Pi:

- Python `>=3.7`
- `systemd`
- Writable channel media root in `RICK_TV_MEDIA_ROOT`
- Continuous network access to the server

## Server Setup

Run the server commands from `rick-tv-server`.

1. Copy the environment template and fill it for your host.

```bash
cd rick-tv-server
cp .env.example .env
# edit .env
# RICK_TV_UID=$(id -u) and RICK_TV_GID=$(id -g) keep runtime files editable on the host
```

2. Start the API service.

```bash
mkdir -p data/media data/config data/state
docker compose up -d --build
```

`docker-compose.yml` reads `RICK_TV_*` values from the environment or `.env`.
Containers run as `RICK_TV_UID:RICK_TV_GID`, so bind-mounted runtime files remain readable and editable from the host. By default, Compose stores all runtime data under `./data`. For a persistent installation, set `RICK_TV_DATA_DIR=/srv/rick-tv` or another absolute path on the host disk.

The API runs with plain `docker compose up`. The Telegram runner is the `rick-tv-bot` service in the same Compose file, using the same image and the same `RICK_TV_DATA_DIR`. To run the bot, set `RICK_TV_TELEGRAM_BOT_TOKEN` and `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`, then enable the `bot` profile:

```bash
docker compose --profile bot up -d --build
```

## Raspberry Pi Setup

Rick TV Pi is layered on top of the prebuilt Video Looper image from
<https://videolooper.de/>. Do not build the playback base by hand for this
project. The supported base is the `videolooper.de` SD-card image, and Rick TV
deploys its own playlist/FIFO overrides on top of that image.

### Fresh Pi Zero W Install

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

```bash
ssh pi@<pi-ip>
sudo supervisorctl status video_looper
ls /usr/local/lib/python3.7/dist-packages/Adafruit_Video_Looper-*.egg
```

The Rick TV deploy script currently expects the legacy Python 3.7 Video Looper
layout used by the `videolooper.de` image. Do not run `apt upgrade` on the Pi as
part of Rick TV setup.

5. From this repository on your workstation, copy and edit the Rick TV Pi env:

```bash
scp rick-tv-pi/provisioning/rick-tv-pi.env.example pi@<pi-ip>:/tmp/rick-tv-pi.env
ssh pi@<pi-ip> 'sudo install -m 0600 /tmp/rick-tv-pi.env /etc/rick-tv-pi.env && sudo nano /etc/rick-tv-pi.env'
```

Set at least `RICK_TV_SERVER_URL`, `RICK_TV_API_TOKEN`, `RICK_TV_MEDIA_ROOT`,
`RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT`, and `RICK_TV_VIDEOLOOPER_COMMAND_PATH`.

6. Deploy Rick TV over SSH:

```bash
PI_HOST=pi@<pi-ip> PI_PASSWORD=<pi-password> \
  rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy
```

7. Reboot once so the boot-level panic/watchdog settings take effect:

```bash
ssh pi@<pi-ip> 'sudo reboot'
```

8. After reboot, verify services:

```bash
ssh pi@<pi-ip> 'systemctl is-active rick-tv-pi.service && sudo supervisorctl status video_looper'
```

### Existing Lab Image

The current legacy `videolooper.de` lab image uses this default SSH login:

- user: `pi`
- password: `video`

After first login, replace the password or add an SSH key and disable password login if the Pi will stay on a shared network.

### Packaged Image Path

After you have a known-good `videolooper.de` image, you can turn it into a Rick
TV image:

```bash
sudo rick-tv-pi/provisioning/image/build_packaged_image.sh \
  --base-image /path/to/known-good-videolooper.img \
  --output-image /path/to/rick-tv.img
```

The builder copies the base image, mounts the root and boot partitions through a loop device, installs the Rick TV payload, and writes `rick-tv.img.sha256`. If the root and boot partitions are already mounted manually, use the lower-level installer:

```bash
rick-tv-pi/provisioning/image/install_packaged_image_payload.sh \
  --rootfs /mnt/rick-tv-root \
  --bootfs /mnt/rick-tv-boot
```

The boot partition will contain `rick-tv.env.example`. Copy it to `rick-tv.env`, then fill in Wi-Fi, SSH, hostname, API token, and runtime settings. On first boot, `rick-tv-firstboot.service` creates `/etc/rick-tv-pi.env`, configures Wi-Fi and SSH, installs pinned `videolooper` overrides and assets, enables `rick-tv-pi.service`, and then stops overwriting manual edits.

For the current lab Pi, SSH deployment is still supported. Before deploying, prepare `/etc/rick-tv-pi.env` from the template:

```bash
sudo cp rick-tv-pi/provisioning/rick-tv-pi.env.example /etc/rick-tv-pi.env
sudo nano /etc/rick-tv-pi.env
```

Edit the file before running deploy so the service starts with the intended values.

```bash
rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy
```

Raw framebuffer placeholders are still part of the legacy `videolooper` runtime. The code logs FIFO commands, playlist reloads, `transition-placeholder.fb` and `interstitial-ad.fb` display events, and `player.play(...)` boundaries. A channel switch draws only the transition placeholder and suppresses the next interstitial; an in-channel playlist refresh does not draw the transition placeholder and uses the regular interstitial before the next playback.

`RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true` is a diagnostic flag. It disables the regular raw `/dev/fb0` placeholder writes, clears stale framebuffer content to black once at startup, and does not otherwise change the playback path. Recent diagnostics showed player aborts even with regular framebuffer placeholder writes disabled, so `omxplayer`/`videolooper` process lifecycle stability remains an active investigation item.

Pi provisioning also installs recovery settings for appliance outages: kernel panic reboot after 10 seconds, panic-on-oops, and the Raspberry Pi/systemd hardware watchdog. This is recovery hardening only; it does not change placeholder rendering or prove the cause of any freeze. A controlled reboot after deploy is required for boot-level `panic=10` and watchdog settings to take full effect.

## Pi Environment

The environment template is:

- `rick-tv-pi/provisioning/rick-tv-pi.env.example`

Important settings:

- `RICK_TV_SERVER_URL`: server API URL, for example `http://192.168.1.10:8080`
- `RICK_TV_API_TOKEN`: shared API token, matching `rick-tv-server/.env`
- `RICK_TV_MEDIA_ROOT`: root directory for channel folders on the Pi
- `RICK_TV_METADATA_PATH`: path to `channels.json`
- `RICK_TV_POLL_INTERVAL_SECONDS`: normal server polling interval
- `RICK_TV_REMOTE_POLL_INTERVAL_SECONDS`: faster polling interval for Telegram remote-control commands
- `RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT`: working playlist directory used by `videolooper`
- `RICK_TV_VIDEOLOOPER_COMMAND_PATH`: FIFO used to send player commands
- `RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS`: diagnostic switch for raw framebuffer placeholders
- `RICK_TV_CHANNEL_SHUFFLE_SECONDS`: interval for reshuffling a channel playlist
- `RICK_TV_TOUCH_SCREEN_WIDTH`: touch input width
- `RICK_TV_TOUCH_SCREEN_HEIGHT`: touch input height
- `RICK_TV_TOUCH_SWAP_AXES`: whether to swap touch axes
- `RICK_TV_TOUCH_GESTURE_HORIZONTAL_AXIS`: gesture axis, `x` or `y`
- `RICK_TV_TOUCH_INVERT_X`: whether to invert touch X
- `RICK_TV_TOUCH_INVERT_Y`: whether to invert touch Y
- `RICK_TV_TOUCH_DEVICE`: explicit input device path, if auto-detection is not enough
- `RICK_TV_RUNTIME_TICK_SECONDS`: runtime loop tick

Minimum required settings:

- `RICK_TV_SERVER_URL`
- `RICK_TV_API_TOKEN`
- `RICK_TV_MEDIA_ROOT`
- `RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT`
- `RICK_TV_VIDEOLOOPER_COMMAND_PATH`

Start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rick-tv-pi.service
sudo systemctl status rick-tv-pi.service
```

## Channels

Channels are directories under `RICK_TV_MEDIA_ROOT`, for example:

- `01_Citadel/`
- `02_Interdimensional_Cable/`
- `03_Empty/`

A channel participates only when its directory contains at least one `.mp4`. Empty directories do not appear in navigation, generated playlists, or polling until a playable `.mp4` exists.

The server SQLite database is the canonical registry for Telegram channel management and for the Pi registry sync. `/api/v1/channels` returns JSON:

```json
{
  "channels": {
    "01_Citadel": {
      "display_name": "Citadel"
    }
  }
}
```

On a first start with no existing channels, the server creates an empty SQLite database. `/api/v1/channels` returns:

```json
{
  "channels": {}
}
```

The bot still allows adding the first channel. A Pi with `RICK_TV_METADATA_PATH` configured does not fall back to local channels after successfully syncing an empty server registry; it waits until channels exist in the server database.

Server media is stored in this readable layout:

```text
media/library/<channel_id>/<item_id>/original/...
media/library/<channel_id>/<item_id>/converted/...
```

The database stores relative paths, item status, delivery filename, and the converted file `sha256`.

## Telegram Uploads And Remote Control

The Telegram runner is implemented in `rick_tv_server.bot_runner` and runs as the `rick-tv-bot` service.

Typical flow:

1. An allowlisted user opens the Telegram bot command menu.
2. `/add_channel` asks only for the display name. The stable channel ID is generated automatically, for example `04_Birdperson_TV`.
3. `/list_channels` shows channels as `01 - Citadel`. Selecting a channel opens `Switch channel on Pi`, `List all videos`, `Rename channel`, and `Delete channel`.
4. `List all videos` shows each active channel video as a separate button. The selected video screen offers `Download`, `Delete`, and `Back`.
5. `Switch channel on Pi` queues a remote command. The Pi picks it up through its fast command poll loop and switches through the `videolooper` FIFO if the channel is locally playable.
6. `Download` sends the converted Pi-ready `.mp4` back to Telegram.
7. `Delete` removes the original and converted files from the server, removes the video from the active library, and queues a Pi delete. The Pi removes its local copy on the next successful poll and confirms with `/api/v1/delete-ack/{id}`.
8. `/restore_all_videos` asks for confirmation before re-delivering the full active library.
9. A user sends a Telegram `video` or `document`; the bot then asks which channel should receive it.
10. After channel selection, the bot downloads the Telegram file locally and calls `UploadProcessor.process_upload(...)`.
11. The server stores the original upload and the converted Pi-ready `.mp4` under `media/library/<channel_id>/<item_id>/...`.
12. The item becomes `pending_delivery`; the Pi downloads it, verifies `sha256`, installs it into the channel directory, and acks delivery. The server then marks it `available`.

The server converts media to the target playback profile (`640x480`, `h264`, `aac`) and validates the converted `.mp4` with `ffprobe` before it appears in `/api/v1/ready`. `ffmpeg` and `ffprobe` are server-only dependencies. The Pi receives an already validated file, verifies `sha256`, stores it in the channel directory, and sends an ack.

Deleting a video from the Telegram channel screen is a physical server delete plus an asynchronous Pi delete. `restore all` requeues active `available` media so a replacement or recovered Pi can download the library again.
