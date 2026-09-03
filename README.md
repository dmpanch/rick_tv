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
6. The Telegram bot can queue a remote channel switch command. The Pi polls `/api/v1/commands`, applies the command when the channel is locally playable, and acknowledges it with `/api/v1/commands/{id}/ack`; commands for registry-known channels remain pending until their first local media file arrives.

## Hardware

The repository is currently aimed at this appliance setup:

- Raspberry Pi Zero W
- Waveshare 2.8inch DPI LCD
- GPIO26 active-low power switch and GPIO18 display/amplifier control
- Either a USB DAC or PWM audio on GPIO19, selected with
  `RICK_TV_AUDIO_PROFILE`

The Pi also needs network access to the server.

## Requirements

Server:

- Docker and Docker Compose
- Free host port selected by `RICK_TV_HOST_PORT` (defaults to `8080`)
- Shared API token in `RICK_TV_API_TOKEN`
- Telegram bot token and allowlisted user IDs if `rick-tv-bot` is enabled

Raspberry Pi:

- Python `>=3.7`
- `systemd`
- Writable channel media root in `RICK_TV_MEDIA_ROOT`
- Continuous network access to the server

## Server Setup

Run the server commands from `rick-tv-server`.

Copy the environment template and fill it for your host.

```bash
cd rick-tv-server
cp .env.example .env
# edit .env
```

Set `RICK_TV_API_TOKEN`, `RICK_TV_PUBLIC_BASE_URL`, `RICK_TV_HOST_PORT`,
`RICK_TV_TELEGRAM_BOT_TOKEN`, and `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`. Keep
`RICK_TV_UID=$(id -u)` and `RICK_TV_GID=$(id -g)` in `.env` so bind-mounted
runtime files stay editable from the host.

Start the full stack:

```bash
docker compose up -d
```

This starts both `rick-tv-server` and `rick-tv-bot`. `docker-compose.yml` reads
`RICK_TV_*` values from the environment or `.env`. Containers run as
`RICK_TV_UID:RICK_TV_GID`, and Compose stores runtime data under
`${RICK_TV_DATA_DIR:-./data}` by default. For a persistent installation, set
`RICK_TV_DATA_DIR=/srv/rick-tv` or another absolute path on the host disk.
`RICK_TV_HOST_PORT` publishes the API on a different host port while the
container continues to listen on `8080`.

For API-only development runs:

```bash
docker compose up -d rick-tv-server
```

To force a rebuild after code changes:

```bash
docker compose up -d --build
```

## Raspberry Pi Setup

Rick TV Pi is distributed as a prepared SD-card image built on top of Video
Looper v2.11 from <https://videolooper.de/>. For a normal install, flash the
Rick TV image and add one first-boot config file on the SD card boot partition.
Do not build the playback base by hand or start from a plain Raspberry Pi OS
image.

### Fresh Pi Install

Ready-made image download:

```text
<ADD_IMAGE_DOWNLOAD_LINK_HERE>
```

You can also build the same image locally. Install `sdm` on the build machine:

```bash
curl -L https://raw.githubusercontent.com/gitbls/sdm/master/install-sdm | bash
```

Then build from the Video Looper v2.11 archive:

```bash
sudo rick-tv-pi/provisioning/image/build_packaged_image.sh \
  --base-image-url https://videolooper.de/video_looper_v2.11.zip \
  --output-image dist/rick-tv-pi.img
```

The local builder writes `dist/rick-tv-pi.img` and
`dist/rick-tv-pi.img.sha256`. The generated image includes the Waveshare 2.8inch
DPI LCD boot config, Rick TV's `/boot/video_looper.ini`, the patched Video
Looper egg, placeholder assets, panic/watchdog recovery config,
`rick-tv-pi.service`, `rick-tv-power-button.service`, `/opt/rick-tv-pi/.venv`, and the pinned Pi runtime
overrides `evdev==1.7.1` and `certifi==2026.4.22`.

The image contains `rick-tv.env.example`, but it does not contain a filled
`rick-tv.env`. Flash either the downloaded image or `dist/rick-tv-pi.img` with
Raspberry Pi Imager by choosing `Use custom`, selecting the image, choosing the
SD card, and writing it. After flashing, open the SD card boot partition and
copy a filled `rick-tv.env` there before the first boot:

```bash
mkdir -p dist
cp rick-tv-pi/provisioning/rick-tv.env.example dist/rick-tv.env
nano dist/rick-tv.env
cp dist/rick-tv.env /path/to/boot/rick-tv.env
```

Fill in Wi-Fi, SSH, hostname, `RICK_TV_SERVER_URL`, `RICK_TV_API_TOKEN`,
`RICK_TV_AUDIO_PROFILE`, and the Pi runtime values. Use `pwm` for the original
GPIO19 television and `usb-dac` for the USB audio build. Telegram bot token and allowed user IDs stay on the
server only; do not put them in the Pi image or `rick-tv.env`. Keep filled env
files out of git.

