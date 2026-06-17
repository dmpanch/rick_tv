# Rick TV Server Deployment

The Rick TV server exposes the FastAPI delivery API, persists queue state on
disk, and can run a Telegram long-polling upload runner from the same container
image. The image includes `ffmpeg` for media conversion support and runs
`ffprobe` validation through the same package before media is exposed to Pi
clients. Uvicorn listens on port `8080` for the API service.

## Configuration

Set these environment variables before starting the service:

- `RICK_TV_API_TOKEN`: required bearer token for API clients.
  Docker Compose uses `change-me-local` only when this variable is omitted for
  local smoke checks; set a real token before using the service.
- `RICK_TV_PUBLIC_BASE_URL`: public URL used when generating download links.
  Defaults to `http://localhost:8080`.
- `RICK_TV_MEDIA_DIR`: media storage path. Defaults to
  `/var/lib/rick-tv/media`.
- `RICK_TV_CONFIG_DIR`: configuration path. Defaults to `/etc/rick-tv`.
- `RICK_TV_STATE_DIR`: persisted state path. Defaults to
  `/var/lib/rick-tv/state`.
- `RICK_TV_CHANNELS_PATH`: YAML channel registry path shared by the API, bot,
  and Pi sync. Defaults to `<RICK_TV_CONFIG_DIR>/channels.yml`.
- `RICK_TV_TELEGRAM_BOT_TOKEN`: Telegram bot token. Required only for the
  `rick-tv-bot` service.
- `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`: comma-separated allowlist of Telegram
  user IDs allowed to manage channels, upload media, and restore archived
  media.

## Docker Compose

From `rick-tv-server/`, create local runtime directories and start the service:

```bash
mkdir -p media config state
export RICK_TV_API_TOKEN="$(openssl rand -hex 32)"
export RICK_TV_PUBLIC_BASE_URL='http://localhost:8080'
docker compose up -d --build
```

The Compose file mounts:

- `./media` to `/var/lib/rick-tv/media`
- `./config` to `/etc/rick-tv`
- `./state` to `/var/lib/rick-tv/state`

It publishes `8080:8080` and uses `restart: unless-stopped` so the server
comes back after host restarts unless it was explicitly stopped.

The same Compose file also defines `rick-tv-bot`, a separate service using the
same image and the same mounted runtime directories. The bot is behind the
`bot` profile so local API smoke checks do not require Telegram credentials:

```bash
export RICK_TV_TELEGRAM_BOT_TOKEN='123456:telegram-token'
export RICK_TV_TELEGRAM_ALLOWED_USER_IDS='123456789'
docker compose --profile bot up -d --build
```

The bot runner uses long polling, not webhooks.

## Channel Registry And Telegram Uploads

The channel registry lives at `RICK_TV_CHANNELS_PATH` and uses this shape:

```yaml
channels:
  01_Citadel:
    display_name: Citadel TV
```

Allowlisted Telegram users can use the Telegram command menu to manage the
registry. `/add_channel` asks only for the display name; the bot generates the
next stable filesystem/API channel ID, for example `04_Birdperson_TV`.
`/list_channels` shows channels as `01 - Citadel`; selecting one channel opens
its own `List all videos`, `Rename channel`, and `Delete channel` actions.
`List all videos` shows each active channel video as a separate button. A video
detail view can send the converted Pi-ready MP4 back to Telegram, delete the
video, or go back to the channel video list. `/restore_all_videos` starts the
restore-all confirmation flow. Renaming changes only `display_name`. Deleting a
channel is rejected while active media or pending device deletion still
references it.

Upload flow:

1. User sends Telegram `video` or `document` media.
2. Bot downloads the Telegram file to a temporary server path.
3. Bot shows explicit channel choices from the YAML registry.
4. User chooses a channel.
5. Bot calls `UploadProcessor.process_upload(...)`.
6. Server stores both original media and converted Pi-ready `.mp4`, validates
   the converted file with `ffprobe`, then marks it `pending` for Pi delivery.

If the first converted output does not match the Rick TV ready profile, the
server retries conversion once with stricter output flags. If validation still
fails, the upload is marked failed and is not returned by `/api/v1/ready`.

Archive delete is a soft delete from the active library: original and converted
files remain on disk. The Telegram restore-all action requeues active archived
library items so a replacement Pi can download the media again.

Deleting a concrete video from the channel video detail view is a hard library
delete. The server removes both original and converted media files immediately,
marks the item `deleted_server_side`, and returns it in `/api/v1/ready` under
`deletions` until the Pi confirms `/api/v1/delete-ack/{item_id}`. The Pi delete
command contains `id`, `channel_id`, and `filename`; missing local files are
treated as already deleted and still acknowledged.

## Smoke Test

From `rick-tv-server/`, verify that the production image builds and the app
imports inside the container without using real secrets:

```bash
docker build -t rick-tv-server:smoke .
docker run --rm \
  -e RICK_TV_API_TOKEN=test-token \
  -e RICK_TV_PUBLIC_BASE_URL=http://localhost:8080 \
  rick-tv-server:smoke \
  python -c "import rick_tv_server.main; assert rick_tv_server.main.app is not None"
```

Use the configured bearer token when calling the API:

```bash
curl -H "Authorization: Bearer ${RICK_TV_API_TOKEN}" \
  'http://localhost:8080/api/v1/ready?channels=01_Citadel'
```

The response shape is:

```json
{
  "items": [],
  "deletions": []
}
```

After the public `/health` endpoint is available, extend the smoke run with a
reachability check:

```bash
docker compose up -d
curl -f http://localhost:8080/health
docker compose logs --no-color --tail=50
docker compose down
```
