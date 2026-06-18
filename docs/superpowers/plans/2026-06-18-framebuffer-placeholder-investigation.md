# Framebuffer Placeholder Investigation Plan

## Summary
Разобраться с нестабильным показом raw framebuffer заглушек на legacy Pi image.
Ожидаемое поведение: переключение канала показывает только
`transition-placeholder.fb`, смена видео внутри текущего канала показывает
только `interstitial-ad.fb`, экран не мигает лишними кадрами и Pi не уходит в
kernel panic.

## Investigation Tasks
- [x] Собрать факты с Pi: `journalctl -u rick-tv-pi.service`, supervisor logs для
  `video_looper`, `dmesg`, частоту воспроизведения проблемы, текущие значения
  `/sys/class/graphics/fb0/*`.
- [x] Добавить диагностические логи в patched `video_looper.py` вокруг FIFO command,
  `self._player.stop(0)`, `_rick_tv_show_transition_placeholder()`,
  `_rick_tv_show_interstitial_ad()`, `self._player.play(...)`, и playlist reload.
- [x] Воспроизвести отдельно три сценария: channel switch, natural next video inside
  channel, playlist refresh for same channel.
- [x] Зафиксировать правило показа: channel switch suppresses the next interstitial;
  in-channel video change never draws transition placeholder.
- [x] Проверить raw `/dev/fb0` под более длинной нагрузкой с реальным remote
  channel switching и отдельным direct framebuffer write stress.
- [ ] Подготовить замену raw `/dev/fb0`, если дальнейшие тесты подтвердят, что
  `omxplayer` abort/freeze связан именно с framebuffer writes:
  omxplayer/videolooper-native overlay, pygame-only OSD, or pre-roll MP4
  placeholder instead of direct framebuffer writes.

## Current Implementation
- FIFO playlist commands now log command details, current playlist state, mtime,
  player stop, playlist reload, placeholder draw path, and `player.play(...)`.
- A command for a different playlist is treated as channel switch: it draws only
  `transition-placeholder.fb` and suppresses the next interstitial.
- A command for the same playlist with a changed mtime is treated as
  same-channel playlist refresh: it does not draw the transition placeholder and
  leaves the normal in-channel interstitial path responsible for the next video.
- Source tests cover the draw-path invariants. Hardware evidence and dmesg
  stress results now show repeated `omxplayer.bin Aborted` events under raw
  framebuffer pressure, but no reproduced kernel panic yet.
- `rick-tv-pi/provisioning/scripts/collect-framebuffer-diagnostics.sh` collects
  the planned Pi evidence over SSH into a local tarball: service journal,
  supervisor status/tails, `dmesg`, `fb0` metadata, playback process command
  lines, installed override markers, and redacted Pi env.
- `RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true` is a diagnostic A/B flag. The
  videolooper override reads it from process env or `/etc/rick-tv-pi.env` and
  skips both regular raw `/dev/fb0` placeholder writes while keeping FIFO
  switching and playback unchanged. At startup it clears the existing
  framebuffer to black once, because an old `.fb` image can otherwise remain
  underneath the omxplayer video plane and show through during stop/start.

## Lab Pi Observation
- 2026-06-18 03:16 Europe/Kyiv: after deploying the diagnostic override to
  `192.168.1.68`, `video_looper` restarted and reported `RUNNING`. The installed
  egg contained the new diagnostic strings and the guarded `quit()` path.
- The supervisor log was cleared and `video_looper` was restarted again to
  verify that the old `pygame.error: video system not initialized` traceback no
  longer reproduced. During that verification SSH connectivity to
  `192.168.1.68` was lost; six ping attempts over about one minute returned no
  replies and ARP stayed `INCOMPLETE`.
- This does not prove a kernel panic by itself. Next hardware step is physical
  inspection or power-cycle, then collect `uptime`, `journalctl`, supervisor
  logs, and `dmesg` before running more placeholder stress tests. Use
  `collect-framebuffer-diagnostics.sh` for that collection.
- 2026-06-18 10:40 Europe/Kyiv: after user reboot, diagnostics from
  `192.168.1.68` were collected into
  `/tmp/rick-tv-framebuffer-diagnostics-20260618-104000`.
