from pathlib import Path
import subprocess
import sys
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIRSTBOOT_SCRIPT = PROJECT_ROOT / "provisioning" / "firstboot" / "rick-tv-firstboot.sh"
FIRSTBOOT_SERVICE = PROJECT_ROOT / "provisioning" / "firstboot" / "rick-tv-firstboot.service"
FIRSTBOOT_EXAMPLE = PROJECT_ROOT / "provisioning" / "rick-tv.env.example"
REMOVED_RUNTIME_EXAMPLE = PROJECT_ROOT / "provisioning" / "rick-tv-pi.env.example"
IMAGE_INSTALLER = (
    PROJECT_ROOT / "provisioning" / "image" / "install_packaged_image_payload.sh"
)
IMAGE_BUILDER = PROJECT_ROOT / "provisioning" / "image" / "build_packaged_image.sh"
SDM_PHASE_SCRIPT = PROJECT_ROOT / "provisioning" / "image" / "sdm_rick_tv_custom_phase.sh"
FRAMEBUFFER_DIAGNOSTICS = (
    PROJECT_ROOT / "provisioning" / "scripts" / "collect-framebuffer-diagnostics.sh"
)
RECOVERY_SCRIPT = PROJECT_ROOT / "provisioning" / "scripts" / "configure-pi-recovery.sh"
PLAYLIST_GENERATOR = (
    PROJECT_ROOT / "provisioning" / "videolooper" / "generate_channel_playlists.py"
)


def test_deploy_restarts_videolooper_before_pi_runtime() -> None:
    script = PROJECT_ROOT / "provisioning" / "deploy_videolooper_image.sh"

    content = script.read_text(encoding="utf-8")

    assert content.index("supervisorctl restart video_looper") < content.index(
        "systemctl restart rick-tv-pi.service"
    )


def test_deploy_payload_excludes_local_secrets_and_runtime_data() -> None:
    script = PROJECT_ROOT / "provisioning" / "deploy_videolooper_image.sh"
    content = script.read_text(encoding="utf-8")

    for excluded in [
        ".env",
        "**/.env",
        "**/*.sqlite3",
        "dist",
        "*.img",
        "*.zip",
        "rick-tv-server/.env",
        "rick-tv-server/data",
        "rick-tv-server/media",
        "rick-tv-server/config",
        "rick-tv-server/state",
        "manual-test-videos",
    ]:
        assert f'--exclude="{excluded}"' in content


def test_deploy_applies_pi_recovery_config() -> None:
    script = PROJECT_ROOT / "provisioning" / "deploy_videolooper_image.sh"
    content = script.read_text(encoding="utf-8")

    assert "configure-pi-recovery.sh" in content
    assert content.index("configure-pi-recovery.sh") < content.index(
        "systemctl restart rick-tv-pi.service"
    )


def test_deploy_installs_pinned_runtime_overrides_after_project() -> None:
    script = PROJECT_ROOT / "provisioning" / "deploy_videolooper_image.sh"
    content = script.read_text(encoding="utf-8")

    project_install = "/opt/rick-tv-pi/.venv/bin/pip install /opt/rick-tv-src/rick-tv-pi"
    override_install = (
        "/opt/rick-tv-pi/.venv/bin/pip install "
        "'evdev==1.7.1' 'certifi==2026.4.22'"
    )

    assert project_install in content
    assert override_install in content
    assert content.index(project_install) < content.index(override_install)


