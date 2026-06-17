from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_deploy_restarts_videolooper_before_pi_runtime() -> None:
    script = PROJECT_ROOT / "provisioning" / "deploy_videolooper_image.sh"

    content = script.read_text(encoding="utf-8")

    assert content.index("supervisorctl restart video_looper") < content.index(
        "systemctl restart rick-tv-pi.service"
    )
