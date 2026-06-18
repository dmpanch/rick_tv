from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIRSTBOOT_SCRIPT = PROJECT_ROOT / "provisioning" / "firstboot" / "rick-tv-firstboot.sh"
FIRSTBOOT_SERVICE = PROJECT_ROOT / "provisioning" / "firstboot" / "rick-tv-firstboot.service"
FIRSTBOOT_EXAMPLE = PROJECT_ROOT / "provisioning" / "firstboot" / "rick-tv.env.example"
IMAGE_INSTALLER = (
    PROJECT_ROOT / "provisioning" / "image" / "install_packaged_image_payload.sh"
)
IMAGE_BUILDER = PROJECT_ROOT / "provisioning" / "image" / "build_packaged_image.sh"
FRAMEBUFFER_DIAGNOSTICS = (
    PROJECT_ROOT / "provisioning" / "scripts" / "collect-framebuffer-diagnostics.sh"
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
        "rick-tv-server/.env",
        "rick-tv-server/data",
        "rick-tv-server/media",
        "rick-tv-server/config",
        "rick-tv-server/state",
        "manual-test-videos",
    ]:
        assert f'--exclude="{excluded}"' in content


def test_firstboot_script_applies_boot_config_without_real_system_commands(tmp_path) -> None:
    rootfs = tmp_path / "rootfs"
    bootfs = tmp_path / "bootfs"
    bootfs.mkdir()
    (rootfs / "opt" / "rick-tv-src").mkdir(parents=True)
    (bootfs / "rick-tv.env").write_text(
        "\n".join(
            [
                "WIFI_COUNTRY=UA",
                "WIFI_SSID='Test Network'",
                "WIFI_PSK='test-password'",
                "RICK_TV_HOSTNAME=rick-tv-test",
                "SSH_ENABLE=true",
                "SSH_AUTHORIZED_KEY='ssh-ed25519 AAAATEST rick-tv'",
                "RICK_TV_SERVER_URL=http://192.168.1.10:8080",
                "RICK_TV_API_TOKEN=test-token",
                "RICK_TV_MEDIA_ROOT=/home/pi/rick-tv/media",
                "RICK_TV_METADATA_PATH=/home/pi/rick-tv/config/channels.json",
                "RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT=/home/pi/rick-tv/playlists",
                "RICK_TV_VIDEOLOOPER_COMMAND_PATH=/tmp/rick-tv-videolooper.fifo",
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
    assert (rootfs / "etc" / "rick-tv-pi.env").read_text(encoding="utf-8") == (
        "RICK_TV_SERVER_URL=http://192.168.1.10:8080\n"
        "RICK_TV_API_TOKEN=test-token\n"
        "RICK_TV_MEDIA_ROOT=/home/pi/rick-tv/media\n"
        "RICK_TV_METADATA_PATH=/home/pi/rick-tv/config/channels.json\n"
        "RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT=/home/pi/rick-tv/playlists\n"
        "RICK_TV_VIDEOLOOPER_COMMAND_PATH=/tmp/rick-tv-videolooper.fifo\n"
    )
    assert "ssid=\"Test Network\"" in (
        rootfs / "etc" / "wpa_supplicant" / "wpa_supplicant.conf"
    ).read_text(encoding="utf-8")
    assert (rootfs / "etc" / "hostname").read_text(encoding="utf-8") == "rick-tv-test\n"
    assert "ssh-ed25519 AAAATEST rick-tv" in (
        rootfs / "home" / "pi" / ".ssh" / "authorized_keys"
    ).read_text(encoding="utf-8")
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


def test_packaged_image_builder_dry_run_copies_base_and_reports_steps(tmp_path) -> None:
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
    assert "dry-run: would attach loop device with partitions" in result.stdout
    assert "dry-run: would run install_packaged_image_payload.sh" in result.stdout
    assert (tmp_path / "rick-tv.img.sha256").exists()


def test_packaged_image_builder_mounts_stages_and_cleans_up_loop_device() -> None:
    content = IMAGE_BUILDER.read_text(encoding="utf-8")

    for expected in [
        "losetup --find --partscan --show",
        "mount \"${loop_device}p2\"",
        "mount \"${loop_device}p1\"",
        "install_packaged_image_payload.sh",
        "sha256sum",
        "trap cleanup EXIT",
        "umount",
        "losetup -d",
    ]:
        assert expected in content


def test_firstboot_example_uses_placeholders_only() -> None:
    content = FIRSTBOOT_EXAMPLE.read_text(encoding="utf-8")

    assert "YOUR_WIFI_SSID" in content
    assert "YOUR_RICK_TV_API_TOKEN" in content
    assert "8905534821" not in content
    assert "104065396" not in content


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
