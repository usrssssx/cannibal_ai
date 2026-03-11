# cannibal_ai
Автоматический мониторинг Telegram‑каналов, дедупликация новостей и рерайт с сохранением Tone of Voice.

## Что делает
- Слушает новые посты в Telegram‑каналах через Telethon (userbot).
- Фильтрует рекламу по стоп‑словам.
- Дедуплицирует посты по эмбеддингам (ChromaDB).
- Переписывает уникальные посты в стиле админа через LLM.
- Даёт editorial workflow в Mini App: источники за 30 дней, AI‑категории,
  выбор исходных постов и генерация готовых драфтов в чат с ботом.
- Опционально подбирает/генерирует изображение для поста.
- Сохраняет сырой текст в SQLite.
- Записывает итоговый текст в файл `OUTPUT_PATH`.

## Требования
- Python 3.11+
- Telethon userbot (нужны api_id и api_hash)
- OpenAI, Ollama или OpenAI‑compatible `llama.cpp` server

## Установка
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Конфигурация
Создай `.env` в корне проекта:
```bash
cp .env.example ./.env
```

Заполни ключи:
```
TELETHON_API_ID=...
TELETHON_API_HASH=...
TARGET_CHANNELS=channel_one,channel_two
AUTO_STYLE_CHANNEL=admin_style_channel
```

### Ollama (по умолчанию)
```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b-instruct
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
PROCESSOR_WORKERS=2
```

Опциональные параметры Ollama (передаются в `/api/chat`):
```
OLLAMA_TEMPERATURE=0.4
OLLAMA_NUM_CTX=4096
OLLAMA_NUM_PREDICT=512
OLLAMA_TOP_P=0.9
OLLAMA_TOP_K=40
OLLAMA_REPEAT_PENALTY=1.1
OLLAMA_REPEAT_LAST_N=64
OLLAMA_MIROSTAT=0
OLLAMA_MIROSTAT_TAU=5.0
OLLAMA_MIROSTAT_ETA=0.1
OLLAMA_NUM_THREAD=4
```

### OpenAI
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

### llama.cpp
Если у вас локально поднят OpenAI‑compatible server на `llama.cpp`, используйте:
```
LLM_PROVIDER=llama_cpp
LLAMA_CPP_BASE_URL=http://localhost:8080
LLAMA_CPP_MODEL=local-model
# опционально, если embedding endpoint использует отдельную модель
LLAMA_CPP_EMBEDDING_MODEL=local-model
```

Поддерживаются оба типовых варианта embedding API:
- `/embedding`
- `/v1/embeddings`

### Изображения (Pexels + Replicate)
Комбо-режим: сначала поиск в Pexels, если не найдено — генерация в Replicate.
```
IMAGE_ENABLED=true
IMAGE_SEARCH_PROVIDER=pexels
IMAGE_GENERATION_PROVIDER=replicate
IMAGE_SAFE_ONLY=true
IMAGE_DOWNLOAD=true
IMAGE_OUTPUT_DIR=./images
IMAGE_QUERY_MAX_WORDS=12
IMAGE_PROMPT_STYLE=photojournalistic, realistic, natural lighting, high detail, no text
PEXELS_API_KEY=your_key
PEXELS_PER_PAGE=1
PEXELS_ORIENTATION=landscape
REPLICATE_API_TOKEN=your_token
REPLICATE_MODEL_VERSION=your_model_version_hash
REPLICATE_POLL_INTERVAL=1.5
REPLICATE_TIMEOUT=60
REPLICATE_NEGATIVE_PROMPT=nsfw, nude, nudity, gore, violence, text
```

Модели Ollama:
```bash
ollama pull qwen2.5:3b-instruct
ollama pull nomic-embed-text
```

## Запуск
```bash
python -m cannibal_core.main
```

При первом запуске Telethon запросит номер телефона и код подтверждения в терминале.
Если задан `AUTO_STYLE_CHANNEL`, основной сервис будет переписывать входящие посты
в стиле этого канала. Если переменная не задана, сервис использует fallback на
профиль источника или встроенные примеры.

## Telegram бот
Бот принимает команды и выдает посты в стиле выбранного канала. Бот использует
ваш userbot‑аккаунт для чтения каналов, поэтому должен быть залогинен один раз.
Также в бот можно переслать пост из нужного канала: источник сохранится для
editorial workflow и появится в Mini App.

