# Full Telegram Upload Runner And Server Library Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a full Telegram upload runner, channel registry management, Pi channel sync, and server-side media library restore flow.

**Architecture:** Run the Telegram bot as a separate Docker Compose service using the same `rick-tv-server` image and shared media/config/state volumes. Store channel registry in server config YAML, expose it to the Pi through an authenticated API endpoint, and keep server-side original plus converted media as the recovery source for a replacement Pi.

**Tech Stack:** Python 3.12, python-telegram-bot, FastAPI, PyYAML, pytest, Docker Compose, server-side ffmpeg/ffprobe, JSON/YAML files on mounted volumes.

---

## Summary

Add a complete Telegram runner as a separate Docker Compose service in the existing server image. The runner is restricted to allowlisted Telegram users, registers direct commands in the Telegram command menu, manages channel registry through those commands, accepts video/document-first upload flow, downloads Telegram media, and passes it to `UploadProcessor.process_upload(...)`.

The server becomes the canonical media library: it keeps original uploads and converted Pi-ready MP4 files so a new or repaired Pi can be restored. Restore is admin-triggered from Telegram via "restore all", which requeues the active server library for delivery to the single current Pi installation.

## Implementation Tasks

### Task 1: Server Settings For Bot And Channel Registry

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/config.py`
- Modify: `rick-tv-server/src/rick_tv_server/main.py`
- Modify: `rick-tv-server/.env.example`
- Modify: `rick-tv-server/tests/test_main.py`

- [x] Add server settings for `telegram_bot_token`, `telegram_allowed_user_ids`, and `channels_path`.
- [x] Load `RICK_TV_TELEGRAM_BOT_TOKEN`, `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`, and `RICK_TV_CHANNELS_PATH` from env.
- [x] Keep API startup working without bot token so `rick-tv-server` can still run independently.
- [x] Add tests for env parsing, default `channels_path`, and allowed-user-id parsing.

### Task 2: Channel Registry Store

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/channels.py`
- Create: `rick-tv-server/tests/test_channels.py`

- [x] Implement YAML-backed channel registry using the current shape:

```yaml
channels:
  01_Citadel:
    display_name: Citadel TV
```

- [x] Provide list/add/rename/delete operations.
- [x] Validate stable filesystem/API channel IDs in the registry.
- [x] Write YAML atomically using a temporary file plus replace.
- [x] Reject delete when `DeliveryStateStore` has active media references for that channel.

### Task 3: Authenticated Channel Registry API

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/api.py`
- Modify: `rick-tv-server/src/rick_tv_server/main.py`
- Modify: `rick-tv-server/tests/test_api.py`

- [x] Add authenticated `GET /api/v1/channels.yml`.
- [x] Return the channel registry YAML from `RICK_TV_CHANNELS_PATH`.
- [x] Preserve existing `/health`, `/ready`, `/download`, and `/ack` behavior.
- [x] Test auth required, content returned, and missing registry returns an empty `channels: {}` document.

### Task 4: Pi Channel Registry Sync

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/config.py`
- Modify: `rick-tv-pi/src/rick_tv_pi/poller.py`
- Modify: `rick-tv-pi/src/rick_tv_pi/main.py`
- Modify: `rick-tv-pi/tests/test_poller.py`
- Modify: `rick-tv-pi/tests/test_main.py`

- [x] Add a Pi-side registry sync method that downloads `/api/v1/channels.yml` with the existing bearer token.
- [x] Write the downloaded YAML to `RICK_TV_METADATA_PATH` atomically when that path is configured.
- [x] Use registry channel IDs for `/api/v1/ready` polling.
- [x] Keep navigation/playlists limited to local playable `.mp4` directories.
- [x] Test first-delivery behavior for a channel known from registry but not yet playable locally.

### Task 5: Multi-Process Safe Delivery State

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Modify: `rick-tv-server/tests/test_state.py`

- [x] Reload state from disk before read operations that affect API/bot visibility.
- [x] Add file locking around read-modify-write operations.
- [x] Keep the existing atomic temp-file replace behavior.
- [x] Test that an API store instance sees pending items created by a separate bot store instance.
- [x] Test that two sequential store instances preserve both updates instead of overwriting stale state.

