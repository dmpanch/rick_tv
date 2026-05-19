#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${RICK_TV_SMOKE_DIR:-/tmp/rick-tv-smoke}"
SERVER_MEDIA_DIR="$WORK_DIR/server-media"
SERVER_CONFIG_DIR="$WORK_DIR/server-config"
SERVER_STATE_DIR="$WORK_DIR/server-state"
PI_MEDIA_DIR="$WORK_DIR/pi-media"

mkdir -p "$WORK_DIR/sources" "$SERVER_MEDIA_DIR" "$SERVER_CONFIG_DIR" "$SERVER_STATE_DIR" "$PI_MEDIA_DIR"

curl -L \
  "https://samplefile.com/samples/download/video/mp4/mp4_5s_sample_file_279KB.mp4/" \
  -o "$WORK_DIR/sources/sample-1.mp4"
curl -L \
  "https://samplefile.com/samples/download/video/mp4/mp4_h264_aac_12s_sample.mp4/" \
  -o "$WORK_DIR/sources/sample-2.mp4"

"$ROOT_DIR/.venv/bin/python" - <<'PY'
import os
import shutil
from pathlib import Path

from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore
from rick_tv_server.uploads import UploadProcessor

work_dir = Path(os.environ.get("RICK_TV_SMOKE_DIR", "/tmp/rick-tv-smoke"))
settings = ServerSettings(
    media_dir=work_dir / "server-media",
    config_dir=work_dir / "server-config",
    state_dir=work_dir / "server-state",
    api_token="smoke-token",
    public_base_url="http://127.0.0.1:8080",
)
store = DeliveryStateStore(settings)
processor = UploadProcessor(
    settings=settings,
    state_store=store,
    item_id_factory=iter(["smoke-channel-1", "smoke-channel-2"]).__next__,
)

items = [
    processor.process_upload(
        user_id="hardware-smoke",
        channel_id="01_Citadel",
        source_path=work_dir / "sources" / "sample-1.mp4",
        original_filename="sample-1.mp4",
    ),
    processor.process_upload(
        user_id="hardware-smoke",
        channel_id="02_Interdimensional_Cable",
        source_path=work_dir / "sources" / "sample-2.mp4",
        original_filename="sample-2.mp4",
    ),
]

pi_media = work_dir / "pi-media"
for item in items:
    channel_dir = pi_media / item.channel_id
    channel_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(item.converted_path, channel_dir / item.filename)

(pi_media / "03_Empty").mkdir(parents=True, exist_ok=True)
print(pi_media)
PY

echo "Prepared Pi media under $PI_MEDIA_DIR"
