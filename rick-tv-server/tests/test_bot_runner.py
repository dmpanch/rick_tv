from __future__ import annotations

import logging
from pathlib import Path

from rick_tv_server.config import ServerSettings


def make_settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(
        media_dir=tmp_path / "media",
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        api_token="test-token",
        public_base_url="https://example.test",
        telegram_bot_token="123456:ABC",
        telegram_allowed_user_ids=(42,),
        channels_path=tmp_path / "config" / "channels.yml",
    )


def test_bot_runner_main_builds_application_and_runs_long_polling(
    tmp_path: Path,
    monkeypatch,
):
    from rick_tv_server import bot_runner

    settings = make_settings(tmp_path)
    built = []
    ran = []

    class FakeApplication:
        def run_polling(self) -> None:
            ran.append(True)

    def fake_build_application(
        built_settings,
        channel_store,
        state_store,
        upload_processor,
    ):
        built.append(
            {
                "settings": built_settings,
                "channel_path": channel_store.path,
                "state_path": state_store.state_path,
                "processor_settings": upload_processor.settings,
            }
        )
        return FakeApplication()

    monkeypatch.setattr(bot_runner, "load_settings_from_env", lambda: settings)
    monkeypatch.setattr(bot_runner, "build_application", fake_build_application)

    bot_runner.main()

    assert built == [
        {
            "settings": settings,
            "channel_path": settings.channels_path,
            "state_path": settings.state_dir / "queue.json",
            "processor_settings": settings,
        }
    ]
    assert ran == [True]
    assert settings.media_dir.is_dir()
    assert settings.config_dir.is_dir()
    assert settings.state_dir.is_dir()


def test_bot_runner_logging_mutes_http_client_info_logs() -> None:
    from rick_tv_server import bot_runner

    logging.getLogger("httpx").setLevel(logging.INFO)

    bot_runner.configure_logging()

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
