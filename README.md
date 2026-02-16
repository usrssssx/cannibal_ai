# cannibal_ai
Автоматический мониторинг Telegram‑каналов, дедупликация новостей и рерайт с сохранением Tone of Voice.

## Что делает
- Слушает новые посты в Telegram‑каналах через Telethon (userbot).
- Фильтрует рекламу по стоп‑словам.
- Дедуплицирует посты по эмбеддингам (ChromaDB).
- Переписывает уникальные посты в стиле админа через LLM.
- Сохраняет сырой текст в SQLite.
- Записывает итоговый текст в файл `OUTPUT_PATH`.

## Требования
- Python 3.11+
- Telethon userbot (нужны api_id и api_hash)
- OpenAI или Ollama (по конфигу)

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
```

### Ollama (по умолчанию)
```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b-instruct
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### OpenAI
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
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

## Настройки (основные)
- `TARGET_CHANNELS` — список каналов через запятую (username без `@`).
- `DUPLICATE_THRESHOLD` — порог похожести (0.85 по умолчанию).
- `PROCESSOR_WORKERS` — число воркеров обработки.
- `PROCESSOR_QUEUE_SIZE` — размер очереди задач.
- `MAX_CHARS` — ограничение длины входного текста.
- `AD_STOP_WORDS` — стоп‑слова для рекламы.
- `STYLE_PROFILE_POSTS` — число постов для авто‑профиля стиля (по умолчанию 80).
- `OUTPUT_PATH` — путь к файлу, куда записываются переписанные посты.

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
- сначала выполнить backfill на 60–100 постов;
- при обновлении корпуса перезапустить сервис.

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