- Boot evidence: previous boot ended at `2026-06-18 00:15:06 UTC`; current boot
  started at `2026-06-18 07:28:50 UTC`. Current boot logs show ext4 recovery and
  corrupted/uncleanly closed system/user journals. No saved panic stack, oops, or
  pstore crash file was found, so the panic cause is still not proven.
- Hardware state during diagnostics: `fb0` is `640x480`, stride `2560`,
  `bits_per_pixel=32`, and both `.fb` assets are `1228800` bytes, matching one
  full `640 * 480 * 4` frame. `vcgencmd get_throttled` returned `0x0`, and
  temperature was about `56.2'C`.
- Kernel boot warnings include GPIO conflicts where `soc:fb` owns GPIO pins that
  `spi`/`i2c` also try to claim, plus an `i2s`/`pwm` conflict on GPIO19. Goodix
  touch eventually binds at `11-005d`. These are configuration smells to review
  for the packaged image, but there is no evidence yet that they caused the
  runtime panic.
- Log evidence confirms the placeholder routing rule:
  channel switches at `07:34:25`, `07:34:48`, `07:37:56`, and six additional
  remote switch commands at `07:45:48` through `07:45:59` each wrote exactly one
  transition placeholder and then logged `Rick TV skipping interstitial after
  channel switch`.
- Natural in-channel playback repeatedly logged only
  `Rick TV showing interstitial ad` before the next `player.play(...)`.
- A same-channel playlist refresh on `04_Pipa_Panch` at `07:41:31` logged
  `same_playlist=True`, `Rick TV same-channel playlist refresh; transition
  placeholder suppressed`, then showed the normal interstitial before playback.
- A limited raw framebuffer stress test alternated `transition-placeholder.fb`
  and `interstitial-ad.fb` directly into `/dev/fb0` 20 times. It completed
  without new kernel errors, and `rick-tv-pi.service`/`video_looper` stayed
  active. This does not fully clear raw framebuffer writes under all
  omxplayer/timing conditions, but it makes a simple bad-size framebuffer write
  less likely.
- A remote-command stress test queued six `select_channel` commands through the
  SQLite-backed command store. All six were completed by the Pi between
  `2026-06-18 07:45:48 UTC` and `07:45:58 UTC`; `video_looper` remained
  `RUNNING`, `rick-tv-pi.service` remained `active`, and `dmesg` had no new
  panic/oops/framebuffer/GPU errors.
- `omxplayer` stderr still shows occasional `Aborted` lines when commands stop a
  running player. The loop recovers and continues playback, but this remains a
  candidate timing edge to instrument if freezes return.
- 2026-06-18 10:52 Europe/Kyiv: deployed the A/B override to `192.168.1.68`,
  set `RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true` in `/etc/rick-tv-pi.env`,
  and restarted supervisor `video_looper`.
- A second remote-command stress test queued six `select_channel` commands after
  disabling raw placeholders. All six completed between
  `2026-06-18 07:52:26 UTC` and `07:52:37 UTC`; `video_looper` remained
  `RUNNING`, `rick-tv-pi.service` remained `active`, and `dmesg` had no new
  panic/oops/framebuffer/GPU errors.
- In A/B mode, each channel switch logged
  `Rick TV transition placeholder disabled by RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS`
  before playlist reload, and natural in-channel playback logged
  `Rick TV interstitial ad disabled by RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS`.
  That confirms the test removed the raw draw path while preserving playback and
  command ack behavior.
- 2026-06-18 10:56 Europe/Kyiv: user still saw placeholders in A/B mode. Direct
  evidence showed `/dev/fb0` hash matched `interstitial-ad.fb` exactly even
  though no new placeholder writes were logged after the A/B restart. Clearing
  `/dev/fb0` to black changed the hash and kept `rick-tv-pi.service` active and
  `video_looper` running. Root cause for this symptom: stale framebuffer content
  from before A/B mode, not continued placeholder drawing.
- 2026-06-18 11:03-11:35 Europe/Kyiv: re-enabled raw framebuffer placeholders
  on `192.168.1.68` with `RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=false`,
  restarted supervisor `video_looper`, and captured logs in
  `/home/pi/rick-tv/diagnostics/framebuffer-20260618T080305Z`.
