# Backend Ready Media Validation Design

## Summary

Rick TV should treat the server as the only component responsible for deciding
whether an uploaded video is playable by the Pi videolooper runtime. The server
already owns media conversion through `ffmpeg`, so it should also validate the
converted MP4 through `ffprobe` before exposing the item through `/api/v1/ready`.

The Pi should not require `ffmpeg` or `ffprobe`. It should download server-ready
media, verify the payload checksum, atomically place the file into the target
channel directory, and acknowledge delivery.

## Problem

The current Pi poller downloads pending media and then calls
`validate_ready_profile()`, which shells out to `ffprobe`. The legacy
videolooper image does not include `ffprobe`, so a correctly downloaded file can
be rejected locally before placement. The server keeps the item in `pending`
state, and the Pi repeatedly redownloads it.

This puts the media compatibility decision in the least convenient place: a
legacy playback appliance that should stay small and stable.

## Goals

- Keep conversion and ready-profile validation on the server.
- Ensure `/api/v1/ready` only exposes media that passed backend validation.
- Retry backend conversion once if the first converted output fails validation.
- Keep Pi delivery lightweight: download, checksum, atomic placement, ack.
- Remove Pi runtime dependency on `ffprobe` and `ffmpeg`.
- Make Telegram upload failures understandable when backend validation fails.

## Non-Goals

- Do not install `ffmpeg` on the Pi as part of normal operation.
- Do not change the target playable profile in this work.
- Do not add Pi-side transcoding or repair logic.
- Do not change videolooper itself.

## Architecture

### Server

`UploadProcessor.process_upload(...)` remains the entry point for Telegram media
uploads. After copying the original file and marking the item as converting, it
will:

1. Convert the source media to the target MP4 profile.
2. Validate the converted output with a server-side ready-profile validator.
3. If validation fails, run one retry conversion with stricter explicit output
   options.
4. Validate the retry output.
5. Mark the item `pending` only when validation succeeds.

If both validation attempts fail, the item must not be exposed through
`/api/v1/ready`. The state store should record a terminal failed status with a
short error message so the Telegram runner can report the upload failure instead
of leaving the item stuck in `converting`.

The existing Pi validator logic should be moved or mirrored into server code,
for example as `rick_tv_server.validator`, so the server owns the `ffprobe`
dependency. The Docker image already installs `ffmpeg`, which includes
`ffprobe`.

### Pi

`Poller._deliver(...)` should no longer call `validate_ready_profile(...)`.
For each ready item it should:

1. Download the file from `download_url`.
2. Compare the downloaded bytes with the provided `sha256`, if present.
3. Write to a temporary path under `.downloads`.
4. Atomically replace the final file in the channel directory.
5. POST `/api/v1/ack/{item_id}`.

If checksum validation fails or file placement raises an error, the Pi should
remove the temp file and leave the item unacked so the next poll can retry.

## Failure Behavior

If server conversion succeeds but validation fails, the server performs one retry
conversion. If retry validation fails too, the upload is marked failed and does
not enter the ready queue. Telegram should send a concise failure message
explaining that the video could not be prepared for Rick TV playback.

If the Pi downloads a server-ready item but checksum validation fails, it should
not ack the item. This remains a delivery/integrity failure, not a media-profile
failure.

## Tests

Server tests should cover:

- `UploadProcessor` marks an item pending only after converter and validator
  success.
- First validation failure triggers exactly one retry conversion.
- Retry validation success marks the retry artifact pending.
- Two validation failures keep the item out of the ready queue and surface an
  upload failure.
- Failed upload state persists a short error message for Telegram reporting.
- The server validator accepts and rejects mocked `ffprobe` profiles.

Pi tests should cover:

- Delivery no longer calls `validate_ready_profile`.
- Successful download plus matching checksum places the file and sends ack.
- Checksum mismatch removes temp data and does not ack.

End-to-end contract tests should be updated so the ready artifact is treated as
server-validated media. The Pi contract should verify delivery and ack without
requiring local `ffprobe`.

## Documentation

README and Pi documentation should say that the server prepares and validates
playable MP4 files for videolooper. Pi setup should not list `ffmpeg` or
`ffprobe` as runtime requirements.
