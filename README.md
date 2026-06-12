# Проектный менеджер (RAG + llama.cpp)

Production-oriented web application: AI-ассистент для студентов по управлению проектами, методологиям и инженерным практикам.  
Стек: React SPA + FastAPI API + SSE realtime + Redis queue + PostgreSQL state + Qdrant RAG + llama.cpp/llama-server.

## 1) Архитектура по слоям

- `frontend` (React + TypeScript SPA)
  - стартовая страница, login, chat, history, sources panel, knowledge base page, admin logs/roles page.
  - streaming ответа через SSE.
- `backend/api` (FastAPI transport layer)
  - REST endpoints (`/api/auth`, `/api/chat`, `/api/knowledge`, `/api/admin`) + SSE endpoint (`/api/chat/stream/{job_id}`).
  - API не содержит бизнес-логики генерации: только валидация, auth, enqueue.
- `backend/services` (AI orchestration layer)
  - очередь, state machine job-ов, сбор контекста, summary-compression, retrieval policy, prompt assembly, вызов llama-server.
- `backend/persistence` (data/state layer)
  - PostgreSQL: users, conversations, messages, summaries, jobs, logs, knowledge metadata.
  - Redis: realtime pub/sub + lock per `(user_id, conversation_id)`.
  - Qdrant: векторный индекс chunk-ов знаний.
- `backend/infrastructure`
  - docker-compose orchestration, env-driven config, structured JSON logging.

Ключевой принцип: **transport layer отделен от AI-логики**. API принимает сообщения и ставит jobs в очередь, worker обрабатывает их автономно.

## 2) Схема БД и хранилищ

PostgreSQL таблицы:

- `users`
  - `id`, `login` (unique), `password_hash`, `role` (`admin|user`), `created_at`.
- `conversations`
  - `id`, `user_id`, `title`, `summary_text`, `summary_tokens`, `created_at`, `updated_at`.
- `messages`
  - `id`, `conversation_id`, `user_id`, `role`, `content`, `attachments` (JSON), `token_count`, `summarized`, `created_at`.
- `generation_jobs`
  - `id`, `user_id`, `conversation_id`, `request_message_id`, `response_message_id`, `status`, `error_message`, `trace_id`, timestamps.
  - индекс `ix_generation_jobs_scope_status (user_id, conversation_id, status)`.
- `knowledge_documents`
  - `id`, `title`, `source_type`, `source_uri`, `checksum` (unique), `metadata_json`, `created_at`.
- `knowledge_chunks`
  - `id`, `document_id`, `chunk_index`, `text`, `metadata_json`, `qdrant_point_id` (unique), `created_at`.
- `pipeline_logs`
  - `id`, `trace_id`, `user_id`, `conversation_id`, `message_id`, `payload` (JSON), `created_at`.
- `model_capabilities`
  - `model_hf` (unique), `multimodal` (источник истины для поддержки изображений).

Qdrant:

- collection `knowledge_chunks`
  - vector: embedding документа/chunk
  - payload: `document_id`, `chunk_index`, `text`, `metadata`

Redis:

- pub/sub channel `job:{job_id}` для realtime статусов/streaming дельт.
- lock key `lock:{user_id}:{conversation_id}` для сериализации выполнения внутри диалога.

## 3) UX и страницы web-приложения

- `/` Стартовая страница
  - что делает ассистент, где factual режим через базу знаний.
- `/login`
  - JWT авторизация и регистрация обычного пользователя.
  - первый админ создается автоматически из `ADMIN_LOGIN` / `ADMIN_PASS`.
- `/chat`
  - список диалогов, сообщения, composer, file input для изображений (только если `MODEL_MULTIMODAL=True` и модель отмечена multimodal), streaming ответа.
  - автоназвание диалога: новый чат создаётся как `Новый диалог`; после **первого успешного ответа** worker переименовывает его по первому сообщению пользователя (без вызова LLM — эвристика: убрать «расскажи про…», взять до 6 слов, максимум 60 символов; только картинка без текста → `Изображение`).
  - статусы: `queued / thinking / retrieving / responding / done / error`.
  - thinking UX: показывается `"Рассуждаю, подождите..."`, chain-of-thought пользователю не показывается.
  - панель источников + явный режим: `На основе базы знаний` / `Общий ответ модели`.
- `/knowledge`
  - загрузка документов в KB + список документов.
- `/admin`
  - просмотр pipeline-логов (только admin).
  - назначение другого пользователя админом (admin-only).

Мультипользовательская изоляция:

- все запросы и выборки в API и worker scoped по `user_id + conversation_id`;
- контексты разных пользователей и диалогов не пересекаются.

## 4) Алгоритм очередей и работы с контекстом

### 4.1 Очередь и конкурентность

- При новом сообщении API:
  1. сохраняет `messages.role=user`,
  2. считает активные jobs в этом scope `(user_id, conversation_id)` со статусами `queued|thinking|retrieving|responding`,
  3. применяет лимит `MAX_QUEUE_SIZE` (по умолчанию `3`),
  4. если лимит превышен: `429` + понятное сообщение,
  5. иначе создает `generation_jobs.status=queued`.
- Worker:
  - выбирает старейший queued job;
  - берет redis-lock на `(user_id, conversation_id)`; при неудаче возвращает job в `queued`;
  - публикует статусы через Redis/SSE.
- Восстановление после сбоя:
  - при старте worker все `thinking|retrieving|responding` переводятся обратно в `queued`.
  - очередь и история не теряются, так как источник истины в PostgreSQL.

### 4.2 Context window

В prompt попадает:

1. системная инструкция;
2. `summary_text` диалога;
3. последние `RAW_MESSAGES_SIZE` raw сообщений;
4. дополнительно `MESSAGES_SUMMARY_SIZE - 1` несуммаризированных bridge-сообщений;
5. RAG fragments (если retrieval включен);
6. текущий вопрос.

Параметры:

- `RAW_MESSAGES_SIZE` default `10`, валидируется `>=1`;
- `MESSAGES_SUMMARY_SIZE` default `5`; если `<1`, summary отключен;
- `SUMMARY_TOKENS_SIZE` default `12000`.

Проверка env-ограничений выполняется один раз при старте приложения (`pydantic Settings`).

### 4.3 Summary compression

Триггер:

- если общее число сообщений > `RAW_MESSAGES_SIZE + MESSAGES_SUMMARY_SIZE - 1`.

Алгоритм:

1. выбрать старые сообщения за пределами хвоста (`RAW + bridge`);
2. брать только `summarized=False`;
3. сгенерировать incremental summary с учетом текущего `summary_text`;
4. merge старого summary + нового;
5. посчитать токены summary;
6. если токенов > `SUMMARY_TOKENS_SIZE`, выполнить повторное сжатие summary;
7. сохранить `conversation.summary_text`, `summary_tokens`;
8. пометить обработанные сообщения `summarized=True`.

Устойчивость:

- после рестарта состояние summary и флаги `summarized` остаются в БД;
- контекст восстанавливается детерминированно.

### 4.4 Отдельная модель для summary (опционально)

По умолчанию summary генерируется тем же `llama-server`, что и основной чат (`LLAMA_HOST` / `LLAMA_PORT`), с моделью `SUMMARY_MODEL_HF` или `MODEL_HF`.

Если включить `USE_DEDICATED_SUMMARY_MODEL=True`, worker отправляет запросы на сжатие контекста на отдельный `llama-server` (`SUMMARY_LLAMA_HOST` / `SUMMARY_LLAMA_PORT`). Рекомендуемая модель — более лёгкая `unsloth/Qwen3.5-4B-GGUF:UD-Q4_K_XL`, чтобы не отнимать VRAM у основной 9B-модели.

В `docker-compose` summary вынесен в **отдельные profiles** (чтобы CPU- и CUDA-контейнеры не боролись за один порт):

| Стек | Короткий profile | По отдельности |
|---|---|---|
| GPU + summary | `llama-gpu-full` | `llama-cuda` + `llama-summary-cuda` |
| CPU + summary | `llama-cpu-full` | `llama` + `llama-summary` |
| Только основная GPU | `llama-cuda` | — |

```bash
# GPU: основная 9B + отдельная 4B для summary (одна команда)
USE_DEDICATED_SUMMARY_MODEL=True
docker compose --profile llama-gpu-full up --build
```

Чтобы не писать `--profile` каждый раз, добавьте в `.env`:

```env
COMPOSE_PROFILES=llama-gpu-full
```

После этого достаточно:

```bash
docker compose up --build
```

```bash
# CPU + summary
docker compose --profile llama-cpu-full up --build
```

Не смешивайте `llama-summary` (CPU) и `llama-summary-cuda` (GPU) — оба слушают `SUMMARY_LLAMA_PORT` (по умолчанию `8767`).

Без profile summary отдельный контейнер не стартует — оставьте `USE_DEDICATED_SUMMARY_MODEL=False`.

## 5) RAG-дизайн

