# Channel Video Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add per-channel Telegram video listing, Telegram download, and server-plus-Pi deletion for individual videos.

**Architecture:** The server remains the canonical media library. The bot lists active media from `DeliveryStateStore`, sends converted MP4 files back to Telegram, and marks videos as server-deleted plus pending device deletion. The Pi poller receives deletion commands from the existing `/api/v1/ready` response and confirms them with a dedicated delete ack endpoint after local file removal.

**Tech Stack:** Python, python-telegram-bot, FastAPI, httpx, pytest.

---

### Task 1: Server Library State

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Test: `rick-tv-server/tests/test_state.py`

- [x] **Step 1: Write failing state tests**

Add tests that create uploaded/converted media in one channel, ack it to archive, call a new `delete_item_from_channel(item_id)` method, and assert:
- active channel lists exclude deleted media;
- original and converted files under `settings.media_dir` are removed;
- the item becomes `deleted_server_side`;
- `device_delete_items_for_channels([channel_id])` returns the item until `ack_device_delete(item_id)`;
- `ack_device_delete(item_id)` changes status to `deleted_from_library`.

- [x] **Step 2: Run state tests red**

Run:

```bash
.venv/bin/python -m pytest rick-tv-server/tests/test_state.py -v
```

Expected: new tests fail because the new methods do not exist.

- [x] **Step 3: Implement state methods**

Add methods on `DeliveryStateStore`:
- `list_active_items_for_channel(channel_id: str) -> list[DeliveryItem]`
- `delete_item_from_channel(item_id: str) -> DeliveryItem`
- `device_delete_items_for_channels(channel_ids: list[str]) -> list[DeliveryItem]`
- `ack_device_delete(item_id: str) -> DeliveryItem`

Use the existing quarantine helpers so server-side file deletion rolls back if persistence fails.

- [x] **Step 4: Run state tests green**

Run:

```bash
.venv/bin/python -m pytest rick-tv-server/tests/test_state.py -v
```

Expected: all state tests pass.

### Task 2: Server API Delete Commands

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/api.py`
- Test: `rick-tv-server/tests/test_api.py`

- [x] **Step 1: Write failing API tests**

Add tests asserting `/api/v1/ready?channels=01_Citadel` returns both:
- `items`: existing pending download items;
- `deletions`: deleted-server-side items with `id`, `channel_id`, and `filename`.

Add tests for `POST /api/v1/delete-ack/{item_id}` requiring bearer auth and moving the item from `deleted_server_side` to `deleted_from_library`.

- [x] **Step 2: Run API tests red**

Run:

```bash
.venv/bin/python -m pytest rick-tv-server/tests/test_api.py -v
```

Expected: new tests fail because `deletions` and `delete-ack` are missing.

- [x] **Step 3: Implement API contract**

Update `ready()` to include `"deletions"` alongside `"items"`. Add `delete_ack()` endpoint that calls `state_store.ack_device_delete(item_id)`.

- [x] **Step 4: Run API tests green**

Run:

```bash
.venv/bin/python -m pytest rick-tv-server/tests/test_api.py -v
```

Expected: all API tests pass.

### Task 3: Pi Poller Device Deletion

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/poller.py`
- Test: `rick-tv-pi/tests/test_poller.py`
- Test: `tests/test_end_to_end_contract.py`

- [x] **Step 1: Write failing poller tests**

Add tests asserting the Pi poller removes `media_root/<channel_id>/<filename>` for each deletion returned by `/api/v1/ready`, then posts `/api/v1/delete-ack/<item_id>`. Deleting a missing local file should still ack.

- [x] **Step 2: Run poller tests red**

Run:

```bash
.venv/bin/python -m pytest rick-tv-pi/tests/test_poller.py tests/test_end_to_end_contract.py -v
```

Expected: new tests fail because the poller ignores deletions.

- [x] **Step 3: Implement deletion handling**

Add a `DeleteItem` dataclass, parse `response.json().get("deletions", [])`, unlink the target file if it exists, and post delete ack. Keep delivery behavior unchanged.

- [x] **Step 4: Run poller tests green**

Run:

```bash
.venv/bin/python -m pytest rick-tv-pi/tests/test_poller.py tests/test_end_to_end_contract.py -v
```

Expected: all poller and contract tests pass.

### Task 4: Telegram Channel Video UI

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Test: `rick-tv-server/tests/test_bot.py`

- [x] **Step 1: Write failing bot tests**

Add tests asserting:
- selected channel view includes `List all videos`;
- `channel_videos:<channel_id>` shows one button per active video;
- `channel_video:<item_id>` shows `Download`, `Delete`, and `Back`;
- download sends the converted MP4 back to Telegram;
- delete calls `delete_item_from_channel(item_id)` and returns to the channel video list.

- [x] **Step 2: Run bot tests red**

Run:

```bash
.venv/bin/python -m pytest rick-tv-server/tests/test_bot.py -v
```

Expected: new tests fail because the new callbacks and buttons do not exist.

- [x] **Step 3: Implement bot callbacks**

Extend the channel callback handler for:
- `channel_videos:<channel_id>`
- `channel_video:<item_id>`
- `channel_video_download:<item_id>`
- `channel_video_delete:<item_id>`

Use `reply_video` for downloads and server-side delete state for deletion.

- [x] **Step 4: Run bot tests green**

Run:

```bash
.venv/bin/python -m pytest rick-tv-server/tests/test_bot.py -v
```

Expected: all bot tests pass.

### Task 5: Docs, Full Verification, Commit

**Files:**
- Modify: `README.md`
- Modify: `docs/rick-tv-server.md`

- [x] **Step 1: Update docs**

Document that channel detail has `List all videos`, that video detail can download or delete, and that deletion removes server files immediately while the Pi removes the local copy on the next successful poll.

- [x] **Step 2: Run full verification**

Run:

```bash
.venv/bin/python -m pytest -v
git diff --check
```

Expected: all tests pass and whitespace check is clean.

- [x] **Step 3: Commit and push**

Run:

```bash
git add README.md docs/rick-tv-server.md docs/superpowers/plans/2026-06-17-channel-video-management.md rick-tv-server/src/rick_tv_server rick-tv-server/tests rick-tv-pi/src/rick_tv_pi rick-tv-pi/tests tests/test_end_to_end_contract.py
git commit -m "feat: manage channel videos from telegram"
git push
```

Expected: feature branch is pushed with the implementation.

