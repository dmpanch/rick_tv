# Framebuffer Placeholder Investigation Plan

## Summary
Разобраться с нестабильным показом raw framebuffer заглушек на legacy Pi image.
Ожидаемое поведение: переключение канала показывает только
`transition-placeholder.fb`, смена видео внутри текущего канала показывает
только `interstitial-ad.fb`, экран не мигает лишними кадрами и Pi не уходит в
kernel panic.

## Investigation Tasks
- [ ] Собрать факты с Pi: `journalctl -u rick-tv-pi.service`, supervisor logs для
  `video_looper`, `dmesg`, частоту воспроизведения проблемы, текущие значения
  `/sys/class/graphics/fb0/*`.
- [x] Добавить диагностические логи в patched `video_looper.py` вокруг FIFO command,
  `self._player.stop(0)`, `_rick_tv_show_transition_placeholder()`,
  `_rick_tv_show_interstitial_ad()`, `self._player.play(...)`, и playlist reload.
- [ ] Воспроизвести отдельно три сценария: channel switch, natural next video inside
  channel, playlist refresh for same channel.
- [x] Зафиксировать правило показа: channel switch suppresses the next interstitial;
  in-channel video change never draws transition placeholder.
- [ ] Проверить, является ли raw `/dev/fb0` запись источником риска. Если да,
  подготовить замену: omxplayer/videolooper-native overlay, pygame-only OSD, or
  pre-roll MP4 placeholder instead of direct framebuffer writes.

## Current Implementation
- FIFO playlist commands now log command details, current playlist state, mtime,
  player stop, playlist reload, placeholder draw path, and `player.play(...)`.
- A command for a different playlist is treated as channel switch: it draws only
  `transition-placeholder.fb` and suppresses the next interstitial.
- A command for the same playlist with a changed mtime is treated as
  same-channel playlist refresh: it does not draw the transition placeholder and
  leaves the normal in-channel interstitial path responsible for the next video.
- Source tests cover the draw-path invariants. Hardware evidence and dmesg
  stress results are still required before replacing raw `/dev/fb0` writes.

## Test Plan
- [x] Unit/source tests assert exactly one transition draw path for FIFO channel
  commands and exactly one interstitial draw path before in-channel playback.
- [ ] Manual Pi test records logs and video/photo evidence for channel switch and
  in-channel transition.
- [ ] `dmesg` after stress test has no framebuffer, GPU, or kernel panic errors.

## Assumptions
- This task is investigation-first; do not remove the existing `.fb` assets until
  the replacement path is proven on real hardware.
- Legacy `videolooper` remains the playback runtime unless this investigation
  proves it is the root cause.
