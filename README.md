# Rick TV

Rick TV — это связка серверного и клиентского сервисов для доставки видео на Raspberry Pi:

- `rick-tv-server` — FastAPI-сервис с очередью доставки и API.
- `rick-tv-bot` — Telegram long-polling runner в Docker Compose, который управляет каналами и загрузками.
- `rick-tv-pi` — клиент на Raspberry Pi, который опрашивает сервер, скачивает ролики, проверяет формат и обновляет плейлисты.

## Что делает проект

1. Видео загружаются на сервер и конвертируются в формат для проигрывания.
2. Сервер держит статусы очереди доставки.
3. Сервер хранит YAML registry каналов и отдаёт его Pi через `/api/v1/channels.yml`.
4. Raspberry Pi периодически синхронизирует registry, запрашивает `/api/v1/ready`, скачивает новые ролики по каналам и подтверждает получение через `/api/v1/ack/{id}`.
5. `videolooper` проигрывает обновлённые плейлисты каналов и является выбранным стабильным runtime playback решением для Pi.

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
```

2) Запустить сервис.

```bash
mkdir -p media config state
docker compose up -d --build
```

Файл `docker-compose.yml` берёт значения `RICK_TV_*` из окружения (или `.env`).

API запускается обычным `docker compose up`. Telegram runner находится в том же Compose-файле как сервис `rick-tv-bot`; он использует тот же image и общие `media/config/state` volumes. Для запуска бота задайте `RICK_TV_TELEGRAM_BOT_TOKEN` и `RICK_TV_TELEGRAM_ALLOWED_USER_IDS`, затем включите профиль:

```bash
docker compose --profile bot up -d --build
```

## Установка и запуск на Raspberry Pi

Перед деплоем подготовьте `/etc/rick-tv-pi.env` из примера:

```bash
sudo cp rick-tv-pi/provisioning/rick-tv-pi.env.example /etc/rick-tv-pi.env
sudo nano /etc/rick-tv-pi.env
```

Редактировать файл нужно **до** запуска деплоя, чтобы нужные значения попали в систему сразу.

После этого выполнить:

```bash
rick-tv-pi/provisioning/deploy_videolooper_image.sh deploy
```

### Что должно быть в `/etc/rick-tv-pi.env`

В репозитории уже есть шаблон с пояснениями:

- `rick-tv-pi/provisioning/rick-tv-pi.env.example`

Коротко по параметрам:

- `RICK_TV_SERVER_URL` — адрес сервера API (`http://...:8080`).
- `RICK_TV_API_TOKEN` — общий токен доступа (тот же, что в `rick-tv-server/.env`).
- `RICK_TV_MEDIA_ROOT` — корень папок каналов на Pi.
- `RICK_TV_METADATA_PATH` — путь к `channels.yml` (опционально).
- `RICK_TV_POLL_INTERVAL_SECONDS` — интервал опроса сервера в секундах.
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

Серверный `channels.yml` является registry для выбора каналов в Telegram и для первого опроса Pi. Pi может знать ID канала из registry и получить первый ролик даже до появления локальной папки с `.mp4`; после доставки канал появится в навигации.

## Как заливать видео через бота

Telegram runner реализован в `rick_tv_server.bot_runner` и запускается сервисом `rick-tv-bot`.

Типовой поток:

1. Allowlisted пользователь открывает `/channels`, создаёт или переименовывает канал.
2. Пользователь запускает `/upload`, выбирает канал и отправляет Telegram `video` или `document`.
3. Бот скачивает файл локально и вызывает `UploadProcessor.process_upload(...)`.
4. Сервер сохраняет original upload и converted Pi-ready `.mp4`.
5. Ролик становится `pending`, затем Pi забирает его с сервера.

Сервер приводит файл к целевому профилю (`640x480`, `h264`, `aac`), а Pi проверяет готовый файл через `ffprobe` перед финальным размещением.

Archive delete в приложении — мягкое удаление из активной библиотеки: физические original/converted файлы остаются на сервере. Действие `restore all` в Telegram requeue-ит активные archived элементы, чтобы заменить или восстановить Pi и заново доставить библиотеку.