### Task 6: Server Media Library Semantics

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/uploads.py`
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Modify: `rick-tv-server/tests/test_upload_flow.py`
- Modify: `rick-tv-server/tests/test_state.py`

- [x] Preserve both original upload and converted Pi-ready MP4 after successful conversion.
- [x] Treat converted MP4 as the active delivery/restoration artifact.
- [x] Keep acknowledged media restorable until a concrete channel-video delete removes it from the library.
- [x] Add restore-all state operation that requeues every active archived library item as pending without duplicating media files.
- [x] Keep restore scope single-Pi; do not add device IDs or per-device ack state.

### Task 7: Telegram Access Control And Runner Entry Point

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/bot_runner.py`
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/tests/test_bot.py`

- [x] Build a `python-telegram-bot` `Application` from server settings, channel registry store, delivery state store, and upload processor.
- [x] Reject users whose Telegram user ID is not in `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`.
- [x] Keep handler logic testable with fake update/context objects.
- [x] Run the bot with long polling, not webhooks.

### Task 8: Telegram Channel CRUD Menu

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/tests/test_bot.py`

- [x] Register `/add_channel`, `/list_channels`, and `/restore_all_videos` in the Telegram command menu.
- [x] Add direct command handlers for add/list/restore and per-channel rename/delete actions.
- [x] Add channel from display name and generate the next stable channel ID automatically.
- [x] Rename only `display_name`, never `channel_id`.
- [x] Reject delete for channels with active media references.
- [x] Confirm destructive delete action before applying soft channel removal.

### Task 9: Telegram Upload Flow

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/tests/test_bot.py`

- [x] Implement video-first upload flow.
- [x] Accept media first, then show explicit channel choices from the YAML registry with remembered-channel ordering.
- [x] Accept Telegram `video` and `document` attachments.
- [x] Download the selected attachment to a server-side temporary upload path.
- [x] Call `UploadProcessor.process_upload(...)` through `asyncio.to_thread(...)`.
- [x] Reply with accepted/pending message on success.
- [x] Reply with a failure message and create no deliverable item on download/conversion failure.

### Task 10: Telegram Restore All

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/tests/test_bot.py`

- [x] Add admin action "restore all".
- [x] Require confirmation before requeueing media.
- [x] Requeue every active archived library item for delivery.
- [x] Exclude soft-deleted library items.
- [x] Reply with the number of media items requeued.

### Task 11: Docker Compose And Documentation

**Files:**
- Modify: `rick-tv-server/docker-compose.yml`
- Modify: `rick-tv-server/Dockerfile`
- Modify: `docs/rick-tv-server.md`
- Modify: `README.md`
- Modify: `rick-tv-server/tests/test_docker_files.py`

- [x] Add `rick-tv-bot` service sharing image/build and `media/config/state` volumes with `rick-tv-server`.
- [x] Set bot-specific env vars in Compose.
- [x] Document bot token, allowed Telegram users, channel registry YAML path, upload flow, channel video deletion, and restore-all behavior.
- [x] Test Compose includes both services and shared volumes.

### Task 12: End-To-End Contract Coverage

**Files:**
- Modify: `tests/test_end_to_end_contract.py`

- [x] Test first upload to a new registry channel is delivered to an empty Pi media root.
- [x] Test Pi downloads channel registry YAML, polls with registry IDs, downloads pending media, atomically places it, and acks it.
- [x] Test restore all requeues archived library media and delivers it to a fresh Pi media root.

## Acceptance Criteria

- Unauthorized Telegram users cannot upload, manage channels, or restore media.
- Allowlisted users can create channels, upload video/document media, and see the media become pending for Pi delivery.
- Server keeps original uploads and converted ready MP4 files after ack/archive.
- Deleting a channel video removes its server files and queues deletion for the Pi.
- Restore all requeues active archived media and allows a replacement Pi to redownload the library.
- API and bot processes can share state safely through mounted state files.
- Pi can learn registry channels from the server while still showing only local playable `.mp4` channels.

## Verification Commands

Run after implementation:

```bash
cd rick-tv-server && python -m pytest -v
cd ../rick-tv-pi && python -m pytest -v
cd .. && python -m pytest tests/test_end_to_end_contract.py -v
cd rick-tv-server && docker compose config
```

Optional runtime smoke when Docker is available:

```bash
cd rick-tv-server
docker compose build
docker compose up -d
curl -f http://localhost:8080/health
docker compose logs --no-color --tail=80
docker compose down
```

## Assumptions

- Bot uses long polling, not Telegram webhooks.
- Channel IDs are manually entered and stable; renaming does not change IDs.
- Bot CRUD channel registry is the source of truth for upload choices and Pi polling IDs.
- Empty channel directories remain hidden from Pi navigation until `.mp4` exists.
- Server stores both original uploads and converted Pi-ready MP4 until a concrete channel-video delete removes that video from the server library.
- Restore is single-Pi for now; no multi-device identities or per-device ack state.
- Full runner implementation includes state-store multi-process safety in the same plan because separate Compose services require it.
