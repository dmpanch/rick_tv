# Touch navigation implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement and verify this plan task by task.

**Goal:** Swipe vertically between channels and horizontally between videos, while reducing the CPU load diagnosed on the Pi.

**Architecture:** Keep evdev and the existing FIFO. Interpret four directions, route channel actions through ChannelNavigator, and send explicit next/previous video commands to the running VideoLooper. Cache unchanged directory contents in the Pi controller and reduce the VideoLooper polling frequency.

**Tech stack:** Python 3.7 on Raspberry Pi Zero W, evdev, OMXPlayer, pytest on the development machine.

**Spec:** The user's request in this chat: up/down changes channels, right/left changes videos. Up and right select next; down and left select previous. Preserve the existing 60-pixel threshold, dominant-axis rejection, and 0.5-second cooldown. With one channel, vertical swipes remain a no-op; horizontal swipes still navigate its playlist and wrap at either end. Keep bot channel semantics unchanged. Deployment includes a backup and a brief service restart.

## Global constraints

- Python 3.7 compatibility, no new runtime dependencies.
- No media deletion, re-download, credential output, or NAS changes.
- Preserve periodic shuffle, media discovery, empty channels, and FIFO retry behavior.
- Keep touch processing responsive; do not reduce its 0.1-second runtime tick.

## Review focus

- Diagonal gestures and axis remapping must not select the wrong action.
- Previous-video must go to the preceding file, including wraparound and repeated commands.
- FIFO command ordering must preserve channel selection followed by video navigation.
- Cached file lists must invalidate after additions, removals, or channel recreation.
- Service deployment must preserve existing settings and allow rollback.

### Task 1: Four-direction touch controls

Files: `touch.py`, `main.py`, `videolooper.py`, their tests, and the VideoLooper override.

Interfaces: TouchInterpreter emits `next_video`, `previous_video`, `next`, or `previous`; existing channel action names remain compatible. VideolooperController exposes `next_video()` and `previous_video()`, transmitting explicit FIFO commands. VideoLooper applies them against its actual playlist position.

- [x] Add failing gesture, runtime-routing, and real FIFO playback tests, including playlist boundaries.
- [x] Implement the minimal handlers, maintaining command order and suppressing the automatic interstitial for manual skips.
- [x] Run focused tests and fix failures.

### Task 2: Remove repeated media scans

Files: `videolooper.py`, the VideoLooper override, and focused behavior tests.

Interfaces: Cache file lists using directory identity and modification metadata. Keep existing sync/rescan APIs and their externally visible timing. Poll the player/FIFO every 50 ms, and external directory changes once per second.

- [x] Add failing tests proving stable directories are not enumerated repeatedly, while additions/removals and scheduled shuffle remain visible.
- [x] Implement caching and bounded directory polling.
- [x] Run the complete repository suite.

### Task 3: Verify and deploy

- [x] Review changes independently; address important findings with regression tests.
- [x] Update user-facing control documentation.
- [x] Back up the installed modules and VideoLooper egg on the Pi; deploy only changed modules and override, compile with Python 3.7, then restart the two services.
- [x] Verify forward/backward commands on the actual playlist, inspect service errors, and repeat the CPU measurement.

## Progress

Baseline: 217 tests passed. New navigation tests first reproduced missing actions and wrong video selections. Cache tests reproduced repeated enumeration and directory polling. Focused navigation checks: 71 passed. Full suite after both tasks: 243 passed; after the review fix: 245 passed. Work is isolated in the app-managed `touch-navigation` worktree.

Ruling: preserve the existing `next`/`previous` channel action names and add explicit video actions, keeping channel navigation and bot interfaces compatible.

Ruling: use the actual installed VideoLooper model as a GPL-attributed test fixture so previous-video, wraparound, and play-count behavior are exercised against the deployed model.

Independent review found one P2: video commands could reach the old channel after a failed channel selection. Added two failing regression cases and retry the selected channel before sending a video command. Both recoverable and persistent FIFO failures now pass.

Deployment completed on the Pi. Backup: `/home/pi/rick-tv/backups/touch-navigation-20261029-235620`. The changed modules compiled with Python 3.7; both services are active, and the imported player exposes the new handler. All 474 media files remain present.

Live FIFO verification selected the exact next playlist file in 1.29 seconds and returned to the previous file in 1.26 seconds. The subsequent 15.3-second steady playback sample measured 41.5% total CPU, versus 98.6% before the change. Rick TV runtime used 15.7%, VideoLooper 1.0%, and OMXPlayer 19.8%. Temperature was 53 C with no throttling.

Physical swipes are not yet verified: the user could not test the screen. The four-direction interpreter, runtime routing, and FIFO playback were verified separately. Preexisting OMXPlayer abort messages and synchronous network polling are outside this change; no claim is made that this update fixes them.