def test_deploy_uses_single_full_config_example_for_missing_runtime_env() -> None:
    script = PROJECT_ROOT / "provisioning" / "deploy_videolooper_image.sh"
    content = script.read_text(encoding="utf-8")

    assert "rick-tv-pi/provisioning/rick-tv.env.example" in content
    assert "rick-tv-pi.env.example" not in content
    assert "--config rick-tv.env" in content
    assert 'scp_pi "$full_config" "$PI_HOST:$REMOTE_TMP/rick-tv.env"' in content
    assert "runtime_config=/tmp/rick-tv-deploy/rick-tv.env" in content
    assert "write_runtime_env_from_full_config" in content
    assert "if [ ! -f /etc/rick-tv-pi.env ]; then" in content
    assert "preserving existing /etc/rick-tv-pi.env" in content

    runtime_start = content.index("runtime_names=(")
    runtime_section = content[
        runtime_start : content.index("local name value", runtime_start)
    ]
    for name in [
        "RICK_TV_SERVER_URL",
        "RICK_TV_API_TOKEN",
        "RICK_TV_METADATA_PATH",
        "RICK_TV_REMOTE_POLL_INTERVAL_SECONDS",
        "RICK_TV_RUNTIME_TICK_SECONDS",
    ]:
        assert name in runtime_section
    for secret_or_boot_only in [
        "WIFI_SSID",
        "WIFI_PSK",
        "SSH_PASSWORD",
        "SSH_AUTHORIZED_KEY",
        "RICK_TV_TELEGRAM_BOT_TOKEN",
        "RICK_TV_TELEGRAM_ALLOWED_USER_IDS",
    ]:
        assert secret_or_boot_only not in runtime_section


