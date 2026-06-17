# Rick TV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working Rick TV system: a non-Dockerized Raspberry Pi appliance client and a Dockerized Telegram/upload/conversion/delivery server.

**Architecture:** Use two Python projects in one repo: `rick-tv-pi` for playable channel discovery, server registry sync, videolooper playback control, touch swipes, polling, download, checksum verification, and atomic placement; `rick-tv-server` for the Telegram upload runner, channel registry management, conversion, ready-profile validation, authenticated HTTP delivery, and server-authoritative state/library. Server state lives in mounted files/volumes and Docker logs go to stdout/stderr; the Pi keeps no durable delivery logs.

**Tech Stack:** Pi Python `>=3.7` for the legacy Raspberry Pi OS image; server Python 3.12; pytest, FastAPI, Uvicorn, python-telegram-bot, PyYAML, httpx, server-side ffmpeg/ffprobe, Docker Compose, systemd service docs for Pi runtime.

---

## File Map

- `rick-tv-pi/pyproject.toml`: Pi package metadata, dependencies, pytest config.
- `rick-tv-pi/src/rick_tv_pi/config.py`: Pi settings loaded from env or YAML.
- `rick-tv-pi/src/rick_tv_pi/channels.py`: playable channel directory discovery, ordering, metadata merge.
- `rick-tv-pi/src/rick_tv_pi/videolooper.py`: videolooper playlist generation, playback-facing state, and FIFO channel switching.
- `rick-tv-pi/src/rick_tv_pi/touch.py`: swipe/tap interpretation with cooldown.
- `rick-tv-pi/src/rick_tv_pi/poller.py`: authenticated channel registry sync, polling, download, checksum verification, atomic move, ack timing.
- `rick-tv-pi/src/rick_tv_pi/main.py`: Pi CLI entrypoint that wires scanner, videolooper, touch, and poller.
- `rick-tv-pi/tests/`: Pi unit and fake-server tests.
- `rick-tv-pi/systemd/rick-tv-pi.service`: Pi service template with stdout/stderr journaling only.
- `rick-tv-server/pyproject.toml`: server package metadata, dependencies, pytest config.
- `rick-tv-server/src/rick_tv_server/config.py`: server settings and conversion profile.
- `rick-tv-server/src/rick_tv_server/state.py`: JSON-backed queue, archive, user selection state.
- `rick-tv-server/src/rick_tv_server/converter.py`: ffmpeg conversion to Pi-ready MP4 profile.
- `rick-tv-server/src/rick_tv_server/validator.py`: ffprobe validation for server-ready MP4 profile.
- `rick-tv-server/src/rick_tv_server/api.py`: authenticated FastAPI polling, download, ack endpoints.
- `rick-tv-server/src/rick_tv_server/bot.py`: Telegram upload/list/delete/confirmation/restore flows.
- `rick-tv-server/src/rick_tv_server/bot_runner.py`: Telegram long-polling runner entrypoint.
- `rick-tv-server/src/rick_tv_server/main.py`: server process entrypoint.
- `rick-tv-server/tests/`: server unit, API, bot, conversion, Docker smoke tests.
- `rick-tv-server/Dockerfile`: production server image.
- `rick-tv-server/docker-compose.yml`: mounted media/config/state volumes, published port, restart policy.
- `docs/rick-tv-pi.md`: Pi setup/runtime notes.
- `docs/rick-tv-server.md`: server setup/runtime notes.

## Implementation Tasks

## Completion Audit

Audited against the current repository state on 2026-06-17. These checkboxes mark implementation artifacts present in code, tests, docs, and git history. Historical red/green test-run steps remain below as originally planned; current verification uses the project-local `.venv`.

- [x] Task 1: Pi package scaffold exists.
- [x] Task 2: Server package scaffold exists.
- [x] Task 3: Pi channel discovery ordering exists and tests cover playable `.mp4` channel filtering.
- [x] Task 4: Pi channel metadata rules exist and tests cover missing metadata behavior.
- [x] Task 5: Pi videolooper playable channel filtering exists and tests cover master playlist filtering.
- [x] Task 6: Pi videolooper channel switch rescan exists and tests cover playlist rewrite/FIFO command behavior.
- [x] Task 7: Pi touch swipe interpretation exists and tests cover left/right/tap behavior.
- [x] Task 8: Pi touch cooldown exists and tests cover repeated swipe suppression.
- [x] Task 9: Server ready-profile validator exists and tests cover ffprobe profile acceptance/rejection.
- [x] Task 10: Pi poll request shape exists and tests cover authenticated ready polling.
- [x] Task 11: Pi download, checksum verification, atomic move, and ack timing exist and tests cover ack-after-placement.
- [x] Task 12: Pi retry/redelivery behavior exists and tests cover failed checksum/download and overwrite redelivery.
- [x] Task 13: Pi main wiring, systemd service, touch queue, videolooper settings, and runtime docs exist.
- [x] Task 14: Server settings and JSON-backed delivery state exist.
- [x] Task 15: Server pending-until-ack lifecycle exists.
- [x] Task 16: Authenticated ready endpoint exists.
- [x] Task 17: Download and ack endpoints exist.
- [x] Task 18: Server conversion profile exists.
- [x] Task 19: Upload-to-pending processing exists.
- [x] Task 20: Telegram explicit channel choice helpers exist.
- [x] Task 21: Telegram pending list/cancel helpers exist.
- [x] Task 22: Telegram archive list/delete confirmation helpers exist.
- [x] Follow-Up Task: Full Telegram upload runner exists in `rick_tv_server.bot_runner`.
- [x] Task 23: Server main, logging setup, Dockerfile, Compose file, and deployment docs exist.
- [x] Task 24: Runtime Docker smoke is confirmed with `docker compose build`, `docker compose up -d`, `/health`, logs, and `docker compose down`.
- [x] Task 25: Public server health endpoint exists.
- [x] Task 26: Repo-level Pi/server contract test exists.
- [x] Task 27: Full Pi verification passes with `.venv/bin/python -m pytest rick-tv-pi/tests -v`.
- [x] Task 28: Full server verification passes with `.venv/bin/python -m pytest rick-tv-server/tests -v` plus Docker smoke.
- [x] Task 29: Automated end-to-end verification passes with `.venv/bin/python -m pytest tests/test_end_to_end_contract.py -v` and root `.venv/bin/python -m pytest -v`.

