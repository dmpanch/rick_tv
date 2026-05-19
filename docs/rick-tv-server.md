# Rick TV Server Deployment

The Rick TV server exposes the FastAPI delivery API and persists queue state on
disk. The container image includes `ffmpeg` for media conversion support and
runs Uvicorn on port `8080`.

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

After the public `/health` endpoint is available, extend the smoke run with a
reachability check:

```bash
docker compose up -d
curl -f http://localhost:8080/health
docker compose logs --no-color --tail=50
docker compose down
```