On first boot, `rick-tv-firstboot.service` reads `/boot/rick-tv.env`, configures
Wi-Fi and SSH, writes `/etc/rick-tv-pi.env`, verifies the non-secret Rick TV
runtime payload, starts `rick-tv-pi.service` and `rick-tv-power-button.service`,
restarts `video_looper`, and then
stops overwriting manual edits. After the Pi joins the network, verify services:

```bash
ssh pi@<pi-ip> 'systemctl is-active rick-tv-pi.service rick-tv-power-button.service && sudo supervisorctl status video_looper'
```

### Update an Existing Lab Pi

For development and lab updates, SSH deployment is still supported on an
already-running `videolooper.de` image. The current legacy lab image uses this
default SSH login:

- user: `pi`
- password: `video`

After first login, replace the password or add an SSH key and disable password
login if the Pi will stay on a shared network. Do not run `apt upgrade` on the
target Pi as part of Rick TV setup; the deploy path expects the legacy Python
3.7 Video Looper layout.

Use the same full Pi config template and pass it to the deploy script:

```bash
mkdir -p dist
cp rick-tv-pi/provisioning/rick-tv.env.example dist/rick-tv.env
nano dist/rick-tv.env
PI_HOST=pi@<pi-ip> PI_PASSWORD=<pi-password> \
  rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy --config dist/rick-tv.env
```

An explicit `deploy --config ...` replaces `/etc/rick-tv-pi.env` with the
runtime subset from that config, including the audio profile. Deploy without a
config preserves an existing runtime environment.

Raw framebuffer placeholders are still part of the legacy `videolooper` runtime. The code logs FIFO commands, playlist reloads, `transition-placeholder.fb` and `interstitial-ad.fb` display events, and `player.play(...)` boundaries. A channel switch draws only the transition placeholder and suppresses the next interstitial; an in-channel playlist refresh does not draw the transition placeholder and uses the regular interstitial before the next playback.

`RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true` is a diagnostic flag. It disables the regular raw `/dev/fb0` placeholder writes, clears stale framebuffer content to black once at startup, and does not otherwise change the playback path. Recent diagnostics showed player aborts even with regular framebuffer placeholder writes disabled, so `omxplayer`/`videolooper` process lifecycle stability remains an active investigation item.

Pi provisioning also installs recovery settings for appliance outages: kernel panic reboot after 10 seconds, panic-on-oops, and the Raspberry Pi/systemd hardware watchdog. This is recovery hardening only; it does not change placeholder rendering or prove the cause of any freeze. A controlled reboot after deploy is required for boot-level `panic=10` and watchdog settings to take full effect.

## Pi Environment

The environment template is:

- `rick-tv-pi/provisioning/rick-tv.env.example`

It is intentionally a full first-boot config: Wi-Fi, SSH, hostname, and Pi
runtime values live in one file. Firstboot and SSH deploy write only the
`RICK_TV_*` runtime subset to `/etc/rick-tv-pi.env` for systemd. Telegram bot
credentials are server-side only and must not be added to the Pi config.

Important settings:

- `RICK_TV_SERVER_URL`: server API URL, for example `http://192.168.1.10:8080`
- `RICK_TV_API_TOKEN`: shared API token, matching `rick-tv-server/.env`
- `RICK_TV_AUDIO_PROFILE`: `usb-dac` (default) or `pwm` for GPIO19 audio
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
- `RICK_TV_TOUCH_SWAP_AXES`: `auto` for the packaged Waveshare DPI image, or explicit `true`/`false`
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
5. `Switch channel on Pi` queues a remote command. The Pi picks it up through its fast command poll loop and switches through the `videolooper` FIFO if the channel is locally playable. For a newly created registry channel, the command remains pending until the Pi downloads at least one playable `.mp4`.
6. `Download` sends the converted Pi-ready `.mp4` back to Telegram.
7. `Delete` removes the original and converted files from the server, removes the video from the active library, and queues a Pi delete. The Pi removes its local copy on the next successful poll and confirms with `/api/v1/delete-ack/{id}`.
8. `/restore_all_videos` asks for confirmation before re-delivering the full active library.
9. A user sends a Telegram `video` or `document`; the bot then asks which channel should receive it.
10. After channel selection, the bot downloads the Telegram file locally and calls `UploadProcessor.process_upload(...)`.
11. The server stores the original upload and the converted Pi-ready `.mp4` under `media/library/<channel_id>/<item_id>/...`.
12. The item becomes `pending_delivery`; the Pi downloads it, verifies `sha256`, installs it into the channel directory, and acks delivery. The server then marks it `available`.

The server converts media to the target playback profile (`640x480`, `h264`, `aac`) and validates the converted `.mp4` with `ffprobe` before it appears in `/api/v1/ready`. `ffmpeg` and `ffprobe` are server-only dependencies. The Pi receives an already validated file, verifies `sha256`, stores it in the channel directory, and sends an ack.

Deleting a video from the Telegram channel screen is a physical server delete plus an asynchronous Pi delete. `restore all` requeues active `available` media so a replacement or recovered Pi can download the library again.
