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

The preferred install path is a Rick TV-prepared image made from the known-good
`videolooper.de` base image. If you have the base image file locally, build a
flashable Rick TV image from the repository root:

```sh
sudo rick-tv-pi/provisioning/image/build_packaged_image.sh \
  --base-image /path/to/known-good-videolooper.img \
  --output-image /path/to/rick-tv.img
```

The builder copies the base image, mounts its root/boot partitions through a
loop device, stages the Rick TV payload, and writes `rick-tv.img.sha256`.
Optionally pass `--boot-config /path/to/rick-tv.env` to put a filled first-boot
config onto the generated image. Do not commit filled config files.

If the partitions are already mounted, stage the payload directly:

```sh
rick-tv-pi/provisioning/image/install_packaged_image_payload.sh \
  --rootfs /mnt/rick-tv-root \
  --bootfs /mnt/rick-tv-boot
```

The installer copies the project to `/opt/rick-tv-src`, installs
`/usr/local/sbin/rick-tv-firstboot`, enables `rick-tv-firstboot.service`, and
places `rick-tv.env.example` on the boot partition.

Before the first boot, copy `rick-tv.env.example` to `rick-tv.env` on the boot
partition and fill in Wi-Fi, API, SSH, hostname, and Rick TV runtime values.
The first-boot service creates `/etc/rick-tv-pi.env`, configures Wi-Fi/SSH,
installs the pinned videolooper overrides/assets, enables `rick-tv-pi.service`,
and writes `/var/lib/rick-tv-pi/firstboot.done`. Later boots skip the setup and
do not overwrite user-edited `/etc/rick-tv-pi.env`.

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
- writes the systemd unit;
- configures `/boot/video_looper.ini`;
- installs pinned Rick TV overrides into the Video Looper Python egg;
- installs `/home/pi/rick-tv/system/transition-placeholder.fb`;
- installs `/home/pi/rick-tv/system/interstitial-ad.fb`;
- installs kernel panic reboot and watchdog recovery config;
- restarts `rick-tv-pi.service` and supervisor `video_looper`.

If `/etc/rick-tv-pi.env` does not exist, the script installs
`rick-tv-pi.env.example`. Edit the real file on the Pi with server URL and token.

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

Copy the overlay files to the boot partition `overlays/` directory if the image
does not already contain them.

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