### Task 1: Scaffold Pi Package

**Files:**
- Create: `rick-tv-pi/pyproject.toml`
- Create: `rick-tv-pi/src/rick_tv_pi/__init__.py`
- Create: `rick-tv-pi/tests/conftest.py`

- [ ] **Step 1: Create failing packaging check**

Create `rick-tv-pi/tests/test_package_import.py`:

```python
def test_package_imports():
    import rick_tv_pi

    assert rick_tv_pi.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_package_import.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'rick_tv_pi'`.

- [ ] **Step 3: Add minimal package metadata**

Create `rick-tv-pi/pyproject.toml` with project name `rick-tv-pi`, Python `>=3.7`, dependencies `httpx`, `PyYAML`, and test dependency `pytest`. Create `rick-tv-pi/src/rick_tv_pi/__init__.py` defining `__version__ = "0.1.0"`. Keep `tests/conftest.py` empty for now.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rick-tv-pi && python -m pip install -e ".[test]" && pytest tests/test_package_import.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi && git commit -m "chore: scaffold pi package"`

### Task 2: Scaffold Server Package

**Files:**
- Create: `rick-tv-server/pyproject.toml`
- Create: `rick-tv-server/src/rick_tv_server/__init__.py`
- Create: `rick-tv-server/tests/conftest.py`

- [ ] **Step 1: Create failing packaging check**

Create `rick-tv-server/tests/test_package_import.py`:

```python
def test_package_imports():
    import rick_tv_server

    assert rick_tv_server.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_package_import.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'rick_tv_server'`.

- [ ] **Step 3: Add minimal package metadata**

Create `rick-tv-server/pyproject.toml` with project name `rick-tv-server`, Python `>=3.12`, dependencies `fastapi`, `uvicorn[standard]`, `python-telegram-bot`, `httpx`, `PyYAML`, and test dependencies `pytest`, `pytest-asyncio`. Create `rick-tv-server/src/rick_tv_server/__init__.py` defining `__version__ = "0.1.0"`. Keep `tests/conftest.py` empty for now.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rick-tv-server && python -m pip install -e ".[test]" && pytest tests/test_package_import.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server && git commit -m "chore: scaffold server package"`

### Task 3: Pi Channel Discovery Ordering

**Files:**
- Create: `rick-tv-pi/src/rick_tv_pi/channels.py`
- Create: `rick-tv-pi/tests/test_channels.py`

- [ ] **Step 1: Write failing channel ordering test**

In `rick-tv-pi/tests/test_channels.py`, create directories `01_Citadel`, `02_Interdimensional_Cable`, `03_Empty`, `Garage`, `10_Late`, `Garage/Nested`, and a regular file `not_a_channel.mp4`. Add `episode.mp4` only to `01_Citadel`, `02_Interdimensional_Cable`, `10_Late`, and `Garage`. Assert `discover_channels(media_root, metadata_path=None)` returns channel ids in order `["01_Citadel", "02_Interdimensional_Cable", "10_Late", "Garage"]`, excluding `03_Empty`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_channels.py::test_discovers_immediate_directories_in_channel_order -v`

Expected: FAIL with import or function missing.

- [ ] **Step 3: Implement minimal discovery**

In `channels.py`, define frozen dataclass `Channel(id: str, number: int, display_name: str | None, path: Path)`. Implement `discover_channels(media_root: Path, metadata_path: Path | None) -> list[Channel]`; include only immediate directories containing at least one `.mp4`, parse leading digits before `_`, sort numbered channels by integer prefix, sort unnumbered channels alphabetically after numbered channels, and assign one-based `number` by final list position.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd rick-tv-pi && pytest tests/test_channels.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/channels.py rick-tv-pi/tests/test_channels.py && git commit -m "feat: discover pi channels"`