### Переменные окружения
```
BOT_TOKEN=123456:ABCDEF
BOT_ALLOWED_USERS=123456789
ENFORCE_ALLOWED_USERS=true
BOT_STYLE_LIMIT=120
BOT_SOURCE_LIMIT=1
BOT_GUIDE_URL=https://your-docs-url
BOT_USER_SESSION=cannibal_bot_userbot
WEBAPP_USER_SESSION=cannibal_webapp_userbot
```

`BOT_ALLOWED_USERS` — список user_id через запятую (если пусто, доступ открыт всем).

### Запуск бота
```bash
python -m cannibal_core.bot
```

Бот использует панель управления с кнопками. Команды остаются для быстрого ввода.

Команды в боте:
```
/style <channel>   — канал стиля
/sources <ch1,ch2> — источники новостей
/limit <N>         — сколько постов брать с источника
/run               — сгенерировать посты
/status            — текущие настройки
/reset             — сброс
/menu              — панель управления
```

## WebApp
WebApp открывается из бота и теперь работает как редакторский pipeline:
- канал‑референс для стиля;
- список каналов‑источников;
- AI‑сводка тем за последние 30 дней;
- просмотр постов внутри темы;
- выбор одного или нескольких исходников;
- генерация итоговых постов с отправкой в чат с ботом.

### Настройки
```
WEBAPP_URL=https://your-public-url
ENFORCE_ALLOWED_USERS=true
WEBAPP_HOST=127.0.0.1
WEBAPP_PORT=8000
WEBAPP_MAX_AGE_SEC=86400
WEBAPP_DUPLICATE_TO_CHAT=true
CLOUDFLARED_TUNNEL_TOKEN=your_token
```

### Запуск WebApp
```bash
python -m cannibal_core.webapp_server
```

## Редакционный workflow
Целевой сценарий для владельца канала:
1. Открыть чат с ботом и зайти в Mini App.
2. Указать свой канал как `style reference`.
3. Добавить источники вручную или переслать боту посты из нужных каналов.
4. Нажать `Обновить темы` и дождаться сводки за 30 дней.
5. Открыть интересующую тему и выбрать один или несколько постов.
6. Нажать `Сгенерировать`.
7. Получить готовые тексты в Mini App и отдельными сообщениями в чате с ботом.

Под капотом workflow устроен как newsroom orchestration:
- `TopicPlannerAgent` выделяет редакционные темы периода.
- `TopicClassifierAgent` назначает постам 1–3 категории.
- `EditorialPlannerAgent` вытаскивает facts/brief из выбранного исходника.
- `EditorialWriterAgent` пишет финальный пост в стиле референс‑канала.

### Публичный URL (локально)
Рекомендовано использовать Cloudflare Tunnel со стабильным URL:
```bash
cloudflared tunnel run --token $CLOUDFLARED_TUNNEL_TOKEN
```
Затем установите `WEBAPP_URL` на выданный Cloudflare домен.

Альтернатива — ngrok (временный URL):
```bash
ngrok http 8000
```
Если нужен стабильный URL — используйте reserved domain в ngrok и задайте `NGROK_DOMAIN`.

Авто‑обновление `WEBAPP_URL` из ngrok:
```bash
python scripts/update_webapp_url.py
```

### Admin диагностика
Для панели статуса и логов:
```
ADMIN_TOKEN=your_admin_token
DATA_RETENTION_DAYS=90
RUNS_RETENTION_DAYS=90
LOGS_CLEANUP_DAYS=30
```
Открывайте в браузере:
```
https://your-public-url/admin
```
Токен вводится в интерфейсе и сохраняется локально.

### Maintenance (очистка данных)
Ручной запуск:
```bash
python scripts/cleanup.py
```
Очистка включает: старые посты, историю запусков, старые лог‑файлы, старые эмбеддинги.

Автозапуск (launchd):
```bash
cp scripts/launchd/com.cannibal.maintenance.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cannibal.maintenance.plist
```

### Автозапуск ngrok (опционально)
```bash
cp scripts/launchd/com.cannibal.ngrok.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cannibal.ngrok.plist
```

