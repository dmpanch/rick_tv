import json

from rick_tv_pi.channels import discover_channels


def test_discovers_immediate_directories_in_channel_order(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()

    (media_root / "01_Citadel").mkdir()
    (media_root / "02_Interdimensional_Cable").mkdir()
    (media_root / "03_Empty").mkdir()
    (media_root / "Garage").mkdir()
    (media_root / "10_Late").mkdir()
    (media_root / "Garage" / "Nested").mkdir()
    (media_root / "not_a_channel.mp4").write_text("not a directory")
    (media_root / "01_Citadel" / "episode.mp4").touch()
    (media_root / "02_Interdimensional_Cable" / "episode.mp4").touch()
    (media_root / "10_Late" / "episode.mp4").touch()
    (media_root / "Garage" / "episode.mp4").touch()

    channels = discover_channels(media_root, metadata_path=None)

    assert [channel.id for channel in channels] == [
        "01_Citadel",
        "02_Interdimensional_Cable",
        "10_Late",
        "Garage",
    ]
    assert [channel.number for channel in channels] == [1, 2, 3, 4]
    assert [channel.display_name for channel in channels] == [None, None, None, None]
    assert [channel.path for channel in channels] == [
        media_root / "01_Citadel",
        media_root / "02_Interdimensional_Cable",
        media_root / "10_Late",
        media_root / "Garage",
    ]


def test_metadata_only_names_existing_directories(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()

    (media_root / "01_Citadel").mkdir()
    (media_root / "Garage").mkdir()
    (media_root / "01_Citadel" / "episode.mp4").touch()
    (media_root / "Garage" / "episode.mp4").touch()
    metadata_path = tmp_path / "channels.json"
    metadata_path.write_text(
        json.dumps(
            {
                "channels": {
                    "01_Citadel": {
                        "display_name": "Citadel TV",
                    },
                    "Missing": {
                        "display_name": "Ignored",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    channels = discover_channels(media_root, metadata_path=metadata_path)

    channels_by_id = {channel.id: channel for channel in channels}
    assert channels_by_id["01_Citadel"].display_name == "Citadel TV"
    assert "Missing" not in channels_by_id
    assert channels_by_id["Garage"].display_name is None