### Task 4: Pi Channel Metadata Rules

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/channels.py`
- Modify: `rick-tv-pi/tests/test_channels.py`

- [ ] **Step 1: Write failing metadata test**

Add a test that writes `channels.yml` containing `01_Citadel: {display_name: "Citadel TV"}` and `Missing: {display_name: "Ignored"}`. Assert `01_Citadel.display_name == "Citadel TV"`, missing metadata creates no channel, and `Garage.display_name is None`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_channels.py::test_metadata_only_names_existing_directories -v`

Expected: FAIL because metadata is not loaded.

- [ ] **Step 3: Implement metadata loading**

Update `discover_channels` to load YAML only when `metadata_path` exists. Accept only mapping shape `channels: {channel_id: {display_name: str}}`. Ignore malformed entries and entries for missing directories. Never derive display names from folder names.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-pi && pytest tests/test_channels.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/channels.py rick-tv-pi/tests/test_channels.py && git commit -m "feat: apply pi channel metadata"`

### Task 5: Pi Videolooper Playable Channel Filtering

**Files:**
- Create: `rick-tv-pi/src/rick_tv_pi/videolooper.py`
- Create: `rick-tv-pi/tests/test_videolooper.py`

- [ ] **Step 1: Write failing playable-channel playlist test**

Test `VideolooperController.sync_channels(channels)` with one playable channel containing `episode.mp4` and one defensive input entry whose directory has no `.mp4`. Assert the master playlist includes only the playable channel playlist.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_videolooper.py::test_sync_channels_skips_empty_channel_playlists -v`

Expected: FAIL with missing module or missing playlist behavior.

- [ ] **Step 3: Implement minimal videolooper playlist controller**

Create `PlayableFile` dataclass with `path: Path`. Create `VideolooperController` with `sync_channels(channels)`, `select_channel(channel)`, `rescan_current_channel()`, `screen_state`, and `current_file`. Treat `.mp4` files as playable; write per-channel playlists, but include only channels with playable files in the master playlist.

- [ ] **Step 4: Run test**

Run: `cd rick-tv-pi && pytest tests/test_videolooper.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/videolooper.py rick-tv-pi/tests/test_videolooper.py && git commit -m "feat: generate videolooper playlists"`

### Task 6: Pi Videolooper Channel Switch Rescan

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/videolooper.py`
- Modify: `rick-tv-pi/tests/test_videolooper.py`

- [ ] **Step 1: Write failing rescan command test**

Select a playable channel, add a new `.mp4`, call `rescan_current_channel()`, and assert the channel playlist is rewritten, `screen_state == "playing"`, `current_file.path.name` reflects a playable file, and the videolooper FIFO command writer receives that channel playlist path.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_videolooper.py::test_rescan_sends_command_when_channel_files_change -v`

Expected: FAIL because rescan does not update videolooper state yet.

- [ ] **Step 3: Implement rescan command path**

Update `rescan_current_channel()` to rescan `.mp4` files sorted by name, rewrite the channel playlist when files change, set `current_file` and `screen_state`, and send the updated playlist path through the videolooper command writer.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-pi && pytest tests/test_videolooper.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/videolooper.py rick-tv-pi/tests/test_videolooper.py && git commit -m "feat: switch videolooper channels on rescan"`

### Task 7: Pi Touch Swipes

**Files:**
- Create: `rick-tv-pi/src/rick_tv_pi/touch.py`
- Create: `rick-tv-pi/tests/test_touch.py`

- [ ] **Step 1: Write failing swipe tests**

Test `TouchInterpreter(cooldown_seconds=0.5)`: left swipe from `(200, 100)` to `(20, 100)` returns `"next"`, right swipe returns `"previous"`, tap movement under threshold returns `None`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_touch.py -v`

Expected: FAIL with missing module.

- [ ] **Step 3: Implement swipe interpreter**

Define `TouchPoint(x: int, y: int, timestamp: float)` and `TouchInterpreter.interpret(start: TouchPoint, end: TouchPoint) -> Literal["next", "previous"] | None`. Require horizontal delta at least 80 pixels and horizontal movement greater than vertical movement.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-pi && pytest tests/test_touch.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/touch.py rick-tv-pi/tests/test_touch.py && git commit -m "feat: interpret pi touch swipes"`

### Task 8: Pi Touch Cooldown

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/touch.py`
- Modify: `rick-tv-pi/tests/test_touch.py`

- [ ] **Step 1: Write failing cooldown test**

Call two valid left swipes with timestamps less than `cooldown_seconds` apart. Assert first returns `"next"` and second returns `None`. Add a third swipe after cooldown and assert it returns `"next"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_touch.py::test_cooldown_blocks_repeated_swipes -v`

Expected: FAIL because cooldown is not enforced.

- [ ] **Step 3: Implement cooldown**

Store `_last_action_at: float | None` on `TouchInterpreter`. When a swipe action is produced, suppress it if `start.timestamp - _last_action_at < cooldown_seconds`; otherwise update `_last_action_at`.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-pi && pytest tests/test_touch.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/touch.py rick-tv-pi/tests/test_touch.py && git commit -m "feat: debounce pi swipes"`

### Task 9: Server Profile Validator

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/validator.py`
- Create: `rick-tv-server/tests/test_validator.py`

