from rick_tv_pi.channels import discover_channels


def test_discovers_immediate_directories_in_channel_order(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()

    (media_root / "01_Citadel").mkdir()
    (media_root / "02_Interdimensional_Cable").mkdir()
    (media_root / "Garage").mkdir()
    (media_root / "10_Late").mkdir()
    (media_root / "Garage" / "Nested").mkdir()
    (media_root / "not_a_channel.mp4").write_text("not a directory")

    channels = discover_channels(media_root, metadata_path=None)

    assert [channel.id for channel in channels] == [
        "01_Citadel",
        "02_Interdimensional_Cable",
        "10_Late",
        "Garage",
    ]