- A 30-minute server/API remote-switch stress queued 430 `select_channel`
  commands and all 430 were acknowledged by the Pi. `video_looper` stayed on the
  same supervisor process, `vcgencmd get_throttled` stayed `0x0`, temperature
  stayed roughly `51-54'C`, and `dmesg` showed no new panic/oops/framebuffer/GPU
  errors.
- During that raw-enabled remote-switch run, `omxplayer` stderr logged one
  user-space abort at `2026-06-18 08:29:46 UTC`. Playback recovered and remote
  command acknowledgements continued, so this is evidence of an `omxplayer`
  timing/stop-start problem, not a reproduced kernel panic.
- 2026-06-18 11:38-11:46 Europe/Kyiv: ran a direct raw framebuffer stress that
  alternated `transition-placeholder.fb` and `interstitial-ad.fb` into
  `/dev/fb0` 500 times while playback continued. The test completed, Pi stayed
  reachable, `get_throttled` stayed `0x0`, final temperature was about
  `56.2'C`, and `dmesg` still had no new panic/oops/framebuffer/GPU errors.
- During the direct raw framebuffer stress, `omxplayer` stderr logged another
  `Aborted` event at `2026-06-18 08:43:33 UTC`. This makes raw framebuffer
  writes plus active omxplayer playback a credible source of user-space player
  instability. It still does not prove the earlier appliance-level kernel panic
  without a preserved panic stack or a reproduced full Pi freeze.

## Current Hypothesis
- The current code-level routing now appears correct: different-channel switch
  draws only the transition placeholder, same-channel refresh suppresses it, and
  in-channel video changes use only the interstitial.
- The earlier kernel panic was real at the appliance level, but its root cause is
  still unproven because the reboot did not preserve a panic stack. The strongest
  remaining suspect is timing/contention between active `omxplayer` playback,
  stop/start, and raw fb writes. Lower-level display/GPIO configuration
  instability on the legacy image remains a secondary suspect.
- Longer raw-enabled tests did not reproduce kernel panic, but they did reproduce
  `omxplayer.bin Aborted` under both remote switch pressure and direct
  framebuffer pressure. Treat the current failure as proven user-space player
  instability and unproven kernel panic until a full freeze captures crash
  evidence.
- The A/B run with raw placeholder writes disabled did not reproduce the panic
  during its shorter stress window. This is useful but not conclusive: a longer
  A/B soak is still needed before deciding whether repeated raw framebuffer
  writes are the root cause or merely adjacent to the failure. The one-time black
  clear is intentionally separate from regular placeholder drawing.
- If the disabled-placeholder A/B build survives a longer soak while raw-enabled
  runs continue to produce `omxplayer` abort/freeze symptoms, raw framebuffer
  access becomes the leading suspect and the replacement should be an
  omxplayer-managed or pre-rendered MP4 transition path.

## Test Plan
- [x] Unit/source tests assert exactly one transition draw path for FIFO channel
  commands and exactly one interstitial draw path before in-channel playback.
- [x] Manual Pi test records logs for channel switch and
  in-channel transition.
- [x] `dmesg` after remote channel-switch stress has no new framebuffer, GPU, or
  kernel panic errors.
- [x] Short A/B remote-switch stress runs with raw `/dev/fb0` placeholders
  disabled and confirms playback/ack still work.
- [x] Raw-enabled remote-switch stress completed 430 server/API
  `select_channel` commands without kernel panic, while recording one
  `omxplayer.bin Aborted`.
- [x] Direct raw `/dev/fb0` stress completed 500 alternating placeholder writes
  without kernel panic, while recording one `omxplayer.bin Aborted`.
- [ ] Capture video/photo evidence of actual screen behavior during channel
  switch and in-channel transition, because logs prove code path selection but
  not visual flicker timing.
- [ ] Run a longer A/B soak with raw `/dev/fb0` placeholders disabled before
  deciding whether to delete or replace the `.fb` path.

## Assumptions
- This task is investigation-first; do not remove the existing `.fb` assets until
  the replacement path is proven on real hardware.
- Legacy `videolooper` remains the playback runtime unless this investigation
  proves it is the root cause.