- [x] **Step 1: Write failing validator tests**

Mock an `ffprobe` JSON result for MP4/H.264/yuv420p/AAC at target resolution and assert `validate_ready_profile(path) is True`. Mock wrong pixel format and assert `False`.

- [x] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_validator.py -v`

Expected: FAIL with missing module.

- [x] **Step 3: Implement server-side validation**

Define `ReadyProfile(width: int = 640, height: int = 480, video_codec: str = "h264", pixel_format: str = "yuv420p", audio_codec: str = "aac")`. Implement `probe_media(path, runner=subprocess.run)` and `validate_ready_profile(path, profile=ReadyProfile(), runner=subprocess.run)` in the server package. Validate container format includes `mp4`, video codec, pixel format, audio codec, target width/height, and bitrate ceilings.

- [x] **Step 4: Run tests**

Run: `cd rick-tv-server && pytest tests/test_validator.py -v`

Expected: PASS.

- [x] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/validator.py rick-tv-server/tests/test_validator.py && git commit -m "feat: add server media profile validator"`

### Task 10: Pi Poll Request Shape

**Files:**
- Create: `rick-tv-pi/src/rick_tv_pi/config.py`
- Create: `rick-tv-pi/src/rick_tv_pi/poller.py`
- Create: `rick-tv-pi/tests/test_poller.py`

- [ ] **Step 1: Write failing fake-server poll test**

Use a local fake HTTP handler or `httpx.MockTransport`. Assert `Poller.poll_once(channels)` sends `GET /api/v1/ready?channels=01_Citadel,Garage` with header `Authorization: Bearer test-token`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_poller.py::test_poll_sends_authenticated_known_channels -v`

Expected: FAIL with missing poller.

- [ ] **Step 3: Implement config and poll shell**

Define `PiSettings(server_base_url: str, api_token: str, media_root: Path, poll_interval_seconds: int = 60, metadata_path: Path | None = None)`. Define `Poller(settings, http_client)` with `poll_once(channels: list[Channel])` that performs the authenticated GET and parses JSON `{"items": []}`.

- [ ] **Step 4: Run test**

Run: `cd rick-tv-pi && pytest tests/test_poller.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/config.py rick-tv-pi/src/rick_tv_pi/poller.py rick-tv-pi/tests/test_poller.py && git commit -m "feat: poll server for ready media"`

### Task 11: Pi Download, Atomic Move, And Ack Timing

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/poller.py`
- Modify: `rick-tv-pi/tests/test_poller.py`

- [ ] **Step 1: Write failing successful delivery test**

Fake server returns one server-validated item `{id, channel_id, filename, download_url, sha256}`. Fake download returns bytes matching `sha256`. Assert the file is first written under `media_root/.downloads`, atomically moved into `media_root/<channel_id>/<filename>`, and `POST /api/v1/ack/<id>` happens only after the destination exists.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_poller.py::test_download_checksum_atomic_move_then_ack -v`

Expected in the original red step: FAIL before the download flow implementation exists.

- [ ] **Step 3: Implement delivery flow**

Add `ReadyItem(id, channel_id, filename, download_url, sha256)`. In `poll_once`, for each item whose channel is known: download with auth header, write to `media_root/.downloads/<id>.tmp`, optionally verify SHA-256 when provided, call validator, create destination channel directory if missing only when it was in known channels, use `Path.replace()` for atomic placement, then POST ack. Do not write durable delivery logs.

- [ ] **Step 4: Run test**

Run: `cd rick-tv-pi && pytest tests/test_poller.py::test_download_checksum_atomic_move_then_ack -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/poller.py rick-tv-pi/tests/test_poller.py && git commit -m "feat: download and acknowledge delivered media"`

### Task 12: Pi Retry And Redelivery Behavior

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/poller.py`
- Modify: `rick-tv-pi/tests/test_poller.py`

- [ ] **Step 1: Write failing retry tests**

Add tests for checksum mismatch and failed download. Assert no ack is sent and destination file is absent. Add redelivery test where destination exists; assert second successful delivery overwrites via atomic replace and sends ack.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rick-tv-pi && pytest tests/test_poller.py::test_checksum_mismatch_does_not_ack tests/test_poller.py::test_redelivery_overwrites_destination_and_acks -v`

Expected: FAIL because retry/redelivery cases are incomplete.

- [ ] **Step 3: Implement retry-safe behavior**

Catch network, checksum, and filesystem exceptions per item. Remove temp files on failure when present. Leave server item unacked. Permit `Path.replace()` over existing destination for Phase 1 duplicate-transfer behavior.

- [ ] **Step 4: Run fake-server tests**

Run: `cd rick-tv-pi && pytest tests/test_poller.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi/src/rick_tv_pi/poller.py rick-tv-pi/tests/test_poller.py && git commit -m "feat: retry pi deliveries without durable state"`

### Task 13: Pi Main Wiring And Service

**Files:**
- Create: `rick-tv-pi/src/rick_tv_pi/main.py`
- Create: `rick-tv-pi/systemd/rick-tv-pi.service`
- Create: `docs/rick-tv-pi.md`
- Create: `rick-tv-pi/tests/test_main.py`

- [ ] **Step 1: Write failing CLI config test**

Test that `load_settings_from_env()` reads `RICK_TV_SERVER_URL`, `RICK_TV_API_TOKEN`, `RICK_TV_MEDIA_ROOT`, optional `RICK_TV_METADATA_PATH`, and defaults poll interval to 60 seconds.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-pi && pytest tests/test_main.py -v`