def test_recovery_script_writes_panic_and_watchdog_config_idempotently(tmp_path) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    (bootfs).mkdir(parents=True)
    (bootfs / "cmdline.txt").write_text(
        "console=serial0,115200 console=tty1 root=/dev/mmcblk0p2 rw rootwait\n",
        encoding="utf-8",
    )
    (bootfs / "config.txt").write_text(
        "disable_overscan=1\n",
        encoding="utf-8",
    )

    for _ in range(2):
        result = subprocess.run(
            ["bash", str(RECOVERY_SCRIPT)],
            check=False,
            env={
                "PATH": "/usr/bin:/bin",
                "RICK_TV_RECOVERY_ROOT": str(rootfs),
                "RICK_TV_RECOVERY_BOOT": str(bootfs),
                "RICK_TV_RECOVERY_DRY_RUN": "1",
            },
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr

    assert (
        rootfs / "etc" / "sysctl.d" / "99-rick-tv-panic.conf"
    ).read_text(encoding="utf-8") == "kernel.panic=10\nkernel.panic_on_oops=1\n"
    assert (
        rootfs / "etc" / "systemd" / "system.conf.d" / "10-rick-tv-watchdog.conf"
    ).read_text(encoding="utf-8") == (
        "[Manager]\n"
        "RuntimeWatchdogSec=15s\n"
        "ShutdownWatchdogSec=2min\n"
    )
    assert (bootfs / "cmdline.txt").read_text(encoding="utf-8").count("panic=10") == 1
    assert (
        bootfs / "cmdline.txt"
    ).read_text(encoding="utf-8") == (
        "console=serial0,115200 console=tty1 root=/dev/mmcblk0p2 rw rootwait panic=10\n"
    )
    assert (bootfs / "config.txt").read_text(encoding="utf-8").count(
        "dtparam=watchdog=on"
    ) == 1
    assert (bootfs / "config.txt").read_text(encoding="utf-8") == (
        "disable_overscan=1\n"
        "\n"
        "# Rick TV recovery watchdog\n"
        "dtparam=watchdog=on\n"
    )


def test_playlist_generator_accepts_offline_root_overrides(tmp_path) -> None:
    media_root = tmp_path / "rootfs" / "home" / "pi" / "rick-tv" / "media"
    playlist_root = tmp_path / "rootfs" / "home" / "pi" / "rick-tv" / "playlists"
    channel_root = media_root / "01_Citadel"
    channel_root.mkdir(parents=True)
    video_path = channel_root / "episode-01.mp4"
    video_path.write_bytes(b"fake mp4")

    result = subprocess.run(
        [sys.executable, str(PLAYLIST_GENERATOR)],
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "RICK_TV_MEDIA_ROOT": str(media_root),
            "RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT": str(playlist_root),
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    master = (playlist_root / "channels.m3u").read_text(encoding="utf-8")
    channel_playlist = (
        playlist_root / "channels" / "01_Citadel.m3u"
    ).read_text(encoding="utf-8")
    assert str(playlist_root / "channels" / "01_Citadel.m3u") in master
    assert str(video_path) in channel_playlist
    paths = [
        line
        for line in (master + channel_playlist).splitlines()
        if line and not line.startswith("#")
    ]
    assert paths
    assert all(line.startswith(str(tmp_path)) for line in paths)


def test_firstboot_script_applies_boot_config_without_real_system_commands(tmp_path) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    bootfs.mkdir()
    (rootfs / "opt" / "rick-tv-src").mkdir(parents=True)
    (rootfs / "opt" / "rick-tv-src" / "rick-tv-pi" / "provisioning" / "scripts").mkdir(
        parents=True
    )
    (rootfs / "opt" / "rick-tv-src" / "rick-tv-pi" / "provisioning" / "scripts" / "configure-pi-recovery.sh").write_text(
        RECOVERY_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (bootfs / "cmdline.txt").write_text(
        "console=serial0,115200 console=tty1 root=/dev/mmcblk0p2 rw rootwait\n",
        encoding="utf-8",
    )
    (bootfs / "config.txt").write_text("disable_overscan=1\n", encoding="utf-8")
    (bootfs / "rick-tv.env").write_text(
        "\n".join(
            [
                "WIFI_COUNTRY=UA",
                "WIFI_SSID='Test Network'",
                "WIFI_PSK='test-password'",
                "RICK_TV_HOSTNAME=rick-tv-test",
                "SSH_ENABLE=true",
                "SSH_PASSWORD='ssh-password'",
                "SSH_AUTHORIZED_KEY='ssh-ed25519 AAAATEST rick-tv'",
                "RICK_TV_SERVER_URL=http://192.168.1.10:8080",
                "RICK_TV_API_TOKEN=test-token",
                "RICK_TV_MEDIA_ROOT=/home/pi/rick-tv/media",
                "RICK_TV_METADATA_PATH=/home/pi/rick-tv/config/channels.json",
                "RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT=/home/pi/rick-tv/playlists",
                "RICK_TV_VIDEOLOOPER_COMMAND_PATH=/tmp/rick-tv-videolooper.fifo",
                "RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true",
                "RICK_TV_TELEGRAM_BOT_TOKEN=server-only-token",
                "RICK_TV_TELEGRAM_ALLOWED_USER_IDS=12345",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(FIRSTBOOT_SCRIPT)],
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "RICK_TV_FIRSTBOOT_ROOT": str(rootfs),
            "RICK_TV_FIRSTBOOT_BOOT": str(bootfs),
            "RICK_TV_FIRSTBOOT_DRY_RUN": "1",
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    runtime_env = (rootfs / "etc" / "rick-tv-pi.env").read_text(encoding="utf-8")
    assert runtime_env == (
        "RICK_TV_SERVER_URL=http://192.168.1.10:8080\n"
        "RICK_TV_API_TOKEN=test-token\n"
        "RICK_TV_MEDIA_ROOT=/home/pi/rick-tv/media\n"
        "RICK_TV_METADATA_PATH=/home/pi/rick-tv/config/channels.json\n"
        "RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT=/home/pi/rick-tv/playlists\n"
        "RICK_TV_VIDEOLOOPER_COMMAND_PATH=/tmp/rick-tv-videolooper.fifo\n"
        "RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS=true\n"
    )
    for secret_or_boot_only in [
        "WIFI_PSK",
        "SSH_PASSWORD",
        "SSH_AUTHORIZED_KEY",
        "RICK_TV_TELEGRAM_BOT_TOKEN",
        "RICK_TV_TELEGRAM_ALLOWED_USER_IDS",
    ]:
        assert secret_or_boot_only not in runtime_env
    assert "ssid=\"Test Network\"" in (
        rootfs / "etc" / "wpa_supplicant" / "wpa_supplicant.conf"
    ).read_text(encoding="utf-8")
    assert (rootfs / "etc" / "hostname").read_text(encoding="utf-8") == "rick-tv-test\n"
    assert "ssh-ed25519 AAAATEST rick-tv" in (
        rootfs / "home" / "pi" / ".ssh" / "authorized_keys"
    ).read_text(encoding="utf-8")
    assert "kernel.panic=10" in (
        rootfs / "etc" / "sysctl.d" / "99-rick-tv-panic.conf"
    ).read_text(encoding="utf-8")
    assert "RuntimeWatchdogSec=15s" in (
        rootfs / "etc" / "systemd" / "system.conf.d" / "10-rick-tv-watchdog.conf"
    ).read_text(encoding="utf-8")
    assert (bootfs / "cmdline.txt").read_text(encoding="utf-8").count("panic=10") == 1
    assert (bootfs / "config.txt").read_text(encoding="utf-8").count(
        "dtparam=watchdog=on"
    ) == 1
    assert "systemctl --no-block restart rick-tv-pi.service" in result.stdout
    assert "systemctl restart rick-tv-pi.service" not in result.stdout
    assert "supervisorctl restart video_looper" in result.stdout
    assert (rootfs / "var" / "lib" / "rick-tv-pi" / "firstboot.done").exists()


def test_firstboot_script_is_idempotent_and_preserves_existing_runtime_env(tmp_path) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    bootfs.mkdir()
    env_file = rootfs / "etc" / "rick-tv-pi.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("RICK_TV_SERVER_URL=http://edited\n", encoding="utf-8")
    marker = rootfs / "var" / "lib" / "rick-tv-pi" / "firstboot.done"
    marker.parent.mkdir(parents=True)
    marker.write_text("already-done\n", encoding="utf-8")
    (bootfs / "rick-tv.env").write_text(
        "RICK_TV_SERVER_URL=http://new\nRICK_TV_API_TOKEN=new-token\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(FIRSTBOOT_SCRIPT)],
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "RICK_TV_FIRSTBOOT_ROOT": str(rootfs),
            "RICK_TV_FIRSTBOOT_BOOT": str(bootfs),
            "RICK_TV_FIRSTBOOT_DRY_RUN": "1",
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8") == "RICK_TV_SERVER_URL=http://edited\n"


def test_packaged_image_payload_installer_stages_firstboot_files(tmp_path) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    rootfs.mkdir()
    bootfs.mkdir()

    result = subprocess.run(
        [
            "bash",
            str(IMAGE_INSTALLER),
            "--rootfs",
            str(rootfs),
            "--bootfs",
            str(bootfs),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert (rootfs / "usr" / "local" / "sbin" / "rick-tv-firstboot").exists()
    assert (
        rootfs / "etc" / "systemd" / "system" / "rick-tv-firstboot.service"
    ).exists()
    assert (
        rootfs
        / "etc"
        / "systemd"
        / "system"
        / "multi-user.target.wants"
        / "rick-tv-firstboot.service"
    ).is_symlink()
    assert (rootfs / "opt" / "rick-tv-src" / "rick-tv-pi").exists()
    assert (bootfs / "rick-tv.env.example").read_text(encoding="utf-8") == (
        FIRSTBOOT_EXAMPLE.read_text(encoding="utf-8")
    )


def test_packaged_image_payload_installer_applies_waveshare_display_boot_config(
    tmp_path,
) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    rootfs.mkdir()
    bootfs.mkdir()
    (bootfs / "config.txt").write_text(
        "# base config\n"
        "dtoverlay=vc4-fkms-v3d\n",
        encoding="utf-8",
    )

    for _ in range(2):
        result = subprocess.run(
            [
                "bash",
                str(IMAGE_INSTALLER),
                "--rootfs",
                str(rootfs),
                "--bootfs",
                str(bootfs),
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr

    overlays = sorted(path.name for path in (bootfs / "overlays").glob("*.dtbo"))
    assert overlays == [
        "vc4-kms-dpi-2inch8.dtbo",
        "waveshare-28dpi-3b-4b.dtbo",
        "waveshare-28dpi-3b.dtbo",
        "waveshare-28dpi-4b.dtbo",
        "waveshare-touch-28dpi.dtbo",
    ]

    config = (bootfs / "config.txt").read_text(encoding="utf-8")
    assert "# dtoverlay=vc4-fkms-v3d # disabled by Rick TV Waveshare DPI config" in config
    assert config.count("# Rick TV Waveshare 2.8inch DPI LCD") == 1
    for expected in [
        "dtoverlay=dpi24",
        "enable_dpi_lcd=1",
        "display_default_lcd=1",
        "hdmi_timings=480 0 26 16 10 640 0 25 10 15 0 0 0 60 0 32000000 1",
        "dtoverlay=waveshare-28dpi-3b-4b",
        "dtoverlay=waveshare-28dpi-3b",
        "dtoverlay=waveshare-28dpi-4b",
        "display_rotate=3",
    ]:
        assert expected in config


def test_packaged_image_payload_installer_applies_videolooper_boot_config(
    tmp_path,
) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    rootfs.mkdir()
    bootfs.mkdir()
    (bootfs / "video_looper.ini").write_text(
        "[video_looper]\n"
        "file_reader = usb_drive\n"
        "osd = true\n"
        "countdown_time = 5\n"
        "console_output = false\n"
        "\n"
        "[control]\n"
        "keyboard_control = true\n"
        "\n"
        "[directory]\n"
        "path = /home/pi/video\n"
        "\n"
        "[playlist]\n"
        "path = \n"
        "\n"
        "[omxplayer]\n"
        "show_titles = false\n"
        "title_duration = 10\n"
        "extra_args = --no-osd --audio_fifo 0.01 --video_fifo 0.01 --align center --font-size 55\n",
        encoding="utf-8",
    )

    for _ in range(2):
        result = subprocess.run(
            [
                "bash",
                str(IMAGE_INSTALLER),
                "--rootfs",
                str(rootfs),
                "--bootfs",
                str(bootfs),
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr

    content = (bootfs / "video_looper.ini").read_text(encoding="utf-8")
    for expected in [
        "video_player = omxplayer",
        "file_reader = directory",
        "osd = false",
        "countdown_time = 0",
        "wait_time = 0",
        "datetime_display = false",
        "is_random = false",
        "console_output = true",
        "keyboard_control = false",
        "gpio_pin_mode = true",
        "gpio_pin_map = ",
        "path = /home/pi/rick-tv",
        "path = playlists/channels.m3u",
        "show_titles = true",
        "command_fifo = /tmp/rick-tv-videolooper.fifo",
    ]:
        assert expected in content
    assert content.count("[rick_tv]") == 1


def test_packaged_image_payload_installer_stages_full_runtime_payload(
    tmp_path,
) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    rootfs.mkdir()
    bootfs.mkdir()
    (bootfs / "cmdline.txt").write_text(
        "console=serial0,115200 console=tty1 root=/dev/mmcblk0p2 rw rootwait\n",
        encoding="utf-8",
    )
    (bootfs / "config.txt").write_text("disable_overscan=1\n", encoding="utf-8")
    egg_path = (
        rootfs
        / "usr"
        / "local"
        / "lib"
        / "python3.7"
        / "dist-packages"
        / "Adafruit_Video_Looper-1.0.21-py3.7.egg"
    )
    egg_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(egg_path, "w") as egg:
        egg.writestr("Adafruit_Video_Looper/video_looper.py", "old video")
        egg.writestr("Adafruit_Video_Looper/omxplayer.py", "old omx")

    result = subprocess.run(
        [
            "bash",
            str(IMAGE_INSTALLER),
            "--rootfs",
            str(rootfs),
            "--bootfs",
            str(bootfs),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert (rootfs / "etc" / "systemd" / "system" / "rick-tv-pi.service").exists()
    assert not (
        rootfs
        / "etc"
        / "systemd"
        / "system"
        / "multi-user.target.wants"
        / "rick-tv-pi.service"
    ).exists()
    assert (
        rootfs / "home" / "pi" / "rick-tv" / "system" / "transition-placeholder.fb"
    ).read_bytes() == (
        PROJECT_ROOT
        / "provisioning"
        / "videolooper"
        / "assets"
        / "transition-placeholder.fb"
    ).read_bytes()
    assert (
        rootfs / "home" / "pi" / "rick-tv" / "system" / "interstitial-ad.fb"
    ).exists()
    assert (
        rootfs / "home" / "pi" / "rick-tv" / "playlists" / "channels.m3u"
    ).read_text(encoding="utf-8") == "#EXTM3U\n"
    assert (rootfs / "home" / "pi" / "rick-tv" / "media").is_dir()
    assert (rootfs / "home" / "pi" / "rick-tv" / "config").is_dir()
    assert (
        rootfs / "etc" / "sysctl.d" / "99-rick-tv-panic.conf"
    ).read_text(encoding="utf-8") == "kernel.panic=10\nkernel.panic_on_oops=1\n"
    assert (
        rootfs / "etc" / "systemd" / "system.conf.d" / "10-rick-tv-watchdog.conf"
    ).read_text(encoding="utf-8") == (
        "[Manager]\n"
        "RuntimeWatchdogSec=15s\n"
        "ShutdownWatchdogSec=2min\n"
    )
    assert "panic=10" in (bootfs / "cmdline.txt").read_text(encoding="utf-8")
    assert "dtparam=watchdog=on" in (bootfs / "config.txt").read_text(encoding="utf-8")

    with zipfile.ZipFile(egg_path) as egg:
        video_looper = egg.read("Adafruit_Video_Looper/video_looper.py").decode()
        omxplayer = egg.read("Adafruit_Video_Looper/omxplayer.py").decode()
    assert "_rick_tv" in video_looper
    assert "command_fifo" in video_looper
    assert "interstitial-ad.fb" in video_looper
    assert "transition-placeholder.fb" in video_looper
    assert "self.stop(0)  # Up to 3 second delay to let the old player stop." in omxplayer


def test_packaged_image_payload_installer_excludes_local_secrets_and_runtime_data() -> None:
    content = IMAGE_INSTALLER.read_text(encoding="utf-8")

    for excluded in [
        "rick-tv-server/.env",
        "rick-tv-server/data",
        "rick-tv-server/media",
        "rick-tv-server/config",
        "rick-tv-server/state",
        "manual-test-videos",
    ]:
        assert f'--exclude="{excluded}"' in content


def test_packaged_image_builder_dry_run_uses_sdm_for_local_base(tmp_path) -> None:
    base_image = tmp_path / "base.img"
    output_image = tmp_path / "rick-tv.img"
    base_image.write_bytes(b"fake image bytes")

    result = subprocess.run(
        [
            "bash",
            str(IMAGE_BUILDER),
            "--base-image",
            str(base_image),
            "--output-image",
            str(output_image),
        ],
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "RICK_TV_IMAGE_BUILDER_DRY_RUN": "1",
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert output_image.read_bytes() == base_image.read_bytes()
    assert "dry-run: would copy" in result.stdout
    assert "sdm --customize --batch --redo-customize --apt-options none" in result.stdout
    assert "--cscript" in result.stdout
    assert "sdm_rick_tv_custom_phase.sh" in result.stdout
    assert "--csrc" in result.stdout
    assert (tmp_path / "rick-tv.img.sha256").exists()


def test_packaged_image_builder_dry_run_downloads_videolooper_url(tmp_path) -> None:
    output_image = tmp_path / "rick-tv.img"

    result = subprocess.run(
        [
            "bash",
            str(IMAGE_BUILDER),
            "--base-image-url",
            "https://videolooper.de/video_looper_v2.11.zip",
            "--output-image",
            str(output_image),
        ],
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "RICK_TV_IMAGE_BUILDER_DRY_RUN": "1",
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "dry-run: would download https://videolooper.de/video_looper_v2.11.zip" in result.stdout
    assert "dry-run: would extract downloaded base image archive" in result.stdout
    assert "sdm --customize --batch --redo-customize --apt-options none" in result.stdout
    assert "video_looper_v2.11.zip" in result.stdout
    assert not output_image.exists()


def test_packaged_image_builder_no_longer_uses_manual_loop_mount_flow() -> None:
    content = IMAGE_BUILDER.read_text(encoding="utf-8")

    assert "losetup" not in content
    assert "mount \"${loop_device}p2\"" not in content
    assert "mount \"${loop_device}p1\"" not in content
    assert "sdm --customize" in content
    assert "--redo-customize" in content
    assert "--apt-options none" in content


def test_sdm_custom_phase_stages_payload_with_sdmpt_and_installs_runtime() -> None:
    content = SDM_PHASE_SCRIPT.read_text(encoding="utf-8")

    assert "phase=\"${1:-}\"" in content
    assert "$SDMPT" in content
    assert "sdm-readparams" in content
    assert "install_packaged_image_payload.sh" in content
    assert "--boot-config" in content
    assert "apt-get install -y --no-install-recommends" in content
    assert "python3-venv" in content
    assert "python3-pip" in content
    assert "python3-evdev" in content
    assert "python3 -m venv --system-site-packages /opt/rick-tv-pi/.venv" in content
    assert "pip<24.1" in content
    assert "setuptools>=61,<69" in content
    assert "/opt/rick-tv-pi/.venv/bin/pip install /opt/rick-tv-src/rick-tv-pi" in content
    assert "/opt/rick-tv-pi/.venv/bin/pip install 'evdev==1.7.1' 'certifi==2026.4.22'" in content
    assert content.index(
        "/opt/rick-tv-pi/.venv/bin/pip install /opt/rick-tv-src/rick-tv-pi"
    ) < content.index(
        "/opt/rick-tv-pi/.venv/bin/pip install 'evdev==1.7.1' 'certifi==2026.4.22'"
    )
    assert "apt-get upgrade" not in content
    assert "apt upgrade" not in content
    assert "RICK_TV_TELEGRAM_BOT_TOKEN" not in content
    assert "RICK_TV_TELEGRAM_ALLOWED_USER_IDS" not in content


def test_firstboot_example_uses_placeholders_only() -> None:
    content = FIRSTBOOT_EXAMPLE.read_text(encoding="utf-8")

    assert not REMOVED_RUNTIME_EXAMPLE.exists()
    assert "YOUR_WIFI_SSID" in content
    assert "SSH_PASSWORD" in content
    assert "YOUR_RICK_TV_API_TOKEN" in content
    assert "RICK_TV_SERVER_URL" in content
    assert "RICK_TV_REMOTE_POLL_INTERVAL_SECONDS" in content
    assert "RICK_TV_TOUCH_SCREEN_WIDTH" in content
    assert 'RICK_TV_TOUCH_SWAP_AXES="auto"' in content
    assert "RICK_TV_TELEGRAM_BOT_TOKEN" not in content
    assert "RICK_TV_TELEGRAM_ALLOWED_USER_IDS" not in content


def test_only_one_public_pi_env_example_remains() -> None:
    examples = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "provisioning").rglob("*.env.example")
    )

    assert examples == ["provisioning/rick-tv.env.example"]


def test_framebuffer_diagnostics_dry_run_records_expected_remote_commands(tmp_path) -> None:
    output_dir = tmp_path / "diagnostics"

    result = subprocess.run(
        [
            "bash",
            str(FRAMEBUFFER_DIAGNOSTICS),
            "--host",
            "pi@192.168.1.68",
            "--output-dir",
            str(output_dir),
            "--since",
            "2026-06-18 00:00:00",
        ],
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "RICK_TV_DIAGNOSTICS_DRY_RUN": "1",
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    commands = (output_dir / "commands.txt").read_text(encoding="utf-8")
    for expected in [
        "journalctl -u rick-tv-pi.service",
        "timeout 8 sudo supervisorctl tail -500 video_looper stdout",
        "timeout 8 sudo supervisorctl tail -500 video_looper stderr",
        "sudo dmesg",
        "/sys/class/graphics/fb0/virtual_size",
        "Adafruit_Video_Looper-1.0.21-py3.7.egg",
        "sed -E 's/(TOKEN|PASSWORD|PSK|KEY)=.*/\\1=<redacted>/'",
    ]:
        assert expected in commands


def test_framebuffer_diagnostics_script_packages_results_without_secrets() -> None:
    content = FRAMEBUFFER_DIAGNOSTICS.read_text(encoding="utf-8")

    assert "tar -czf" in content
    assert "rick-tv-framebuffer-diagnostics" in content
    assert "RICK_TV_DIAGNOSTICS_DRY_RUN" in content
    assert "StrictHostKeyChecking=no" in content