## Настройки (основные)
- `TARGET_CHANNELS` — список каналов через запятую (username без `@`).
- `DUPLICATE_THRESHOLD` — порог похожести (0.85 по умолчанию).
- `PROCESSOR_WORKERS` — число воркеров обработки.
- `PROCESSOR_QUEUE_SIZE` — размер очереди задач.
- `MAX_CHARS` — ограничение длины входного текста.
- `EMBEDDING_MAX_CHARS` — ограничение длины текста для эмбеддингов (по умолчанию 2000).
- `AD_STOP_WORDS` — стоп‑слова для рекламы.
- `STYLE_PROFILE_POSTS` — число постов для авто‑профиля стиля (по умолчанию 80).
- `AUTO_STYLE_CHANNEL` — канал, чей стиль использовать в автоматическом `main`‑режиме.
- `EDITORIAL_TOPIC_WINDOW_DAYS` — окно обзора источников для Mini App (по умолчанию 30 дней).
- `EDITORIAL_SOURCE_SYNC_LIMIT` — сколько последних сообщений читать с каждого источника.
- `EDITORIAL_TOPIC_MAX_POSTS` — максимум постов, которые попадут в тематический отчёт.
- `EDITORIAL_TOPIC_MAX_CATEGORIES` — максимум AI‑категорий в одном отчёте.
- `EDITORIAL_TOPIC_BATCH_SIZE` — размер batch для multi‑label категоризации постов.
- `STYLE_PROFILE_EXAMPLES` — сколько живых примеров постов добавлять в промпт (по умолчанию 4).
- `STYLE_PROFILE_EXAMPLE_LIMIT` — сколько последних постов просматривать для примеров (по умолчанию 200).
- `STYLE_PROFILE_EXAMPLE_MIN_CHARS` — минимальная длина примера (по умолчанию 40).
- `STYLE_PROFILE_EXAMPLE_MAX_CHARS` — максимальная длина примера (по умолчанию 400).
- `REWRITE_MODE` — режим переписывания (`balanced` или `aggressive`).
- `REWRITE_TEMPERATURE` — температура рерайта (чем выше, тем сильнее перефразирование, но выше риск искажений).
- `LOG_FILE` — путь к лог‑файлу (если задан, логи пишутся и в файл).
- `LOG_ROTATION` — ротация логов (например `10 MB`).
- `LOG_RETENTION` — сколько хранить логи (например `14 days`).
- `TELEGRAM_RETRY_ATTEMPTS` — число повторов при ошибках Telegram (по умолчанию 3).
- `TELEGRAM_RETRY_BASE_DELAY` — базовая задержка между повторами (по умолчанию 1.0).
- `TELEGRAM_FLOOD_SLEEP_MAX` — максимум ожидания FloodWait (по умолчанию 120 секунд).
- `ENFORCE_ALLOWED_USERS` — требовать `BOT_ALLOWED_USERS` (по умолчанию `true`).
- `CLOUDFLARED_TUNNEL_TOKEN` — токен Cloudflare Tunnel для стабильного URL.
- `OUTPUT_PATH` — путь к файлу, куда записываются переписанные посты.
- `ALERT_BOT_TOKEN` — токен бота для оповещений (если не указан, используется `BOT_TOKEN`).
- `ALERT_CHAT_ID` — чат/пользователь для оповещений (user_id или chat_id).

## Примеры стиля
Можно переопределить примеры стиля через `.env`:
```
STYLE_EXAMPLES_RU=Пример 1||Пример 2||Пример 3
STYLE_EXAMPLES_EN=Example 1||Example 2||Example 3
```
Разделитель — `||`.

## Сбор корпуса (backfill)
Чтобы собрать 60–100 последних постов и улучшить стиль, запусти:
```bash
python -m cannibal_core.backfill --limit 100 --channels channel_one,channel_two
```

Опции:
- `--limit` — сколько последних постов брать на канал.
- `--channels` — список каналов через запятую (перезапишет `TARGET_CHANNELS`).
- `--no-embeddings` — сохранить только SQLite, без эмбеддингов (не подходит для семантического подбора).

## Авто‑профиль стиля
При старте сервис автоматически строит “профиль стиля” по последним постам канала и
передаёт его в промпт. Это повышает близость к “почерку автора”.