Expected: FAIL because entrypoint/config loading is missing.

- [ ] **Step 3: Implement Pi entrypoint and service docs**

Add `main.py` with `load_settings_from_env()` and `main()` loop that discovers playable channels, initializes videolooper/touch/poller, polls every 60 seconds, and rescans the selected videolooper channel for file changes. Add systemd unit with `ExecStart=/usr/bin/python -m rick_tv_pi.main`, environment file `/etc/rick-tv-pi.env`, no app log file path, and stdout/stderr to journal. Document hardware assumptions, playable-channel filtering, videolooper playback, and no inbound Rick TV ports in `docs/rick-tv-pi.md`.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-pi && pytest -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-pi docs/rick-tv-pi.md && git commit -m "feat: wire pi runtime entrypoint"`

### Task 14: Server Configuration And State Skeleton

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/config.py`
- Create: `rick-tv-server/src/rick_tv_server/state.py`
- Create: `rick-tv-server/tests/test_state.py`

- [ ] **Step 1: Write failing state test**

Test `DeliveryStateStore` can create uploaded item, mark converting, mark pending, and persist/reload JSON from `state/queue.json`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_state.py::test_state_persists_delivery_lifecycle -v`

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement JSON-backed state**

Define `ServerSettings(media_dir: Path, config_dir: Path, state_dir: Path, api_token: str, public_base_url: str)`. Define item statuses `uploaded`, `converting`, `pending`, `canceled`, `delivered`, `archived`, `deleted_server_side`. Implement atomic JSON write using temp file plus replace. Store items, per-user last channel, acknowledgements, and archive index in state JSON.

- [ ] **Step 4: Run state test**

Run: `cd rick-tv-server && pytest tests/test_state.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/config.py rick-tv-server/src/rick_tv_server/state.py rick-tv-server/tests/test_state.py && git commit -m "feat: persist server delivery state"`

### Task 15: Server Pending Until Ack

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Modify: `rick-tv-server/tests/test_state.py`

- [ ] **Step 1: Write failing ack lifecycle test**

Create a pending item. Assert repeated `ready_items_for_channels(["01_Citadel"])` returns it. Call `ack_item(item_id)` and assert status transitions to `delivered`, then `archived`, and ready list no longer includes it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_state.py::test_pending_remains_ready_until_ack -v`

Expected: FAIL because ready/ack behavior is missing.

- [ ] **Step 3: Implement ready and ack methods**

Add `ready_items_for_channels(channel_ids)`, `ack_item(item_id)`, and archive indexing. Keep pending items pending until ack; do not infer delivery from download.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-server && pytest tests/test_state.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/state.py rick-tv-server/tests/test_state.py && git commit -m "feat: keep server deliveries pending until ack"`

### Task 16: Server API Authentication And Ready Endpoint

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/api.py`
- Create: `rick-tv-server/tests/test_api.py`

- [ ] **Step 1: Write failing API auth test**

Using FastAPI `TestClient`, call `GET /api/v1/ready?channels=01_Citadel` without auth and assert 401. Call with `Authorization: Bearer test-token` and assert 200 with pending item JSON.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_api.py::test_ready_endpoint_requires_bearer_token -v`

Expected: FAIL with missing API.

- [ ] **Step 3: Implement API app factory**

Define `create_app(settings, state_store) -> FastAPI`. Implement bearer-token dependency. Implement `GET /api/v1/ready` returning `{"items": [{"id", "channel_id", "filename", "download_url", "sha256"}]}` for requested channels.

- [ ] **Step 4: Run API test**

Run: `cd rick-tv-server && pytest tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/api.py rick-tv-server/tests/test_api.py && git commit -m "feat: expose authenticated ready endpoint"`

### Task 17: Server Download And Ack Endpoints

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/api.py`
- Modify: `rick-tv-server/tests/test_api.py`

- [ ] **Step 1: Write failing download/ack test**

Create pending converted file under mounted media path. Assert authenticated `GET /api/v1/download/{item_id}` returns file bytes and does not change status. Assert authenticated `POST /api/v1/ack/{item_id}` changes status to delivered/archive and returns 204.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_api.py::test_download_does_not_deliver_ack_does -v`

Expected: FAIL because endpoints are missing.

- [ ] **Step 3: Implement endpoints**

Add download endpoint with auth, 404 for missing/canceled/non-pending items, and `FileResponse` from converted media path. Add ack endpoint with auth and idempotent success for already delivered/archive items.

- [ ] **Step 4: Run API tests**

Run: `cd rick-tv-server && pytest tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/api.py rick-tv-server/tests/test_api.py && git commit -m "feat: serve downloads and acknowledgements"`

### Task 18: Server Conversion Profile

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/converter.py`
- Create: `rick-tv-server/tests/test_converter.py`

