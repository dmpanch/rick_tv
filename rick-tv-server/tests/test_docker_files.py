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

    assert "${RICK_TV_DATA_DIR:-./data}/media:/var/lib/rick-tv/media" in content
    assert "${RICK_TV_DATA_DIR:-./data}/config:/etc/rick-tv" in content
    assert "${RICK_TV_DATA_DIR:-./data}/state:/var/lib/rick-tv/state" in content
    assert "8080:8080" in content
    assert "restart: unless-stopped" in content


def test_docker_compose_supports_local_smoke_without_external_env() -> None:
    compose_file = PROJECT_ROOT / "docker-compose.yml"

    content = compose_file.read_text(encoding="utf-8")

    assert "RICK_TV_API_TOKEN: ${RICK_TV_API_TOKEN:-" in content
    assert "RICK_TV_API_TOKEN: ${RICK_TV_API_TOKEN:?" not in content


def test_docker_compose_runs_services_as_host_user_by_default() -> None:
    compose_file = PROJECT_ROOT / "docker-compose.yml"

    content = compose_file.read_text(encoding="utf-8")

    assert content.count('user: "${RICK_TV_UID:-1000}:${RICK_TV_GID:-1000}"') == 2


def test_docker_compose_runs_bot_service_with_shared_runtime_volumes() -> None:
    compose_file = PROJECT_ROOT / "docker-compose.yml"

    content = compose_file.read_text(encoding="utf-8")

    assert "rick-tv-bot:" in content
    assert "python -m rick_tv_server.bot_runner" in content
    assert (
        content.count("${RICK_TV_DATA_DIR:-./data}/media:/var/lib/rick-tv/media")
        == 2
    )
    assert content.count("${RICK_TV_DATA_DIR:-./data}/config:/etc/rick-tv") == 2
    assert (
        content.count("${RICK_TV_DATA_DIR:-./data}/state:/var/lib/rick-tv/state")
        == 2
    )
    assert "RICK_TV_TELEGRAM_BOT_TOKEN" in content
    assert "RICK_TV_TELEGRAM_ALLOWED_USER_IDS" in content
    assert "RICK_TV_CHANNELS_PATH" not in content


def test_docker_compose_runs_bot_by_default_without_profile() -> None:
    compose_file = PROJECT_ROOT / "docker-compose.yml"

    content = compose_file.read_text(encoding="utf-8")

    assert "profiles:" not in content


def test_dockerignore_excludes_runtime_volume_directories() -> None:
    dockerignore = PROJECT_ROOT / ".dockerignore"

    assert dockerignore.exists()
    content = dockerignore.read_text(encoding="utf-8")

    assert "media/" in content
    assert "config/" in content
    assert "state/" in content
    assert "data/" in content


def test_env_example_documents_single_host_data_dir() -> None:
    env_example = PROJECT_ROOT / ".env.example"

    content = env_example.read_text(encoding="utf-8")

    assert "RICK_TV_DATA_DIR=./data" in content
    assert "/srv/rick-tv" in content


def test_env_example_documents_telegram_as_default_stack_required() -> None:
    env_example = PROJECT_ROOT / ".env.example"

    content = env_example.read_text(encoding="utf-8")

    assert "Required for the default Docker Compose stack" in content


def test_startup_docs_use_one_command_without_bot_profile_or_manual_dirs() -> None:
    docs_files = [
        PROJECT_ROOT.parent / "README.md",
        PROJECT_ROOT.parent / "docs" / "rick-tv-server.md",
    ]

    for docs_file in docs_files:
        content = docs_file.read_text(encoding="utf-8")
        old_profile_command = "docker compose " + "--profile" + " bot"
        old_manual_dirs = "mkdir -p data/media " + "data/config data/state"

        assert "docker compose up -d" in content
        assert old_profile_command not in content
        assert old_manual_dirs not in content


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
