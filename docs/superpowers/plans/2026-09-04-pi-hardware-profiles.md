# Pi Hardware Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit USB-DAC/PWM audio profiles and restore the original GPIO26 power-switch behavior for both Rick TV hardware builds.

**Architecture:** `RICK_TV_AUDIO_PROFILE` selects the Video Looper audio configuration and the GPIO19 behavior of a dedicated power-button service. Provisioning propagates the selected profile from the private boot/deploy environment, while the existing display overlay remains the authoritative GPIO mapping.

**Tech Stack:** Python 3.7-compatible Python, pytest, Bash provisioning scripts, systemd, RPi.GPIO, Raspberry Pi Video Looper.

**Spec:** `docs/superpowers/specs/2026-09-04-pi-hardware-profiles-design.md`

## Global Constraints

- Raspberry Pi Zero W and Raspberry Pi OS Buster/Python 3.7 remain supported.
- `usb-dac` remains the default for upgrades without an explicit profile.
- The older television explicitly uses `RICK_TV_AUDIO_PROFILE=pwm`.
- GPIO18, GPIO19, and GPIO26 behavior must match the approved design.
- Telegram bot credentials stay server-side and never enter the Pi image.
- No SD card is written until code and configuration tests pass and the target disk is re-identified.

---

### Task 1: Audio Profile Configuration

**Files:**
- Modify: `rick-tv-pi/tests/test_provisioning_scripts.py`
- Modify: `rick-tv-pi/provisioning/videolooper/configure_rick_tv_videolooper.py`

**Interfaces:**
- Consumes: environment variable `RICK_TV_AUDIO_PROFILE`.
- Produces: `configure_audio(config, profile)` and a generated `video_looper.ini` configured for `usb-dac` or `pwm`.

- [ ] **Step 1: Write failing behavior tests**

Add tests that execute the real configurer against a temporary INI and assert
literal output values: default and explicit `usb-dac` produce `sound = alsa`,
`hw_device = 1,0`, `hw_vol = 100%`, `hw_vol_control = PCM`; `pwm` produces
`sound = both` and a blank `hw_device`; an unknown profile exits non-zero with
an explanatory error.

- [ ] **Step 2: Run the focused tests and observe the expected failures**

Run:

```bash
.venv/bin/python -m pytest rick-tv-pi/tests/test_provisioning_scripts.py -k 'audio_profile or routes_omxplayer' -v
```

Expected: PWM and invalid-profile tests fail because profile selection does not exist.

- [ ] **Step 3: Implement profile selection**

Normalize `RICK_TV_AUDIO_PROFILE`, default it to `usb-dac`, configure the
literal INI values above, and reject values outside `{usb-dac, pwm}`.

- [ ] **Step 4: Re-run focused tests**

Run the Step 2 command. Expected: all selected tests pass.

### Task 2: GPIO Power Button Runtime

**Files:**
- Create: `rick-tv-pi/src/rick_tv_pi/power_button.py`
- Create: `rick-tv-pi/tests/test_power_button.py`

**Interfaces:**
- Consumes: `RICK_TV_AUDIO_PROFILE`, RPi.GPIO, `raspi-gpio`, and `tvservice`.
- Produces: `PowerButtonController`, `run_power_button_loop()`, and module CLI `python -m rick_tv_pi.power_button`.

- [ ] **Step 1: Write failing controller tests**

Use an in-memory fake GPIO adapter and a recording command runner. Assert that
active-low GPIO26 applies on/off state, GPIO18 and `tvservice` commands match
the design, PWM toggles GPIO19, USB DAC never touches GPIO19, and unchanged
input does not repeat commands.

- [ ] **Step 2: Run the new tests and observe import failure**

Run:

```bash
.venv/bin/python -m pytest rick-tv-pi/tests/test_power_button.py -v
```

Expected: collection fails because `rick_tv_pi.power_button` does not exist.

- [ ] **Step 3: Implement the minimal Python 3.7-compatible controller**

Lazy-load RPi.GPIO in `main()`, inject GPIO/runner/sleep for tests, configure
BCM GPIO26 with pull-up, apply the initial state once, and process transitions
at a 0.3-second polling interval.

- [ ] **Step 4: Re-run the new tests**

Run the Step 2 command. Expected: all tests pass.

### Task 3: Provisioning and Environment Propagation