- [ ] **Step 1: Write failing ffmpeg command test**

Test `build_ffmpeg_command(input_path, output_path, profile)` includes `-f mp4`, `-c:v libx264`, `-pix_fmt yuv420p`, `-c:a aac`, scale to `640:480`, and modest video bitrate such as `700k`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_converter.py::test_ffmpeg_command_targets_pi_ready_profile -v`

Expected: FAIL with missing converter.

- [ ] **Step 3: Implement conversion command**

Define `ConversionProfile(width=640, height=480, video_bitrate="700k", audio_bitrate="96k")`. Implement `build_ffmpeg_command` and `convert_to_ready_mp4(input_path, output_path, profile, runner=subprocess.run)` that writes only `.mp4` output and raises on ffmpeg failure.

- [ ] **Step 4: Run converter tests**

Run: `cd rick-tv-server && pytest tests/test_converter.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/converter.py rick-tv-server/tests/test_converter.py && git commit -m "feat: convert uploads to pi-ready mp4"`

### Task 19: Server Upload To Pending Flow

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Modify: `rick-tv-server/src/rick_tv_server/converter.py`
- Create: `rick-tv-server/tests/test_upload_flow.py`

- [ ] **Step 1: Write failing upload-flow test**

Simulate storing an uploaded file for channel `01_Citadel`. Stub converter success. Assert item status sequence becomes uploaded -> converting -> pending and pending item has converted path, filename, channel id, and SHA-256.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_upload_flow.py -v`

Expected: FAIL with missing orchestration.

- [ ] **Step 3: Implement upload processing service**

Create `rick-tv-server/src/rick_tv_server/uploads.py` with `UploadProcessor.process_upload(user_id, channel_id, source_path, original_filename)`. Store original under `media/uploaded`, converted under `media/converted`, compute SHA-256, and mark pending only after conversion succeeds.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-server && pytest tests/test_upload_flow.py tests/test_state.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/uploads.py rick-tv-server/src/rick_tv_server/state.py rick-tv-server/tests/test_upload_flow.py && git commit -m "feat: process uploads into pending media"`

### Task 20: Telegram Explicit Channel Choices And Last Selection

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/bot.py`
- Create: `rick-tv-server/tests/test_bot.py`

- [ ] **Step 1: Write failing bot choice test**

Using bot handler functions with fake update/context objects, simulate user `42` uploading media after last channel was `Garage`. Assert the response still includes explicit choices for all configured channels, with `Garage` marked or ordered as remembered convenience, not auto-selected.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_bot.py::test_upload_always_shows_explicit_channel_choices -v`

Expected: FAIL with missing bot module.

- [ ] **Step 3: Implement channel-choice bot functions**

Define `ChannelChoice(id, display_name)` and pure functions `build_upload_channel_keyboard(channels, remembered_channel_id)` and `remember_user_channel(user_id, channel_id, state_store)`. Keep Telegram SDK boundary thin so tests cover flow logic without network calls.

- [ ] **Step 4: Run bot test**

Run: `cd rick-tv-server && pytest tests/test_bot.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/bot.py rick-tv-server/tests/test_bot.py && git commit -m "feat: require explicit telegram channel selection"`

### Task 21: Telegram Pending List And Cancel

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Modify: `rick-tv-server/tests/test_bot.py`
- Modify: `rick-tv-server/tests/test_state.py`

- [ ] **Step 1: Write failing pending cancel test**

Create two pending items. Assert bot pending-list formatter shows both. Simulate deleting one pending item and assert state status becomes `canceled`, ready endpoint no longer returns it, and converted file is not eligible for download.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_bot.py::test_pending_delete_marks_canceled tests/test_state.py::test_canceled_pending_is_not_ready -v`

Expected: FAIL because cancellation is missing.

- [ ] **Step 3: Implement pending list/cancel**

Add `list_pending_items()`, `cancel_pending_item(item_id)`, and bot formatters/actions for pending media. Do not delete local Pi files because pending items have not been acknowledged.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-server && pytest tests/test_bot.py tests/test_state.py tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/bot.py rick-tv-server/src/rick_tv_server/state.py rick-tv-server/tests && git commit -m "feat: cancel pending telegram media"`

### Task 22: Telegram Delivered/Archive List And Confirmed Delete

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Modify: `rick-tv-server/tests/test_bot.py`
- Modify: `rick-tv-server/tests/test_state.py`

- [ ] **Step 1: Write failing archive delete test**

Create archived item with converted file. Assert bot archive-list formatter shows it. Simulate delete request and then confirmation. Assert status becomes `deleted_from_library`, archive index removes it, server files remain on disk, and no Pi deletion request is emitted for this legacy archive-list soft delete flow.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_bot.py::test_archive_delete_requires_confirmation_and_is_server_side_only -v`

Expected: FAIL because archive deletion is missing.

- [ ] **Step 3: Implement confirmed archive deletion**

