from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_installs_ffmpeg_and_runs_server() -> None:
    dockerfile = PROJECT_ROOT / "Dockerfile"

    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")

    assert "ffmpeg" in content
    assert "uvicorn" in content
    assert "rick_tv_server.main:app" in content


def test_docker_compose_mounts_runtime_directories_and_publishes_port() -> None:
    compose_file = PROJECT_ROOT / "docker-compose.yml"

    assert compose_file.exists()
    content = compose_file.read_text(encoding="utf-8")

    assert "./media:/var/lib/rick-tv/media" in content
    assert "./config:/etc/rick-tv" in content
    assert "./state:/var/lib/rick-tv/state" in content
    assert "8080:8080" in content
    assert "restart: unless-stopped" in content


def test_docker_compose_supports_local_smoke_without_external_env() -> None:
    compose_file = PROJECT_ROOT / "docker-compose.yml"

    content = compose_file.read_text(encoding="utf-8")

    assert "RICK_TV_API_TOKEN: ${RICK_TV_API_TOKEN:-" in content
    assert "RICK_TV_API_TOKEN: ${RICK_TV_API_TOKEN:?" not in content


def test_server_docs_document_docker_build_and_import_smoke_check() -> None:
    docs_file = PROJECT_ROOT.parent / "docs" / "rick-tv-server.md"

    assert docs_file.exists()
    content = docs_file.read_text(encoding="utf-8")

    assert "docker build -t rick-tv-server:smoke ." in content
    assert "docker run --rm" in content
    assert "RICK_TV_API_TOKEN=test-token" in content
    assert "change-me-local" in content
    assert "import rick_tv_server.main" in content
    assert "/health" in content
