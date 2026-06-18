# Rick TV

Rick TV — это связка серверного и клиентского сервисов для доставки видео на Raspberry Pi:

- `rick-tv-server` — FastAPI-сервис с очередью доставки и API.
- `rick-tv-bot` — Telegram long-polling runner в Docker Compose, который управляет каналами и загрузками.
- `rick-tv-pi` — клиент на Raspberry Pi, который опрашивает сервер, скачивает проверенные сервером ролики, сверяет `sha256` и обновляет плейлисты.

## Что делает проект

1. Видео загружаются на сервер и конвертируются в формат для проигрывания.
2. Сервер держит SQLite-библиотеку каналов, видео и статусов доставки.
3. Сервер отдаёт JSON registry для Pi через `/api/v1/channels`.
4. Raspberry Pi периодически синхронизирует registry, запрашивает `/api/v1/ready`, скачивает новые ролики по каналам, применяет команды удаления и подтверждает получение через `/api/v1/ack/{id}` или удаление через `/api/v1/delete-ack/{id}`.
5. `videolooper` проигрывает обновлённые плейлисты каналов и является выбранным стабильным runtime playback решением для Pi.
6. Telegram bot может поставить команду переключения канала; Pi забирает её через `/api/v1/commands` и подтверждает `/api/v1/commands/{id}/ack`.

## Аппаратные требования

Для сценария в репозитории используются:

- Raspberry Pi Zero W.
- Waveshare 2.8inch DPI LCD.

Также нужен сетевой доступ Pi к серверу.

## Предусловия

### Для сервера (`rick-tv-server`)

- Docker и Docker Compose.
- Свободный порт `8080`.
- Базовый токен доступа (`RICK_TV_API_TOKEN`).
- Telegram bot token и allowlist user IDs, если запускается `rick-tv-bot`.

### Для Raspberry Pi (`rick-tv-pi`)

- Python 3.7+.
- Сервисный запуск через `systemd`.
- Доступная для записи директория каналов (`RICK_TV_MEDIA_ROOT`).
- Непрерывное подключение к серверу по сети.

## Установка и запуск сервера

Запуск выполняется из директории `rick-tv-server`.

1) Скопируйте пример переменных и заполните его под свой хост.

```bash
cd rick-tv-server
cp .env.example .env
# отредактировать .env значениями под окружение
# RICK_TV_UID=$(id -u), RICK_TV_GID=$(id -g) сохраняют runtime-файлы доступными на хосте
```

2) Запустить сервис.

```bash
mkdir -p data/media data/config data/state
docker compose up -d --build
```

Файл `docker-compose.yml` берёт значения `RICK_TV_*` из окружения (или `.env`).
Контейнеры запускаются под `RICK_TV_UID:RICK_TV_GID`, чтобы bind-mounted
runtime-файлы оставались читаемыми и редактируемыми с хоста. По умолчанию
Compose монтирует всё runtime-состояние из `./data`; для постоянной установки
задайте `RICK_TV_DATA_DIR=/srv/rick-tv` или другой абсолютный путь на диске.

API запускается обычным `docker compose up`. Telegram runner находится в том же Compose-файле как сервис `rick-tv-bot`; он использует тот же image и общий `RICK_TV_DATA_DIR`. Для запуска бота задайте `RICK_TV_TELEGRAM_BOT_TOKEN` и `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`, затем включите профиль:

```bash
docker compose --profile bot up -d --build
```

## Установка и запуск на Raspberry Pi

Для текущего legacy `videolooper` image дефолтный SSH-доступ:

- user: `pi`
- password: `video`

После первого входа замените пароль или добавьте SSH key и отключите парольный доступ, если Pi будет жить в постоянной сети.

Для новой установки предпочтительный путь — подготовить known-good legacy
`videolooper` image как Rick TV image. Смонтируйте root/boot partitions образа и
запустите:

```bash
rick-tv-pi/provisioning/image/install_packaged_image_payload.sh \
  --rootfs /mnt/rick-tv-root \
  --bootfs /mnt/rick-tv-boot
```

На boot partition появится `rick-tv.env.example`; скопируйте его в
`rick-tv.env`, заполните Wi-Fi, SSH, hostname, API token и runtime-параметры.
На первом boot `rick-tv-firstboot.service` создаст `/etc/rick-tv-pi.env`,
настроит Wi-Fi/SSH, установит pinned videolooper overrides/assets, включит
`rick-tv-pi.service` и больше не будет перетирать ручные правки.

Для текущей lab Pi можно продолжать обновляться по SSH. Перед деплоем
подготовьте `/etc/rick-tv-pi.env` из примера:

```bash
sudo cp rick-tv-pi/provisioning/rick-tv-pi.env.example /etc/rick-tv-pi.env
sudo nano /etc/rick-tv-pi.env
```

Редактировать файл нужно **до** запуска деплоя, чтобы нужные значения попали в систему сразу.

После этого выполнить:

```bash
rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy
```

Raw framebuffer placeholders на Pi сейчас остаются частью legacy videolooper
runtime. Код логирует FIFO commands, playlist reload, показ
`transition-placeholder.fb`/`interstitial-ad.fb` и границы `player.play(...)`.
Channel switch показывает только transition placeholder и подавляет следующий
interstitial; обновление playlist внутри текущего канала не рисует transition и
использует обычный in-channel interstitial перед следующим playback.

### Что должно быть в `/etc/rick-tv-pi.env`

В репозитории уже есть шаблон с пояснениями:

- `rick-tv-pi/provisioning/rick-tv-pi.env.example`

Коротко по параметрам:

- `RICK_TV_SERVER_URL` — адрес сервера API (`http://...:8080`).
- `RICK_TV_API_TOKEN` — общий токен доступа (тот же, что в `rick-tv-server/.env`).
- `RICK_TV_MEDIA_ROOT` — корень папок каналов на Pi.
- `RICK_TV_METADATA_PATH` — путь к `channels.json` (опционально).
- `RICK_TV_POLL_INTERVAL_SECONDS` — интервал опроса сервера в секундах.
- `RICK_TV_REMOTE_POLL_INTERVAL_SECONDS` — быстрый интервал опроса Telegram remote-control команд.
- `RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT` — путь к рабочей папке `videolooper`.
- `RICK_TV_VIDEOLOOPER_COMMAND_PATH` — FIFO для команд проигрывателю.
- `RICK_TV_CHANNEL_SHUFFLE_SECONDS` — как часто перемешивать плейлист внутри канала.
- `RICK_TV_TOUCH_SCREEN_WIDTH` — ширина touch input-экрана.
- `RICK_TV_TOUCH_SCREEN_HEIGHT` — высота touch input-экрана.
- `RICK_TV_TOUCH_SWAP_AXES` — своп осям `true/false`.
- `RICK_TV_TOUCH_GESTURE_HORIZONTAL_AXIS` — ось для определения жеста `x` или `y`.
- `RICK_TV_TOUCH_INVERT_X` — инверсия X (`1/0`, `true/false`, `on/off`, `yes/no`).
- `RICK_TV_TOUCH_INVERT_Y` — инверсия Y (`1/0`, `true/false`, `on/off`, `yes/no`).
- `RICK_TV_TOUCH_DEVICE` — путь к устройству ввода, если нужно принудительно указать.
- `RICK_TV_RUNTIME_TICK_SECONDS` — шаг внутреннего цикла runtime.

Минимум для запуска:

- `RICK_TV_SERVER_URL`
- `RICK_TV_API_TOKEN`
- `RICK_TV_MEDIA_ROOT`
- `RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT`
- `RICK_TV_VIDEOLOOPER_COMMAND_PATH`

Запустить сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rick-tv-pi.service
sudo systemctl status rick-tv-pi.service
```

## Как устроены каналы

Каналы — это папки внутри `RICK_TV_MEDIA_ROOT`, например:

- `01_Citadel/`
- `02_Interdimensional_Cable/`
- `03_Empty/`

Канал участвует только если внутри есть хотя бы один `.mp4`. Пустые папки не попадают в навигацию, плейлисты и список каналов для polling API до появления playable `.mp4`.

Серверная SQLite DB является canonical registry для выбора каналов в Telegram и для первого опроса Pi. Endpoint `/api/v1/channels` отдаёт JSON вида `{"channels": {"01_Citadel": {"display_name": "Citadel"}}}`.

Если сервер стартует впервые без каналов, он создаёт пустую SQLite DB. `/api/v1/channels` вернёт `{"channels": {}}`, бот позволит добавить первый канал, а Pi с настроенным `RICK_TV_METADATA_PATH` не будет fallback-иться на локальные каналы до появления registry-каналов на сервере.

Серверная медиатека хранится в читаемой структуре `media/library/<channel_id>/<item_id>/original/...` и `media/library/<channel_id>/<item_id>/converted/...`. В DB сохраняются относительные пути, статус, delivery filename и `sha256` converted-файла.

## Как заливать видео через бота

Telegram runner реализован в `rick_tv_server.bot_runner` и запускается сервисом `rick-tv-bot`.

Типовой поток:

1. Allowlisted пользователь открывает Telegram command menu.
2. `/add_channel` просит только название; stable channel ID создаётся автоматически инкрементом, например `04_Birdperson_TV`.
3. `/list_channels` показывает каналы в виде `01 - Citadel`; выбор канала открывает `Switch channel on Pi`, `List all videos`, `Rename channel` и `Delete channel`.
4. `List all videos` показывает каждое активное видео канала отдельной кнопкой. Внутри видео доступны `Download`, `Delete` и `Back`.
5. `Switch channel on Pi` ставит remote command; Pi забирает её быстрым poll и переключается через videolooper FIFO, если канал уже playable локально.
6. `Download` отправляет converted Pi-ready `.mp4` обратно в Telegram.
7. `Delete` удаляет original и converted файлы с сервера, убирает видео из active library и ставит команду удаления для Pi. Pi удалит локальную копию при следующем успешном poll и подтвердит `/api/v1/delete-ack/{id}`.
8. `/restore_all_videos` запрашивает подтверждение на повторную доставку всей активной библиотеки.
9. Пользователь отправляет Telegram `video` или `document`; бот после этого предлагает выбрать канал.
10. После выбора канала бот скачивает файл локально и вызывает `UploadProcessor.process_upload(...)`.
11. Сервер сохраняет original upload и converted Pi-ready `.mp4` в `media/library/<channel_id>/<item_id>/...`.
12. Ролик становится `pending_delivery`, затем Pi забирает его с сервера; после ack сервер переводит его в `available`.

Сервер приводит файл к целевому профилю (`640x480`, `h264`, `aac`) и валидирует converted `.mp4` через `ffprobe` до появления файла в `/api/v1/ready`. `ffmpeg` и `ffprobe` нужны только серверу: Pi скачивает уже проверенный файл, сверяет `sha256`, кладет его в каталог канала и отправляет ack.

Delete из экрана конкретного видео канала — физическое удаление с сервера плюс асинхронное удаление с Pi. Действие `restore all` в Telegram requeue-ит активные `available` элементы, чтобы заменить или восстановить Pi и заново доставить библиотеку.