Add `request_archive_delete(item_id)`, `confirm_archive_delete(item_id)`, and bot callbacks for list/delete/confirm. Scope deletion to soft removal from the active library while retaining original and converted server-side files.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-server && pytest tests/test_bot.py tests/test_state.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/bot.py rick-tv-server/src/rick_tv_server/state.py rick-tv-server/tests && git commit -m "feat: delete archived media server-side"`

### Follow-Up Task: Full Telegram Upload Runner

**Status:** Not implemented in the current codebase. The existing bot module provides channel-choice keyboards, pending/archive list helpers, and callback handlers; it does not yet run a complete Telegram media ingestion flow.

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/src/rick_tv_server/main.py`
- Test: `rick-tv-server/tests/test_bot.py`

- [ ] **Step 1: Write failing Telegram media runner test**

Using fake Telegram update/context objects, simulate user `42` selecting channel `01_Citadel` and then sending a media file. Assert the runner downloads the Telegram file to server media storage and calls `UploadProcessor.process_upload(user_id="42", channel_id="01_Citadel", source_path=<downloaded file>, original_filename=<telegram filename>)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_bot.py::test_telegram_media_runner_processes_upload -v`

Expected: FAIL because the full Telegram media runner does not exist yet.

- [ ] **Step 3: Implement the runner**

Add a thin Telegram SDK boundary that records explicit channel selection, accepts a subsequent media message, downloads it to a server-side temporary upload path, and calls `UploadProcessor.process_upload(...)`. Keep conversion and state transitions inside `UploadProcessor`.

- [ ] **Step 4: Run bot tests**

Run: `cd rick-tv-server && pytest tests/test_bot.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/bot.py rick-tv-server/src/rick_tv_server/main.py rick-tv-server/tests/test_bot.py && git commit -m "feat: run telegram upload ingestion"`

### Task 23: Server Main, Logging, And Docker

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/main.py`
- Create: `rick-tv-server/Dockerfile`
- Create: `rick-tv-server/docker-compose.yml`
- Create: `docs/rick-tv-server.md`
- Create: `rick-tv-server/tests/test_docker_files.py`

- [ ] **Step 1: Write failing Docker file tests**

Test `Dockerfile` exists, installs ffmpeg, runs `uvicorn rick_tv_server.main:app`, and `docker-compose.yml` mounts `./media:/var/lib/rick-tv/media`, `./config:/etc/rick-tv`, `./state:/var/lib/rick-tv/state`, publishes `8080:8080`, and has `restart: unless-stopped`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_docker_files.py -v`

Expected: FAIL because Docker files are missing.

- [ ] **Step 3: Implement server process and Docker files**

Create `main.py` that loads env `RICK_TV_MEDIA_DIR`, `RICK_TV_CONFIG_DIR`, `RICK_TV_STATE_DIR`, `RICK_TV_API_TOKEN`, `RICK_TV_PUBLIC_BASE_URL`, initializes state store, exposes `app`, and configures standard logging to stdout/stderr. Create Dockerfile with Python 3.12 slim, ffmpeg install, package install, and Uvicorn command on port 8080. Create Compose file with mounted volumes, published port, token env reference, and restart policy. Document deployment in `docs/rick-tv-server.md`.

- [ ] **Step 4: Run Docker file tests**

Run: `cd rick-tv-server && pytest tests/test_docker_files.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/main.py rick-tv-server/Dockerfile rick-tv-server/docker-compose.yml docs/rick-tv-server.md rick-tv-server/tests/test_docker_files.py && git commit -m "feat: dockerize rick tv server"`

### Task 24: Server Docker Smoke Verification

**Files:**
- Modify: `rick-tv-server/tests/test_docker_files.py`

- [ ] **Step 1: Add smoke command to plan execution notes**

Add a test marker or documented command that builds the image and checks the app imports.

- [ ] **Step 2: Run build smoke**

Run: `cd rick-tv-server && docker compose build`

Expected: image builds successfully and includes ffmpeg.

- [ ] **Step 3: Run container reachability smoke**

Run: `cd rick-tv-server && docker compose up -d && curl -f http://localhost:8080/health && docker compose logs --no-color --tail=50 && docker compose down`

Expected: health endpoint returns 200 and logs appear in Docker stdout/stderr.

- [ ] **Step 4: Commit any documentation tweaks**

Run: `git add rick-tv-server/tests/test_docker_files.py docs/rick-tv-server.md && git commit -m "test: document server docker smoke checks"`

### Task 25: Server Health Endpoint

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/api.py`
- Modify: `rick-tv-server/tests/test_api.py`

- [ ] **Step 1: Write failing health test**

Assert `GET /health` returns `{"status": "ok"}` without bearer auth so Docker and local network reachability checks can use it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rick-tv-server && pytest tests/test_api.py::test_health_endpoint_is_public -v`

Expected: FAIL because health route is missing.

- [ ] **Step 3: Implement health route**

Add public `GET /health` to `create_app`.

- [ ] **Step 4: Run tests**

Run: `cd rick-tv-server && pytest tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add rick-tv-server/src/rick_tv_server/api.py rick-tv-server/tests/test_api.py && git commit -m "feat: add server health endpoint"`

### Task 26: End-To-End Local Contract Test

