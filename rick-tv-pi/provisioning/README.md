# Rick TV Pi Provisioning

This provisioning set targets Raspberry Pi Zero W running the prebuilt Video
Looper SD-card image from <https://videolooper.de/>. Rick TV installs pinned
playlist/FIFO overrides into that existing Video Looper runtime.

Current lab device:

- `ssh pi@192.168.1.68`
- password: `video`

Do not run `apt upgrade` on the target Pi as part of Rick TV deployment.

## Flash a Fresh Videolooper Base

If you do not already have a known-good videolooper image, make one first:

1. Download the Video Looper image zip from <https://videolooper.de/>. Choose a
   release that supports Raspberry Pi Zero W.

2. Open Raspberry Pi Imager, choose `Use custom`, select the downloaded
   Video Looper image zip, choose the SD card, and write it. Keep the Linux user
   as `pi`; the current provisioning paths assume `/home/pi`.

3. Boot the Pi. The current lab image uses:

```text
user: pi
password: video
```

4. SSH into the Pi and verify that the Video Looper runtime is present:

```sh
ssh pi@<pi-ip>
sudo supervisorctl status video_looper
ls /usr/local/lib/python3.7/dist-packages/Adafruit_Video_Looper-*.egg
```

The Rick TV deploy script currently expects the legacy Python 3.7 Video Looper
layout used by the `videolooper.de` image. Do not run `apt upgrade` on the Pi as
part of Rick TV setup.

## Packaged Image Payload

The preferred install path is a Rick TV-prepared image made from the
`videolooper.de` v2.11 base archive with `gitbls/sdm`. Install `sdm` on the
build machine:

```sh
curl -L https://raw.githubusercontent.com/gitbls/sdm/master/install-sdm | bash
```

Then build a flashable Rick TV image from the repository root:

```sh
sudo rick-tv-pi/provisioning/image/build_packaged_image.sh \
  --base-image-url https://videolooper.de/video_looper_v2.11.zip \
  --output-image dist/rick-tv-pi.img
```

The builder downloads/extracts the Video Looper image outside tracked repo
paths, copies it to the requested output image, runs `sdm --customize` with Rick
TV's custom phase script, stages the Rick TV payload, and writes
`dist/rick-tv-pi.img.sha256`. During staging it also copies the Waveshare
2.8inch DPI LCD DTBO files to the boot partition, appends Rick TV's legacy DPI
display block to `config.txt`, writes Rick TV's `/boot/video_looper.ini`,
patches the Video Looper egg, installs placeholder assets, creates the empty
playlist tree, installs panic/watchdog recovery config, installs
`rick-tv-pi.service`, and builds `/opt/rick-tv-pi/.venv`. The venv installs
`evdev==1.7.1` and `certifi==2026.4.22` as pip-level runtime overrides because
the legacy `videolooper.de` Buster image otherwise exposes older system
packages through `--system-site-packages`. Optionally pass
`--boot-config /path/to/rick-tv.env` to put a filled first-boot config onto a
private generated image. Do not commit filled config files.

Before the first boot, copy `rick-tv.env.example` to `rick-tv.env` on the boot
partition and fill in Wi-Fi, API, SSH, hostname, and Rick TV runtime values.
The first-boot service creates `/etc/rick-tv-pi.env`, configures Wi-Fi/SSH,
re-applies the same idempotent runtime checks, starts `rick-tv-pi.service`,
restarts `video_looper`, and writes `/var/lib/rick-tv-pi/firstboot.done`. Later
boots skip the setup and do not overwrite user-edited `/etc/rick-tv-pi.env`.
Telegram bot token and allowed user IDs are server-side settings; do not put
them in the Pi image or `rick-tv.env`.

## Deploy to a Running Pi

From the repository root:

```sh
rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy
```

Useful overrides:

```sh
PI_HOST=pi@192.168.1.68 PI_PASSWORD=video \
  rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy
```

The deploy script:

- installs required packages only;
- copies the project to `/opt/rick-tv-src`;
- installs `rick-tv-pi` into `/opt/rick-tv-pi/.venv`;
- installs pinned venv runtime overrides matching the working Pi:
  `evdev==1.7.1` and `certifi==2026.4.22`;
- writes the systemd unit;
- configures `/boot/video_looper.ini`;
- installs pinned Rick TV overrides into the Video Looper Python egg;
- installs `/home/pi/rick-tv/system/transition-placeholder.fb`;
- installs `/home/pi/rick-tv/system/interstitial-ad.fb`;
- installs kernel panic reboot and watchdog recovery config;
- restarts `rick-tv-pi.service` and supervisor `video_looper`.

If `/etc/rick-tv-pi.env` does not exist, the script generates it from the
`RICK_TV_*` values in `rick-tv-pi/provisioning/rick-tv.env.example`. For real
values, create a private filled config and pass it to deploy:

```sh
mkdir -p dist
cp rick-tv-pi/provisioning/rick-tv.env.example dist/rick-tv.env
nano dist/rick-tv.env
PI_HOST=pi@192.168.1.68 PI_PASSWORD=video \
  rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy --config dist/rick-tv.env
```

Existing `/etc/rick-tv-pi.env` files are preserved. Wi-Fi/SSH fields from the
full config are firstboot-only; deploy writes only the runtime `RICK_TV_*`
subset.

## Wi-Fi Bootstrap

For an SD card whose image has Wi-Fi disabled, mount the FAT boot partition on
your workstation and run:

```sh
rick-tv-pi/provisioning/deploy_videolooper_image.sh wifi \
  --boot /Volumes/boot \
  --ssid "YOUR_WIFI_SSID" \
  --psk "YOUR_WIFI_PASSWORD"
```

This writes `wpa_supplicant.conf` and an `ssh` marker file to the boot
partition. The committed `wifi/wpa_supplicant.conf.example` keeps placeholders
only.

## Display

For the Waveshare 2.8inch DPI LCD on the legacy image, use:

- `display/config.txt.waveshare-28dpi-legacy`
- `vendor/waveshare-28dpi/overlays/*.dtbo`

The packaged-image builder applies these automatically. Manual copying is only
for lab repair of an already-written boot partition.

## Framebuffer Diagnostics

When investigating placeholder flicker, wrong placeholder ordering, or suspected
GPU/kernel instability, collect a diagnostics bundle from the workstation:

```sh
rick-tv-pi/provisioning/scripts/collect-framebuffer-diagnostics.sh \
  --host pi@192.168.1.68 \
  --identity-file ~/.ssh/rick_tv_pi_ed25519 \
  --since "2026-06-18 00:00:00"
```

The bundle includes `rick-tv-pi.service` journal output, `video_looper`
supervisor status/tails, `dmesg`, `/sys/class/graphics/fb0/*`, playback process
command lines, installed override markers, and a redacted `/etc/rick-tv-pi.env`.
Supervisor tails are wrapped with `timeout` so empty logs do not hang collection.
For A/B testing, set `RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true` in
`/etc/rick-tv-pi.env` to keep videolooper playback/switching active while
skipping both regular raw `/dev/fb0` placeholder writes. On startup, the
override clears any stale framebuffer image to black once so an old placeholder
does not show through when omxplayer stops between videos.

## Panic And Watchdog Recovery

Provisioning runs `scripts/configure-pi-recovery.sh` on both a running deploy and
first boot of a packaged image. It installs:

- `/etc/sysctl.d/99-rick-tv-panic.conf` with `kernel.panic=10` and `kernel.panic_on_oops=1`;
- `panic=10` in the boot partition `cmdline.txt`;
- `dtparam=watchdog=on` in the boot partition `config.txt`;
- `/etc/systemd/system.conf.d/10-rick-tv-watchdog.conf` with `RuntimeWatchdogSec=15s` and `ShutdownWatchdogSec=2min`.

The script is idempotent and does not run `apt upgrade`. Reboot once after
deploying to activate boot-level panic/watchdog settings. This is recovery
hardening only; placeholder rendering and `videolooper` playback behavior stay
unchanged.