Полезно:
- для production‑сценария задайте `AUTO_STYLE_CHANNEL`, чтобы авто‑режим всегда
  писал в едином Tone of Voice;
- сначала выполнить backfill на 60–100 постов;
- при обновлении корпуса перезапустить сервис.

## Сессии Telethon
Рекомендуется использовать разные session‑файлы для разных режимов, чтобы избежать
ошибки `database is locked` при параллельном запуске:
```
TELETHON_SESSION=cannibal_userbot
BOT_USER_SESSION=cannibal_bot_userbot
WEBAPP_USER_SESSION=cannibal_webapp_userbot
BOT_SESSION=cannibal_bot
```

## Резервные копии
Скрипт бэкапа базы и векторов:
```bash
bash scripts/backup.sh
```

## Миграции БД (Alembic)
Приложение при старте само доводит схему до `head` через Alembic.

Ручной запуск:
```bash
python -m cannibal_core.migrate
```

Явный вызов Alembic тоже поддерживается:
```bash
alembic upgrade head
```
Для полной переинициализации сделайте бэкап и удалите `cannibal.db`, затем выполните
`python -m cannibal_core.migrate` или `alembic upgrade head`.

Создание новой миграции после изменения моделей:
```bash
alembic revision --autogenerate -m "your message"
```

## Health check
Мини‑проверка конфигурации и доступности LLM‑провайдера:
```bash
python scripts/health_check.py
```

## E2E сценарий (быстрый прогон)
1) Backfill для стиля:
```bash
python -m cannibal_core.backfill --limit 100 --channels @your_channel
```
2) Запуск основного сервиса:
```bash
python -m cannibal_core.main
```
3) Запуск бота и WebApp:
```bash
python -m cannibal_core.bot
python -m cannibal_core.webapp_server
```
4) В боте: `/start`, при необходимости переслать пост из нужного канала.
5) В WebApp: указать канал стиля и источники → `Обновить темы`.
6) Выбрать тему → отметить посты → `Сгенерировать`.

## CI/CD
### CI
GitHub Actions запускает тесты (`pytest`) на каждый push/PR.

### CD (опционально)
Добавьте секреты в GitHub:
```
DEPLOY_HOST=your.server
DEPLOY_USER=your_user
DEPLOY_KEY=-----BEGIN OPENSSH PRIVATE KEY-----
DEPLOY_PATH=/path/to/cannibal
DEPLOY_PORT=22
DEPLOY_COMMAND=launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cannibal.main.plist; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cannibal.main.plist
```
`DEPLOY_COMMAND` можно заменить на ваши команды перезапуска (systemctl/pm2/launchctl).

## Автозапуск (macOS)
Шаблоны launchd лежат в `scripts/launchd/`.
Перед использованием замените пути на свой каталог.
```
cp scripts/launchd/com.cannibal.main.plist ~/Library/LaunchAgents/
cp scripts/launchd/com.cannibal.bot.plist ~/Library/LaunchAgents/
cp scripts/launchd/com.cannibal.webapp.plist ~/Library/LaunchAgents/
cp scripts/launchd/com.cannibal.cloudflared.plist ~/Library/LaunchAgents/

launchctl load ~/Library/LaunchAgents/com.cannibal.main.plist
launchctl load ~/Library/LaunchAgents/com.cannibal.bot.plist
launchctl load ~/Library/LaunchAgents/com.cannibal.webapp.plist
launchctl load ~/Library/LaunchAgents/com.cannibal.cloudflared.plist
```

## Тесты
```bash
source .venv/bin/activate
pytest -q
```

## Файлы
- `cannibal_core/config.py` — настройки
- `cannibal_core/listener.py` — Telethon listener
- `cannibal_core/deduplicator.py` — дедупликация
- `cannibal_core/brain.py` — рерайт
- `cannibal_core/processor.py` — очередь и оркестрация
- `cannibal_core/database.py` — SQLite модели
- `cannibal_core/vector_store.py` — ChromaDB
- `cannibal_core/backfill.py` — сбор корпуса постов
- `cannibal_core/style_profile.py` — авто‑профиль стиля

## Примечания
- База SQLite и Chroma хранятся локально.
- При изменении схемы БД проще всего удалить старый файл `cannibal.db`.
- Для продакшена стоит добавить мониторинг, лимиты и интеграцию с publish‑каналом.