**Files:**
- Create: `tests/test_end_to_end_contract.py`
- Modify: `pyproject.toml` if a repo-level test runner is introduced

- [ ] **Step 1: Write failing cross-project test**

Create a repo-level pytest that initializes server state with a pending converted MP4, starts FastAPI TestClient or ASGI transport, creates Pi `Poller` with known channel `01_Citadel`, stubs Pi validator to true, runs one poll, and asserts file exists in Pi media root and server state is archived.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_end_to_end_contract.py -v`

Expected: FAIL until imports/test path wiring is configured.

- [ ] **Step 3: Add repo-level test config**

Create root `pyproject.toml` with pytest pythonpath entries for `rick-tv-pi/src` and `rick-tv-server/src`, plus test dependencies documentation. Keep app packages independent.

- [ ] **Step 4: Make contract pass**

Adjust only public interfaces from previous tasks if needed: server ready/download/ack JSON must match Pi `ReadyItem`; Pi ack route must match server route. Do not add a second protocol.

- [ ] **Step 5: Run contract test**

Run: `pytest tests/test_end_to_end_contract.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run: `git add pyproject.toml tests/test_end_to_end_contract.py rick-tv-pi rick-tv-server && git commit -m "test: verify pi server delivery contract"`

### Task 27: Full Pi Verification

**Files:**
- No new files expected unless tests reveal gaps.

- [ ] **Step 1: Run Pi test suite**

Run: `cd rick-tv-pi && pytest -v`

Expected: PASS for channel discovery/metadata, playable-channel filtering, videolooper playlist/channel switching, swipes/taps/cooldown, fake-server polling, checksum mismatch retry, atomic move/ack, and redelivery overwrite.

- [ ] **Step 2: Inspect for durable delivery logs**

Run: `rg -n "delivery.log|sqlite|queue.json|ack.json|open\\(.*log|FileHandler" rick-tv-pi/src rick-tv-pi/tests`

Expected: no Pi durable delivery log/state files. Any stdout/stderr or journald references are acceptable.

- [ ] **Step 3: Commit fixes if needed**

If tests or log scan fail, add focused failing tests first, fix, rerun `cd rick-tv-pi && pytest -v`, then commit with a narrow message.

### Task 28: Full Server Verification

**Files:**
- No new files expected unless tests reveal gaps.

- [ ] **Step 1: Run server test suite**

Run: `cd rick-tv-server && pytest -v`

Expected: PASS for Docker file checks, API auth, ready/download/ack, Telegram upload explicit choices, last selected channel, pending list/cancel, archive list/confirmed soft library removal, conversion profile, and queue lifecycle.

- [ ] **Step 2: Run Docker smoke**

Run: `cd rick-tv-server && docker compose build && docker compose up -d && curl -f http://localhost:8080/health && docker compose logs --no-color --tail=50 && docker compose down`

Expected: build succeeds, health endpoint reachable, logs visible through Docker.

- [ ] **Step 3: Commit fixes if needed**

If tests or smoke fail, add focused failing tests first, fix, rerun relevant command, then commit with a narrow message.

### Task 29: Final End-To-End Verification

**Files:**
- No new files expected unless documentation needs correction.

- [ ] **Step 1: Run all automated tests**

Run: `pytest -v && cd rick-tv-pi && pytest -v && cd ../rick-tv-server && pytest -v`

Expected: all tests pass.

- [ ] **Step 2: Run local E2E flow**

Run the documented manual flow from `docs/rick-tv-server.md`: place sample upload in server media volume, select `01_Citadel`, convert to pending, poll with Pi client pointed at local server, download, validate, atomic move, ack, and confirm server state transitions to delivered/archive.

Expected: converted MP4 appears under Pi `media_root/01_Citadel`, server item is archived, and no Pi durable delivery log is created.

- [ ] **Step 3: Review spec coverage**

Run: `rg -n "TO""DO|TB""D|place""holder|implement ""later" .`

Expected: no unfinished markers remain except irrelevant tool-generated metadata and the explicitly scoped full Telegram upload runner follow-up.

- [ ] **Step 4: Commit final docs/test adjustments**

Run: `git add docs rick-tv-pi rick-tv-server tests pyproject.toml && git commit -m "docs: finalize rick tv verification"` if any final changes were needed.

## Self-Review

- Spec coverage: The plan covers both projects, Pi channel discovery/metadata, playable-channel filtering, server registry sync, videolooper playback, touch swipes and cooldown, polling/download/checksum verification/atomic move/ack, retry/redelivery, no Pi durable delivery state, Telegram upload-list/delete/archive/restore flows, full Telegram upload runner, server conversion and validation profile, Docker deployment, mounted volumes, stdout/stderr logs, and final end-to-end verification.
- Marker scan: No unfinished markers or unspecified "add tests" steps are intentionally present.
- Type consistency: Shared protocol names are stable across tasks: `Channel`, `ReadyItem`, `PiSettings`, `ServerSettings`, `DeliveryStateStore`, `ConversionProfile`, `UploadProcessor`, and `/api/v1/ready`, `/api/v1/download/{item_id}`, `/api/v1/ack/{item_id}`.
