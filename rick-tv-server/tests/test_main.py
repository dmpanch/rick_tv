from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import get_type_hints

from fastapi import FastAPI

from rick_tv_server.config import ServerSettings


def import_main_with_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RICK_TV_API_TOKEN", "test-token")
    monkeypatch.setenv("RICK_TV_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("RICK_TV_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RICK_TV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("RICK_TV_PUBLIC_BASE_URL", "https://server.example.test")
    monkeypatch.setenv("RICK_TV_TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("RICK_TV_TELEGRAM_ALLOWED_USER_IDS", "42, 100")
    monkeypatch.setenv("RICK_TV_CHANNELS_PATH", str(tmp_path / "config" / "channels.yml"))
    monkeypatch.setenv("RICK_TV_DB_PATH", str(tmp_path / "state" / "custom.sqlite3"))
    sys.modules.pop("rick_tv_server.main", None)
    return importlib.import_module("rick_tv_server.main")


def test_load_settings_from_env_uses_runtime_environment(monkeypatch, tmp_path: Path):
    main = import_main_with_env(monkeypatch, tmp_path)

    settings = main.load_settings_from_env()

    assert settings == ServerSettings(
        media_dir=tmp_path / "media",
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        api_token="test-token",
        public_base_url="https://server.example.test",
        telegram_bot_token="bot-token",
        telegram_allowed_user_ids=(42, 100),
        channels_path=tmp_path / "config" / "channels.yml",
        db_path=tmp_path / "state" / "custom.sqlite3",
    )


def test_load_settings_from_env_defaults_channels_path_and_bot_settings(
    monkeypatch,
    tmp_path: Path,
):
    main = import_main_with_env(monkeypatch, tmp_path)
    monkeypatch.delenv("RICK_TV_TELEGRAM_BOT_TOKEN")
    monkeypatch.delenv("RICK_TV_TELEGRAM_ALLOWED_USER_IDS")
    monkeypatch.delenv("RICK_TV_CHANNELS_PATH")
    monkeypatch.delenv("RICK_TV_DB_PATH")

    settings = main.load_settings_from_env()

    assert settings.telegram_bot_token is None
    assert settings.telegram_allowed_user_ids == ()
    assert settings.channels_path == tmp_path / "config" / "channels.yml"
    assert settings.db_path is None


def test_load_settings_from_env_requires_api_token(monkeypatch, tmp_path: Path):
    main = import_main_with_env(monkeypatch, tmp_path)
    monkeypatch.delenv("RICK_TV_API_TOKEN")

    try:
        main.load_settings_from_env()
    except RuntimeError as error:
        assert str(error) == "RICK_TV_API_TOKEN must be set"
    else:
        raise AssertionError("missing API token should fail server startup")


def test_create_server_app_creates_runtime_directories(monkeypatch, tmp_path: Path):
    main = import_main_with_env(monkeypatch, tmp_path)
    initialized_settings = []

    class FakeDeliveryStateStore:
        def __init__(self, settings: ServerSettings):
            initialized_settings.append(settings)

    monkeypatch.setattr(main, "DeliveryStateStore", FakeDeliveryStateStore)

    app = main.create_server_app()

    assert isinstance(app, FastAPI)
    assert (tmp_path / "media").is_dir()
    assert (tmp_path / "config").is_dir()
    assert (tmp_path / "state").is_dir()
    assert initialized_settings == [main.load_settings_from_env()]


def test_create_server_app_interface_is_typed(monkeypatch, tmp_path: Path):
    main = import_main_with_env(monkeypatch, tmp_path)

    assert get_type_hints(main.create_server_app)["return"] is FastAPI