### 5.1 Схема данных RAG

- `knowledge_documents`: мета документа и checksum для dedupe.
- `knowledge_chunks`: chunk тексты, metadata, привязка к qdrant point id.
- Qdrant payload дублирует ключевые метаданные для retrieval без join.

### 5.2 Chunking strategy

- скользящее окно по символам:
  - `chunk_size=800`,
  - `overlap=120`.
- Это простой baseline; легко заменить на sentence/token chunker.

### 5.3 Metadata/payload strategy

Рекомендуемые поля:

- `title`, `domain`, `source_uri`, `doc_type`, `language`, `version`, `tags`.

Сейчас минимум:

- `title` + пользовательский `metadata_json`.

### 5.4 Индексация

1. upload документа через `/api/knowledge/upload`,
2. checksum dedupe,
3. chunking,
4. embedding (`EMBEDDING_MODEL`; в Docker по умолчанию `hashing-384`, без PyTorch/CUDA),
5. upsert points в Qdrant,
6. запись `knowledge_chunks` в PostgreSQL.

### 5.5 Когда retrieval запускать

- Retrieval policy based on lexical markers (`гост`, `iso`, `scrum`, `kanban`, `devops`, `стандарт`, etc.).
- Если вопрос conversational/навигационный -> без RAG.
- Если factual question -> retrieval `top_k=5` и включение retrieval-aware prompt.

### 5.6 Ранжирование и подмешивание

- Qdrant cosine similarity top-k.
- В prompt вставляются chunks с `document_id`, `chunk_id`, `score`.
- В UI показываются использованные источники из фактических retrieval_results.
- Ассистент не генерирует выдуманные ссылки: источники берутся только из retrieval payload.

Текущий Docker-friendly embedding backend `hashing-384` использует детерминированный
нормализованный hash-vector. Он нужен, чтобы проверить весь RAG pipeline без
скачивания тяжелых CUDA/PyTorch wheel-ов. Для более качественного semantic search
его можно заменить отдельным embedding-сервисом или transformer backend-ом.

## 6) Промпты

В `backend/app/services/prompt_templates.py`:

- `MAIN_ASSISTANT_PROMPT`
- `RETRIEVAL_AWARE_PROMPT`
- `SUMMARIZATION_PROMPT`
- `OPTIONAL_MULTIMODAL_PROMPT`

Режимы:

- обычный ответ;
- retrieval-aware factual response;
- summarization;
- optional multimodal.

Безопасность:

- chain-of-thought не показывается;
- при нехватке данных модель должна честно сказать о недостаточности KB.

## 7) Конфигурация (.env)

Обязательные env:

- `MODEL_HF`
- `MODEL_CONTEXT_SIZE`
- `ADMIN_LOGIN`
- `ADMIN_PASS`
- `LLAMA_HOST`
- `LLAMA_PORT`
- `LLAMA_IMAGE`
- `MODEL_MULTIMODAL`
- `MAX_QUEUE_SIZE`
- `RAW_MESSAGES_SIZE`
- `MESSAGES_SUMMARY_SIZE`
- `SUMMARY_TOKENS_SIZE`
- `SUMMARY_MODEL_HF`
- `SUMMARY_MODEL_CONTEXT_SIZE`
- `USE_DEDICATED_SUMMARY_MODEL`
- `SUMMARY_LLAMA_HOST`
- `SUMMARY_LLAMA_PORT`
- `DATABASE_URL`
- `REDIS_URL`
- `QDRANT_URL`
- `EMBEDDING_MODEL`
- `LOG_LEVEL`

Дополнительно:

- `JWT_SECRET`

Файлы:

- `.env` исключен из git;
- `.env.example` содержит пример значений.

## 8) llama.cpp / llama-server

Предпочтительный запуск через `llama-server`:

```bash
llama-server \
  -hf unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL \
  -c 32768 \
  --host 0.0.0.0 \
  --port 8765
```

Варианты:

- внешний локальный llama.cpp (`LLAMA_HOST` указывает на host);
- контейнер `llama` в `docker-compose` (profile `llama`), если локально не установлен.
- образ llama.cpp задается через `LLAMA_IMAGE`; по умолчанию используется CPU-образ `ghcr.io/ggml-org/llama.cpp:server`.
- `LLAMA_PLATFORM=linux/amd64` фиксирует архитектуру контейнера и помогает избежать случайного запуска через эмуляцию.
- `LLAMA_N_GPU_LAYERS`, `LLAMA_THREADS`, `LLAMA_PARALLEL` управляют скоростью/параллельностью llama-server.
- `LLAMA_EXTRA_ARGS` позволяет передать дополнительные параметры, например `--cache-type-k q8_0 --cache-type-v q8_0`.
- Flash Attention намеренно не включается: на разных сборках llama.cpp этот параметр ведет себя нестабильно и требует явного значения `on|off|auto`.

