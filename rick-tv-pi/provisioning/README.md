# Rick TV Pi Provisioning

This provisioning set targets the prepared Raspberry Pi OS Legacy/Buster image
that already contains Adafruit `pi_video_looper`, `supervisor`, and `omxplayer`.

Current lab device:

- `ssh pi@192.168.1.68`
- password: `video`

Do not run `apt upgrade` on the target Pi as part of Rick TV deployment.

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
- installs pinned Rick TV `pi_video_looper` overrides into the Adafruit Video Looper egg;
- installs `/home/pi/rick-tv/system/transition-placeholder.fb`;
- installs `/home/pi/rick-tv/system/interstitial-ad.fb`;
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
