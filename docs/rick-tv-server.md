# Rick TV Server Deployment

The Rick TV server exposes the FastAPI delivery API, persists channel and media
library state in SQLite, and can run a Telegram long-polling upload runner from
the same container image. The image includes `ffmpeg` for media conversion support and runs
`ffprobe` validation through the same package before media is exposed to Pi
clients. Uvicorn listens on port `8080` for the API service.

## Configuration

Set these environment variables before starting the service:

- `RICK_TV_API_TOKEN`: required bearer token for API clients.
  Docker Compose uses `change-me-local` only when this variable is omitted for
  local smoke checks; set a real token before using the service.
- `RICK_TV_PUBLIC_BASE_URL`: public URL used when generating download links.
  Defaults to `http://localhost:8080`.
- `RICK_TV_DATA_DIR`: host directory mounted by Docker Compose for media,
  config, and state. Defaults to `./data`; for production prefer an absolute
  path such as `/srv/rick-tv`.
- `RICK_TV_MEDIA_DIR`: media storage path. Defaults to
  `/var/lib/rick-tv/media`.
- `RICK_TV_CONFIG_DIR`: configuration path. Defaults to `/etc/rick-tv`.
- `RICK_TV_STATE_DIR`: persisted state path. Defaults to
  `/var/lib/rick-tv/state`.
- `RICK_TV_DB_PATH`: canonical SQLite database path for channels, media library,
  delivery statuses, and bot channel preferences. Defaults to
  `<RICK_TV_STATE_DIR>/rick-tv.sqlite3`.
- `RICK_TV_CHANNELS_PATH`: legacy YAML channel registry import path. If the DB
  is empty, startup imports this file once and deletes it after successful
  migration. Runtime channel changes are stored in SQLite.
- `RICK_TV_UID` and `RICK_TV_GID`: host user/group used by Docker Compose when
  running the API and bot containers. Defaults to `1000:1000` so bind-mounted
  runtime files stay editable from the host on a typical Linux workstation.
- `RICK_TV_TELEGRAM_BOT_TOKEN`: Telegram bot token. Required only for the
  `rick-tv-bot` service.
- `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`: comma-separated allowlist of Telegram
  user IDs allowed to manage channels, upload media, and restore available
  media.

## Docker Compose

From `rick-tv-server/`, create local runtime directories and start the service:

```bash
mkdir -p data/media data/config data/state
export RICK_TV_API_TOKEN="$(openssl rand -hex 32)"
export RICK_TV_PUBLIC_BASE_URL='http://localhost:8080'
export RICK_TV_DATA_DIR="${RICK_TV_DATA_DIR:-./data}"
export RICK_TV_UID="$(id -u)"
export RICK_TV_GID="$(id -g)"
docker compose up -d --build
```

The Compose file mounts:

- `${RICK_TV_DATA_DIR:-./data}/media` to `/var/lib/rick-tv/media`
- `${RICK_TV_DATA_DIR:-./data}/config` to `/etc/rick-tv`
- `${RICK_TV_DATA_DIR:-./data}/state` to `/var/lib/rick-tv/state`

It publishes `8080:8080` and uses `restart: unless-stopped` so the server
comes back after host restarts unless it was explicitly stopped.
The SQLite DB path inside the container remains
`/var/lib/rick-tv/state/rick-tv.sqlite3`, so with Compose it physically lives at
`${RICK_TV_DATA_DIR:-./data}/state/rick-tv.sqlite3` on the host.

If runtime files were created earlier by root-owned containers, change ownership
once before restarting with `RICK_TV_UID/GID`:

```bash
docker compose run --rm --user root --entrypoint sh rick-tv-server \
  -lc "chown -R $(id -u):$(id -g) /etc/rick-tv /var/lib/rick-tv/media /var/lib/rick-tv/state"
```

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

The channel registry lives in SQLite. The API serves `/api/v1/channels` as JSON
using this generated shape:

```json
{
  "channels": {
    "01_Citadel": {
      "display_name": "Citadel TV"
    }
  }
}
```

If the DB is empty and no legacy `channels.yml` or `queue.json` exists, startup
creates an empty DB and `/api/v1/channels` returns `{"channels": {}}`.

The server also exposes a small authenticated remote-control API for the current
single Pi appliance. `GET /api/v1/commands` returns pending commands, and
`POST /api/v1/commands/{command_id}/ack` completes a command after the Pi has
handled it. The first command type is `select_channel`, queued from Telegram.

Allowlisted Telegram users can use the Telegram command menu to manage the
registry. `/add_channel` asks only for the display name; the bot generates the
next stable filesystem/API channel ID, for example `04_Birdperson_TV`.
`/list_channels` shows channels as `01 - Citadel`; selecting one channel opens
its own `Switch channel on Pi`, `List all videos`, `Rename channel`, and
`Delete channel` actions. `Switch channel on Pi` queues a remote command and
does not wait for the Pi to acknowledge it synchronously.
`List all videos` shows each active channel video as a separate button. A video
detail view can send the converted Pi-ready MP4 back to Telegram, delete the
video, or go back to the channel video list. `/restore_all_videos` starts the
restore-all confirmation flow. Renaming changes only `display_name`. Deleting a
channel is rejected while active media or pending device deletion still
references it.

Upload flow:

1. User sends Telegram `video` or `document` media.
2. Bot downloads the Telegram file to a temporary server path.
3. Bot shows explicit channel choices from the SQLite registry.
4. User chooses a channel.
5. Bot calls `UploadProcessor.process_upload(...)`.
6. Server stores both original media and converted Pi-ready `.mp4` under
   `media/library/<channel_id>/<item_id>/...`, validates the converted file with
   `ffprobe`, then marks it `pending_delivery` for Pi delivery.

If the first converted output does not match the Rick TV ready profile, the
server retries conversion once with stricter output flags. If validation still
fails, the upload is marked failed and is not returned by `/api/v1/ready`.

The Telegram restore-all action requeues active available library items so a
replacement Pi can download the media again. Deleting a concrete video from the
channel video detail view is a hard library delete. The server removes both
original and converted media files immediately, marks the item
`pending_device_delete`, and returns it in `/api/v1/ready` under `deletions` until
the Pi confirms `/api/v1/delete-ack/{item_id}`. The Pi delete command contains
`id`, `channel_id`, and `filename`; missing local files are treated as already
deleted and still acknowledged.

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
  'http://localhost:8080/api/v1/channels'
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