**Files:**
- Create: `rick-tv-pi/systemd/rick-tv-power-button.service`
- Modify: `rick-tv-pi/provisioning/rick-tv.env.example`
- Modify: `rick-tv-pi/provisioning/firstboot/rick-tv-firstboot.sh`
- Modify: `rick-tv-pi/provisioning/image/install_packaged_image_payload.sh`
- Modify: `rick-tv-pi/provisioning/deploy_videolooper_image.sh`
- Modify: `rick-tv-pi/tests/test_provisioning_scripts.py`

**Interfaces:**
- Consumes: private boot/deploy `rick-tv.env`.
- Produces: persisted `RICK_TV_AUDIO_PROFILE`, staged and enabled power-button service, and profile-aware Video Looper provisioning.

- [ ] **Step 1: Add failing provisioning tests**

Exercise firstboot and packaged-image installers against temporary roots. Assert
that the profile is copied into the runtime env, an explicit deploy config is
used for Video Looper audio even when a runtime env already exists, and the
power-button unit is staged/enabled without grepping implementation-only text.

- [ ] **Step 2: Run the focused provisioning tests and observe failures**

Run:

```bash
.venv/bin/python -m pytest rick-tv-pi/tests/test_provisioning_scripts.py -k 'audio_profile or power_button' -v
```

Expected: failures identify missing env propagation and service installation.

- [ ] **Step 3: Implement provisioning changes**

Add the profile to runtime env allowlists; source an explicit boot/deploy config
for the configurer; stage, enable, and restart `rick-tv-power-button.service` in
the same paths that manage `rick-tv-pi.service`; keep secrets excluded from
packaged source archives.

- [ ] **Step 4: Re-run focused provisioning tests**

Run the Step 2 command. Expected: all selected tests pass.

### Task 4: Documentation and Repository Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/rick-tv-pi.md`

**Interfaces:**
- Consumes: the implemented environment and service contracts.
- Produces: operator instructions for both televisions and the old-TV install flow.

- [ ] **Step 1: Document both profiles and GPIO behavior**

Document `usb-dac` as the compatibility default, `pwm` as the required old-TV
setting, fixed GPIO18/19/26 behavior, and the fact that bot credentials are
server-only.

- [ ] **Step 2: Run all platform-independent tests**

Run:

```bash
.venv/bin/python -m pytest \
  --ignore=rick-tv-pi/tests/test_provisioning_scripts.py
.venv/bin/python -m pytest rick-tv-pi/tests/test_provisioning_scripts.py -k 'audio_profile or power_button or routes_omxplayer' -v
```

Expected: all selected tests pass. Record separately the eight known macOS-only
Bash/BSD-sed baseline failures if the unfiltered suite is run on macOS.

- [ ] **Step 3: Inspect the final diff and Python 3.7 syntax constraints**

Run `git diff --check`, inspect `git diff --stat`, and ensure new Python avoids
syntax unavailable in Python 3.7.

### Task 5: Prepare, Flash, and Boot the Old Television

**Files:**
- Local private file only: ignored `dist/rick-tv-old.env`
- Source image: `~/Downloads/Telegram Desktop/rick-tv-pi.img`

**Interfaces:**
- Consumes: existing Wi-Fi/server secrets discovered locally or supplied by the user, the verified image, and the explicitly identified SD-card device.
- Produces: a bootable old-TV SD card and live hardware verification evidence.

- [ ] **Step 1: Prepare the private old-TV config**

Set Wi-Fi, SSH, server URL, API token, runtime paths, and
`RICK_TV_AUDIO_PROFILE=pwm`. Do not add Telegram bot token or allowed-user IDs.

- [ ] **Step 2: Re-identify and flash the exact SD-card disk**

Unmount only the confirmed removable card, write the verified image, sync,
mount its FAT boot partition, and copy the private config as `rick-tv.env`.

- [ ] **Step 3: Boot and discover the Pi**

Insert the card into the old Pi, boot it, discover its DHCP address/hostname,
and connect over SSH.

- [ ] **Step 4: Deploy the profile branch and verify hardware**

Deploy with `--config dist/rick-tv-old.env`; verify both systemd services,
Video Looper, `sound = both`, GPIO26 transitions, GPIO18 state, PWM audio on
GPIO19, display output, server polling, and Telegram channel switching.