Для NVIDIA GPU используйте отдельный compose profile:

```bash
docker compose --profile llama-cuda up --build
```

При этом `llama-cuda` получает сетевой alias `llama`, поэтому `LLAMA_HOST=llama` не меняется. На хосте должен быть установлен NVIDIA Container Toolkit / включена GPU-поддержка Docker Desktop.

Модель и cache скачивания сохраняются в примонтированной папке `/models`.
Путь на хосте задается переменной:

```env
LLAMA_MODELS_DIR=${LOCALAPPDATA}/llama.cpp
```

На Windows это обычно:

```text
C:\Users\<user>\AppData\Local\llama.cpp
```

Для контейнеров выставлены `HOME`, `HF_HOME`, `HUGGINGFACE_HUB_CACHE`, `XDG_CACHE_HOME` и `LLAMA_CACHE` внутрь `/models`, а `/root/.cache` дополнительно смонтирован в ту же папку. Поэтому пересборка `api/worker/frontend` не должна заново скачивать модель. Повторное скачивание возможно только если удалить эту папку, выполнить `docker compose down -v` для томов, сменить `MODEL_HF` или если сам `llama.cpp` не нашел совместимый cache.

CPU fallback:

```bash
docker compose --profile llama up --build
```

Для локального запуска по умолчанию используется `MODEL_CONTEXT_SIZE=32768`. Окно `128000` для 9B-модели на 16 GB VRAM часто не помещается из-за KV-cache и может не загрузиться вообще.

Пример с CPU-контейнерной моделью:

```bash
docker compose --profile llama up --build
```

Без profile llama:

```bash
docker compose up --build
```

Тогда API ожидает уже доступный внешний `llama-server`.

### 8.1 Замена моделей

Модели задаются через `.env` и подхватываются `llama-server` при старте контейнера. Пересборка `api` / `worker` / `frontend` для смены модели не нужна — достаточно изменить env и перезапустить соответствующие контейнеры llama.

| Переменная | Назначение |
|---|---|
| `MODEL_HF` | Основная модель чата (контейнеры `llama` / `llama-cuda`) |
| `MODEL_CONTEXT_SIZE` | Размер контекста основной модели (`-c`) |
| `SUMMARY_MODEL_HF` | Модель для summary (контейнеры `llama-summary` / `llama-summary-cuda` или та же, что и чат, если флаг выключен) |
| `SUMMARY_MODEL_CONTEXT_SIZE` | Размер контекста summary-модели |
| `USE_DEDICATED_SUMMARY_MODEL` | `True` — summary идёт на отдельный llama-server; `False` — на основной |

Пример: основной чат на 9B, summary на 4B:

```env
MODEL_HF=unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL
MODEL_CONTEXT_SIZE=32768
USE_DEDICATED_SUMMARY_MODEL=True
SUMMARY_MODEL_HF=unsloth/Qwen3.5-4B-GGUF:UD-Q4_K_XL
SUMMARY_MODEL_CONTEXT_SIZE=16384
SUMMARY_LLAMA_HOST=llama-summary
SUMMARY_LLAMA_PORT=8767
```

После правки `.env`:

```bash
docker compose --profile llama-gpu-full up -d
docker compose restart llama-cuda llama-summary-cuda
```

Первый запуск с новым `MODEL_HF` / `SUMMARY_MODEL_HF` скачает GGUF в `LLAMA_MODELS_DIR` (общий cache для обоих контейнеров). Смена квантования или репозитория Hugging Face считается новой моделью.

Замена через docker compose напрямую: в `docker-compose.yml` команда контейнера уже использует `${MODEL_HF}` и `${SUMMARY_MODEL_HF}` из `.env`. Можно также переопределить переменные в shell без правки файла:

```bash
MODEL_HF=unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_M docker compose --profile llama-cuda up -d llama-cuda
```

Для внешнего (не compose) `llama-server` укажите `-hf ...` при ручном запуске и выставьте `LLAMA_HOST` / `LLAMA_PORT` (и при dedicated summary — `SUMMARY_LLAMA_HOST` / `SUMMARY_LLAMA_PORT`) в `.env`.

## 9) Запуск

1. Скопировать env:

```bash
cp .env.example .env
```

