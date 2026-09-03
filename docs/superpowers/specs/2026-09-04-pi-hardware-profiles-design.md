# Pi Hardware Profiles Design

Date: 2026-09-04
Status: Approved in conversation

## Goal

Run the current Rick TV Pi software on both television builds without changing
their wiring:

- the newer build uses a USB DAC;
- the older build uses PWM audio on GPIO19;
- both builds use the existing active-low power switch on GPIO26 and the
  GPIO18 display/amplifier control scheme.

## Configuration

`RICK_TV_AUDIO_PROFILE` is the single hardware-selection setting exposed in
`rick-tv.env`:

- `usb-dac` preserves the current deployed behavior: omxplayer uses ALSA device
  `1,0`, hardware volume `100%`, and the `PCM` mixer control;
- `pwm` restores the proven old-TV behavior: omxplayer uses `sound = both`, no
  explicit ALSA hardware device, and boot config keeps PWM audio on GPIO19.

The default is `usb-dac` so upgrading the newer TV without a newly generated
environment file does not silently reroute its audio. The older TV must set
`RICK_TV_AUDIO_PROFILE=pwm` explicitly.

The value is copied from the boot environment into `/etc/rick-tv-pi.env` and
is also honored by SSH deployment with an explicit `--config` file. Unknown
profile values fail provisioning rather than guessing.

Telegram bot credentials remain server-side. Pi configuration contains Wi-Fi,
the Rick TV server URL, the shared API token, and the hardware profile.

## Power Button

A dedicated `rick-tv-power-button.service` runs a small Python module from the
Rick TV Pi virtual environment.

- GPIO numbering uses BCM mode.
- GPIO26 is an input with pull-up; low means the television is on.
- GPIO18 is input while on and output-low while off, matching the original
  display/amplifier wiring.
- `tvservice --sdtvon="NTSC [P]"` turns video on and `tvservice -o` turns it
  off, matching the original appliance.
- Under the `pwm` profile, GPIO19 is restored to PWM ALT5 while on and changed
  to input while off. Under `usb-dac`, the button service never changes GPIO19.
- The loop applies the physical switch state immediately and then polls every
  0.3 seconds, changing outputs only on transitions.

The service is staged and enabled by packaged-image provisioning, first boot,
and SSH deployment.

## Old-TV Installation Flow

1. Flash the verified `rick-tv-pi.img` already stored on the Mac.
2. Put a private `rick-tv.env` on the FAT boot partition with Wi-Fi, SSH,
   server URL, shared API token, and `RICK_TV_AUDIO_PROFILE=pwm`.
3. Boot the old Raspberry Pi Zero W.
4. Connect over SSH and deploy this branch with the same private config.
5. Verify display, GPIO26 power switch, GPIO18 control, PWM sound, Rick TV
   services, media polling, and Telegram remote channel selection.

