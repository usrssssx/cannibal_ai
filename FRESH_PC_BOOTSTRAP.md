# Fresh PC Bootstrap

Инструкция для развёртывания `cannibal_ai` на новом ПК, где локально будет крутиться `llama.cpp`.

Если открываешь этот файл в Codex на новой машине, можно просто написать:

```text
Открой FRESH_PC_BOOTSTRAP.md и выполни его как runbook. Ничего не пропускай. Если упрёшься в отсутствующие зависимости или неверный путь к модели, остановись и кратко перечисли, что именно нужно от меня.
```

## 1. Что должно быть на новом ПК

- `git`
- `python3` 3.11+
- доступ к Telegram-аккаунту, который будет использоваться как userbot
- локально установленный `llama.cpp` server (`llama-server`)
- `.gguf` модель для генерации
- модель/режим embeddings на том же сервере, если нужен полный workflow

## 2. Что перенести со старой машины

Обязательно:

- папку проекта `cannibal_ai`
- актуальный `.env` или заполнить новый по `.env.example`

Если хотите сохранить состояние:

- `cannibal.db`
- папку `chroma/`
- папку `images/`
- Telethon session-файлы: `*.session*`

Если хотите чистый старт, `cannibal.db`, `chroma/`, `images/` и session-файлы можно не переносить.

## 3. Размещение проекта

Пример:

```bash
mkdir -p ~/work
cd ~/work
git clone <repo-url> cannibal_ai
cd cannibal_ai
```

Если переносите папкой, просто положите проект в удобный путь и зайдите в него:

```bash
cd /path/to/cannibal_ai
```

## 4. Python-окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 5. Конфиг `.env`

Если `.env` не переносили:

```bash
cp .env.example .env
```

Минимальный рабочий шаблон под `llama.cpp`:

```env
TELETHON_API_ID=...
TELETHON_API_HASH=...

BOT_TOKEN=...
BOT_ALLOWED_USERS=123456789
ENFORCE_ALLOWED_USERS=true

BOT_SESSION=cannibal_bot
BOT_USER_SESSION=cannibal_bot_userbot
WEBAPP_USER_SESSION=cannibal_webapp_userbot
TELETHON_SESSION=cannibal_userbot

WEBAPP_HOST=127.0.0.1
WEBAPP_PORT=8000
WEBAPP_URL=https://your-public-https-url
WEBAPP_DUPLICATE_TO_CHAT=true

LLM_PROVIDER=llama_cpp
LLAMA_CPP_BASE_URL=http://127.0.0.1:8080
LLAMA_CPP_MODEL=local-model
LLAMA_CPP_EMBEDDING_MODEL=local-model

IMAGE_ENABLED=false
```

Если нужно временно открыть доступ без whitelist:

```env
ENFORCE_ALLOWED_USERS=false
```

После первого успешного запуска лучше вернуть `true`.

## 6. Поднять `llama.cpp`

Проект ожидает OpenAI-compatible API и рабочий chat endpoint.

Базовый пример:

```bash
llama-server -m /absolute/path/to/model.gguf --port 8080 --embedding
```

Если нужен больший контекст:

```bash
llama-server -m /absolute/path/to/model.gguf --port 8080 --embedding -c 8192
```

Важно:

- `LLAMA_CPP_BASE_URL` в `.env` должен совпадать с адресом сервера
- server должен отвечать на chat requests
- для полного editorial workflow нужен embedding endpoint

Если embeddings не работают, тематическая сводка и часть пайплайна будут деградировать или падать.

## 7. Мини-проверка окружения

```bash
source .venv/bin/activate
python scripts/health_check.py
```

Если health check не проходит, сначала чинить это, а не запускать бот/WebApp.

## 8. Миграции БД

Если база новая:

```bash
source .venv/bin/activate
python -m cannibal_core.migrate
```

Если переносили старую базу, этот шаг всё равно безопасно прогоняет её до `head`.

## 9. Запуск сервисов

Для нового editorial workflow нужны как минимум 2 процесса.

Окно 1:

```bash
cd /path/to/cannibal_ai
source .venv/bin/activate
python -m cannibal_core.bot
```

Окно 2:

```bash
cd /path/to/cannibal_ai
source .venv/bin/activate
python -m cannibal_core.webapp_server
```

Опционально, если нужен авто-monitoring pipeline:

Окно 3:

```bash
cd /path/to/cannibal_ai
source .venv/bin/activate
python -m cannibal_core.main
```

## 10. Первый запуск Telethon

На первом старте Telethon попросит:

- номер телефона
- код из Telegram
- возможно, 2FA пароль

Это нормально. После успешного логина появятся session-файлы.

## 11. Публичный URL для Mini App

`WEBAPP_URL` должен быть публичным `https`-адресом.

Самый удобный вариант: Cloudflare Tunnel.

Пример:

```bash
cloudflared tunnel run --token $CLOUDFLARED_TUNNEL_TOKEN
```

После этого:

- взять внешний URL
- прописать его в `WEBAPP_URL`
- перезапустить `cannibal_core.bot` и `cannibal_core.webapp_server`

Временная альтернатива:

```bash
ngrok http 8000
```

## 12. Smoke test после подъёма

1. Открыть чат с ботом.
2. Выполнить `/start`.
3. Открыть Mini App.
4. Указать свой канал как `style`.
5. Добавить 1-2 источника.
6. Нажать `Обновить темы`.
7. Открыть любую тему.
8. Выбрать посты.
9. Нажать `Сгенерировать`.
10. Проверить, что результат пришёл и в Mini App, и в чат с ботом.

## 13. Если нужно перенести состояние

Проверьте после копирования:

```bash
ls -lah *.session*
ls -lah cannibal.db
ls -lah chroma
```

Если session-файлы не перенесены, Telethon залогинится заново.

## 14. Типовые проблемы

### `BOT_ALLOWED_USERS` / `User is not allowed`

Либо:

- добавить свой `user_id` в `BOT_ALLOWED_USERS`

Либо временно:

- поставить `ENFORCE_ALLOWED_USERS=false`

### `llama.cpp health check failed`

Проверить:

- жив ли `llama-server`
- правильный ли `LLAMA_CPP_BASE_URL`
- доступен ли порт `8080`

### Mini App не открывается

Проверить:

- `WEBAPP_URL` задан
- URL публичный и на `https`
- `webapp_server` действительно запущен

### Бот пишет, но темы не строятся

Проверить:

- может ли userbot читать указанные каналы
- работает ли embeddings endpoint у `llama.cpp`
- нет ли ошибок в логах `webapp`/`bot`

## 15. Команды быстрой диагностики

```bash
source .venv/bin/activate
python -m py_compile cannibal_core/*.py tests/*.py
pytest -q
```

Если нужен только быстрый smoke импортов:

```bash
source .venv/bin/activate
python scripts/health_check.py
```

## 16. Что попросить Codex сделать на новой машине

Рекомендуемый промпт:

```text
Открой FRESH_PC_BOOTSTRAP.md и выполни его как runbook. Затем проверь .env, подними llama.cpp, bot и webapp, пройди smoke test до шага генерации. Если что-то не работает, сначала исправь конфиг и локальные runtime-проблемы, потом продолжай.
```

## 17. Когда всё поднято

Если smoke test прошёл, следующий шаг:

- настроить постоянный запуск процессов
- подключить Cloudflare Tunnel/systemd/launchd
- прогнать реальный editorial сценарий на ваших боевых каналах