2. Проверить значения `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `LLAMA_HOST/PORT`.

3. (Опционально) Проверить, что порты свободны:

```powershell
.\scripts\check_ports.ps1
```

Или вручную на Windows:

```powershell
netstat -ano | findstr ":8766"
netstat -ano | findstr ":8767"
docker compose ps
```

Если порт занят старым контейнером: `docker compose stop llama-summary llama-summary-cuda` или смените `SUMMARY_LLAMA_PORT` в `.env`.

4. Запустить:

```bash
docker compose up --build
```

5. Открыть:

- frontend: `http://localhost:5173`
- api docs: `http://localhost:8000/docs`

6. При необходимости загрузить стартовую базу знаний:

```bash
python scripts/seed_knowledge_base.py
```

Скрипт логинится под `ADMIN_LOGIN` / `ADMIN_PASS` и индексирует Markdown-файлы из
`knowledge_seed/` через публичный API `/api/knowledge/upload`.

Обычные пользователи могут зарегистрироваться на странице `/login`. Админ может
выдать роль администратора на странице `/admin`.

## 10) Логирование и трассировка

Формат JSON (structured logs), включая:

- `trace_id`
- `user_id`
- `conversation_id`
- `message_id`
- `inbound`
- `context_window`
- `compression`
- `retrieval`
- `llm_call`
- `performance`
- `queue`

Как искать проблемы:

- фильтр по `trace_id` через stdout лог контейнера `api`/`worker`;
- корреляция по `conversation_id` для конфликтов контекста;
- по `queue.size`/`queue.position` находить перегруз;
- по `llm_call.time_to_first_token_ms` смотреть задержку до первого токена;
- по `llm_call.tokens_per_second_after_first` смотреть скорость генерации после первого токена;
- по `performance.generation_latency_ms` смотреть общее время LLM streaming-вызова;
- по `performance.total_from_question_received_ms` смотреть время от поступления вопроса до завершения генерации;
- по `retrieval.latency_ms` / `performance.retrieval_latency_ms` смотреть время поиска по векторной базе;
- `retrieval.used=false` при factual вопросе — индикатор tuning policy/KB.

## 11) Тесты

Backend тесты (`pytest` + coverage threshold 40%):

- queue policy,
- context recovery,
- summary policy,
- rag policy,
- multimodal policy,
- llama-server stream parser,
- token estimator,
- API smoke happy path.

Запуск:

```bash
cd backend
pytest
```

## 12) План директорий проекта

```text
RAGAPP/
  frontend/
    src/
      pages/
      api.ts
      App.tsx
  backend/
    app/
      api/
      services/
      models.py
      db.py
      config.py
      worker.py
    tests/
  knowledge_seed/
    scrum.md
    kanban.md
    devops.md
    project_documentation.md
  scripts/
    seed_knowledge_base.py
  docker-compose.yml
  .env.example
  .gitignore
  README.md
```

## 13) Масштабирование и отказоустойчивость

- Горизонтально масштабировать `api` (stateless transport).
- Масштабировать `worker` несколькими инстансами: redis-lock не даст одновременно обрабатывать один `(user,conversation)` scope.
- PostgreSQL/Redis/Qdrant вынесены в отдельные сервисы и имеют volume-персистентность.
- Контекст и jobs восстанавливаются после рестартов через БД.

## 14) Ограничения текущей версии

- Retrieval policy сейчас эвристическая (keyword-based), без ML-классификатора intent.
- Embeddings по умолчанию `hashing-384`: это легкий backend для локального запуска, не полноценная transformer-семантика.
- Chunking baseline по символам; токен-ориентированная нарезка может повысить качество.
- Нет отдельного observability stack (Prometheus/Grafana/OTel), только structured logs.
- Нет фоновых миграций Alembic; используется auto create tables при старте.
- Встроенный upload принимает текстовые документы; PDF/DOCX можно добавить отдельным parser-слоем перед `IngestionService`.
- Контейнер `llama` включается профилем `--profile llama`; без него нужен внешний `llama-server` на `LLAMA_HOST:LLAMA_PORT`.

## 15) Тестовая стартовая база знаний

Минимальный seed лежит в `knowledge_seed/`:

- `scrum.md` - роли, события и артефакты Scrum;
- `kanban.md` - поток работ и WIP-limits;
- `devops.md` - CI/CD и базовые DevOps-практики;
- `project_documentation.md` - минимальный набор проектной документации.

Далее можно расширять через upload API пакетно (books, ГОСТ/методички, internal standards).
