# News Aggregator

Автоматизированная система сбора, анализа и публикации новостей с использованием AI-агентов.

**Источники новостей:**
- Telegram-каналы (мониторинг через UserBot)
- RSS/Atom ленты (feedparser)
- Web-сайты (requests + BeautifulSoup4)

**Версия:** 4.0.0
**Последнее обновление:** 2026-08-16

---

## 📋 Оглавление

- [Описание](#описание)
- [Архитектура](#архитектура)
- [Быстрый старт (Docker)](#быстрый-старт-docker)
- [Быстрый старт (вручную)](#быстрый-старт-вручную)
- [Конфигурация](#конфигурация)
- [AI Агенты](#ai-агенты)
- [Логика обработки](#логика-обработки)
- [Web админка](#web-админка)
- [Документация](#документация)
- [Тестирование](#тестирование)

---

## Описание

**News Aggregator** — это система для:
- Мониторинга Telegram-каналов в реальном времени
- Автоматической категоризации и оценки срочности новостей (1-5)
- Генерации сводных новостей через AI-агентов (Categorizer → Analyst → Editor → Archivist)
- Векторного поиска похожих событий (ChromaDB + sentence-transformers)
- Публикации в Telegram-каналы
- Парсинга RSS/Atom лент с автопроверкой каждые 5 минут
- Парсинга веб-сайтов через requests + BeautifulSoup4
- Web интерфейса администрирования (FastAPI + 52 endpoint'а)
- Управления подписками и платежами (Telegram Stars)
- 2FA аутентификации (TOTP) для администраторов
- Health check и мониторинга состояния всех компонентов

### Ключевые возможности

| Возможность | Описание |
|------------|----------|
| **Мониторинг** | Отслеживание Telegram-каналов через UserBot (Telethon) |
| **Категоризация** | AI-классификация новостей по категориям и срочности (1-5) |
| **Срочные новости** | Обработка новостей срочностью 4-5 немедленно |
| **Доверенные источники** | Публикация без модерации от проверенных каналов |
| **RSS парсинг** | Парсинг RSS/Atom лент (каждые 5 мин) |
| **Web парсинг** | Парсинг сайтов через requests + bs4 |
| **Векторный поиск** | Поиск похожих событий через ChromaDB (HNSW) |
| **AI-агенты** | 4 агента: Categorizer, Analyst, Editor, Archivist |
| **Подписки** | Платные подписки для пользователей (Telegram Stars) |
| **Прямая генерация** | Генерация новостей админом без источника |
| **2FA** | TOTP-аутентификация для администраторов |
| **Web админка** | FastAPI + JWT — главная панель, консоль, задачи, настройки |
| **Service Manager** | Управление сервисами (старт/стоп/рестарт) через веб-консоль |
| **Health Check** | Проверка здоровья всех компонентов (БД, Ollama, ChromaDB, бот) |
| **Уведомления** | Панель уведомлений о сбоях сервисов |

### Статистика проекта

| Метрика | Значение |
|---------|----------|
| **Строк кода (services)** | ~34 500 |
| **Строк кода (database)** | ~5 100 |
| **Файлов тестов** | 63 |
| **API endpoint'ов** | 52 |
| **Страниц веб-админки** | 7 (главная, консоль, настройки, новости, каналы, пользователи, задачи, RSS, web) |
| **Модулей** | 16 |
| **Репозиториев** | 11 |

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│              (Application — lifecycle, сигналы)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
   ┌───────────────┐ ┌───────────────┐ ┌─────────────────┐
   │ ServiceManager│ │  Web Admin    │ │  AgentTaskQueue │
   │ (lazy start)  │ │  (FastAPI)    │ │  (+ Redis)      │
   └───────┬───────┘ └───────────────┘ └─────────────────┘
           │
    ┌──────┼──────────┬───────────┐
    ▼      ▼          ▼           ▼
┌───────┐ ┌────────┐  ┌─────────┐  ┌────────────┐
│  Bot  │ │ Listener│  │Scheduler│  │ Health     │
│(aiogram│ │(Telethon│  │ (+ RSS) │  │ Check      │
│ )     │ │ )      │  │         │  │            │
└───────┘ └────────┘  └─────────┘  └────────────┘
           │
           ▼
   ┌─────────────────────────────────────────────────┐
   │              NewsOrchestrator                    │
   │         (Strategy pattern + EventBus)            │
   └─────────────────────────────────────────────────┘
           │
    ┌──────┼───────────┬───────────┬────────────────┐
    ▼      ▼           ▼           ▼                ▼
┌───────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────┐
│ Urgent│ │Scheduled│ │ Trusted │ │ Categoriz│ │ Vector │
│News   │ │News     │ │ Source  │ │ ation    │ │ Search │
└───────┘ └─────────┘ └─────────┘ └──────────┘ └────────┘
```

### Стек технологий

| Категория | Технология |
|-----------|-----------|
| **Telegram** | aiogram 3.x, Telethon 1.30+ |
| **Backend** | Python 3.12, FastAPI, uvicorn |
| **Web Admin** | FastAPI + JWT + Tailwind CSS + Jinja2 |
| **ORM** | SQLAlchemy 2.0 + Alembic |
| **Database** | SQLite (dev) / PostgreSQL (prod) |
| **LLM** | Ollama (qwen2.5:7b), OpenAI (GPT-4o-mini), Anthropic (Claude) |
| **Vector DB** | ChromaDB + sentence-transformers (HNSW) |
| **AI Agents** | Categorizer, Analyst, Editor, Archivist |
| **Queue** | Redis + Celery (опционально) |
| **Container** | Docker + Docker Compose |
| **Monitoring** | Prometheus + Grafana + Health Check API |
| **CI/CD** | GitHub Actions |

---

## Быстрый старт (Docker)

### 1. Настройка

```bash
# Копируем .env.example
cp .env.example .env

# Редактируем .env (заполняем TELEGRAM_BOT_TOKEN и др.)
nano .env
```

### 2. Запуск

```bash
# Запускаем все сервисы
docker-compose up -d

# Проверяем статус
docker-compose ps

# Смотрим логи
docker-compose logs -f
```

### 3. Инициализация

```bash
# Применяем миграции
docker-compose exec app alembic upgrade head

# Загружаем модель Ollama
docker-compose exec ollama ollama pull qwen2.5:7b
```

### 4. Доступ

| Сервис | URL | Порт |
|--------|-----|------|
| Основное приложение | http://localhost | 8000 |
| Web админка | http://localhost:8001 | 8001 |
| PostgreSQL | localhost | 5432 |
| ChromaDB | http://localhost:8000 | 8000 |
| Ollama | http://localhost:11434 | 11434 |
| Redis | localhost | 6379 |
| Prometheus | http://localhost:9090 | 9090 |
| Grafana | http://localhost:3000 | 3000 |

### Production

```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## Быстрый старт (вручную)

### Требования
- Python 3.12+
- Ollama (локальный сервер LLM)
- Telegram Bot Token
- Telegram API credentials

### Установка

```bash
cd news_aggregator

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Заполните .env

alembic upgrade head

ollama serve
ollama pull qwen2.5:7b

python main.py
```

### Локальный запуск

После запуска открывается Web Admin панель: `http://localhost:8001`

Сервисы (Bot, Listener, Scheduler) запускаются **лениво** через консоль админки — не автоматически.

---

## Конфигурация

### Переменные окружения

| Переменная | Описание | Обязательно |
|------------|----------|:-----------:|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | ✅ |
| `TELEGRAM_API_ID` | Telegram API ID | ✅ |
| `TELEGRAM_API_HASH` | Telegram API hash | ✅ |
| `TELEGRAM_PHONE_NUMBER` | Номер для Listener Bot | ✅ |
| `ADMIN_ID` | Telegram ID администратора | ✅ |
| `WEB_ADMIN_JWT_SECRET` | JWT секрет для веб-админки | ✅ |
| `ENCRYPTION_KEY` | Ключ шифрования (32+ символа) | ✅ |
| `DATABASE_URL` | PostgreSQL URL (опционально) | — |
| `REDIS_URL` | Redis URL (опционально) | — |
| `LLM_PRIMARY_PROVIDER` | Основной LLM провайдер | — |
| `OLLAMA_HOST` | URL Ollama API | — |
| `OLLAMA_MODEL` | Модель Ollama | — |

### Основные настройки

| Настройка | По умолчанию | Описание |
|-----------|--------------|----------|
| `event_processing_interval_hours` | 48 | Интервал обработки событий |
| `agent_model` | `qwen2.5:7b` | Модель для AI агентов |
| `channel_trust_window_size` | 100 | Окно для расчёта рейтинга канала |
| `payment_provider` | `test` | Платёжный провайдер |
| `categorization_queue_maxlen` | 10 | Макс. размер очереди категоризации |

---

## AI Агенты

| Агент | Задача | Промпт |
|-------|--------|--------|
| **Categorizer** | Первичная классификация, фильтрация рекламы | `prompts/categorizer.txt` |
| **Analyst** | Оценка категории + confidence, тэгирование | `prompts/analyst.txt` |
| **Editor** | Генерация новости в журналистском стиле | `prompts/editor.txt` |
| **Archivist** | Структурирование контекста для векторного поиска | `prompts/archivist.txt` |

### LLM провайдеры

- **Основной:** Ollama (`qwen2.5:7b`)
- **Fallback:** OpenAI (GPT-4o-mini), Anthropic (Claude Sonnet)
- **Circuit Breaker** защищает от каскадных сбоев
- **LLM Cache** кэширует повторяющиеся запросы

---

## Логика обработки

### Срочность 4-5 (срочные)
```
Пост → Categorization → UrgentNewsStrategy
    → Analyst → EventBus → Editor → Archivist → Модерация
```

### Срочность 1-3 (плановые)
```
Пост → Categorization → Analyst (дуэт с Categorizer)
    → ScheduledNewsStrategy → БД (checked_at=false)
    → Scheduler (задачи в БД) → Editor → Archivist → Модерация
```

### Доверенный источник
```
Пост → Categorization → Analyst → TrustedSourceStrategy
    → Публикация → Уведомление подписчикам
```

### RSS и Web парсинг
```
RSS/Web Parser → БД (rss_news / web_news)
    → AI категоризация → Post (checked_at=false)
    → Планировщик → Editor → Archivist → Модерация
```

---

## Web админка

Веб-интерфейс администрирования на FastAPI + Tailwind CSS + Jinja2. Запускается на порту `8001`.

### Страницы

| Страница | URL | Описание |
|----------|-----|----------|
| **Главная** | `/` | Дашборд: статистика, статус сервисов, health check, быстрые действия |
| **Консоль** | `/console` | Управление сервисами (старт/стоп/рестарт), выполнение SQL/Python, логи |
| **Настройки** | `/settings` | Редактирование `.env` переменных, горячее применение |
| **Новости** | `/news` | Список новостей, модерация |
| **Каналы** | `/channels` | Управление каналами-источниками |
| **Пользователи** | `/users` | Список пользователей, подписки |
| **Задачи** | `/tasks` | Управление задачами планировщика |
| **RSS ленты** | `/rss` | Управление RSS источниками |
| **Web парсинг** | `/web` | Управление web источниками |

### API endpoint'ы (52)

| Группа | Endpoint'ы | Описание |
|--------|-----------|----------|
| **Health** | `/health`, `/health/full`, `/health/{component}` | Проверка здоровья компонентов |
| **Сервисы** | `/api/services/status`, `/api/notifications/read` | Статус сервисов, уведомления |
| **Консоль** | `/api/execute`, `/api/python`, `/api/sql`, `/api/logs`, `/api/{service}/start` | Выполнение команд, управление сервисами |
| **Задачи** | `/tasks/*` (12 endpoint'ов) | CRUD задач, планирование |
| **Новости** | `/api/news/recent`, `/api/news/generate` | Последние новости, генерация |
| **Каналы** | `/api/channels`, `/channels` | Управление каналами |
| **Настройки** | `/api/env`, `/api/env/restart` | Чтение/запись настроек |
| **Listener** | `/api/listener/auth/*` (6 endpoint'ов) + WebSocket | Авторизация ListenerBot |
| **Аутентификация** | `/auth/login`, `/auth/logout` | Вход/выход в веб-админку |

### Управление сервисами (ServiceManager)

Сервисы запускаются **лениво** — не автоматически при старте приложения, а через веб-консоль:

- **Admin Bot** — Telegram бот (aiogram)
- **Listener Bot** — мониторинг каналов (Telethon)
- **Scheduler** — планировщик задач + RSS парсинг

Поддерживаются операции: старт, стоп, рестарт, проверка здоровья.

### Health Check

Проверяет здоровье 7 компонентов:

| Компонент | Критичность | Что проверяет |
|-----------|------------|---------------|
| **database** | CRITICAL | Подключение к БД, `SELECT 1` |
| **telegram_bot** | CRITICAL | `getMe` через Telegram API |
| **ollama** | HIGH | `/api/tags` — доступность Ollama |
| **llm_fallback** | HIGH | Fallback провайдер (все LLM) |
| **vector_search** | HIGH | ChromaDB подключение |
| **circuit_breakers** | MEDIUM | Состояние circuit breaker'ов |
| **scheduler** | MEDIUM | Подсчёт задач по статусам |
| **categorization_queue** | MEDIUM | Статус очереди категоризации |

Статусы обновляются автоматически каждые 10 секунд.

---

## Документация

### Основная

| Документ | Описание |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Детальная архитектура системы |
| [docs/WEB_ADMIN_GUIDE.md](docs/WEB_ADMIN_GUIDE.md) | Руководство по веб-админке |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | История изменений |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Операционное руководство |
| [docs/CONSOLE_GUIDE.md](docs/CONSOLE_GUIDE.md) | Консоль управления |

### Архитектура и компоненты

| Документ | Описание |
|----------|----------|
| [docs/HEALTH_CHECK_SETUP.md](docs/HEALTH_CHECK_SETUP.md) | Health check компонентов |
| [docs/REDIS_QUEUE_SETUP.md](docs/REDIS_QUEUE_SETUP.md) | Распределённая очередь Redis |
| [docs/CELERY_WORKER_SETUP.md](docs/CELERY_WORKER_SETUP.md) | Celery воркер |
| [docs/CIRCUIT_BREAKER_SETUP.md](docs/CIRCUIT_BREAKER_SETUP.md) | Circuit Breaker |
| [docs/LLM_FALLBACK_SETUP.md](docs/LLM_FALLBACK_SETUP.md) | Fallback LLM провайдер |
| [docs/LLM_CACHE_IMPLEMENTATION.md](docs/LLM_CACHE_IMPLEMENTATION.md) | Кэширование LLM |
| [docs/HNSW_VECTOR_SEARCH_OPTIMIZATION.md](docs/HNSW_VECTOR_SEARCH_OPTIMIZATION.md) | Оптимизация HNSW |
| [docs/AUTO_REINDEX_IMPLEMENTATION.md](docs/AUTO_REINDEX_IMPLEMENTATION.md) | Автопереиндексация |
| [docs/DATABASE_ABSTRACTION_LAYER.md](docs/DATABASE_ABSTRACTION_LAYER.md) | Абстрактный слой БД |
| [docs/AI_AGENT_MICROSERVICE.md](docs/AI_AGENT_MICROSERVICE.md) | AI-агенты микросервис |

### Инфраструктура

| Документ | Описание |
|----------|----------|
| [docs/DOCKER_SETUP_2026_08_09.md](docs/DOCKER_SETUP_2026_08_09.md) | Docker контейнеризация |
| [docs/POSTGRESQL_SETUP.md](docs/POSTGRESQL_SETUP.md) | PostgreSQL |
| [docs/POSTGRESQL_PRODUCTION_SETUP.md](docs/POSTGRESQL_PRODUCTION_SETUP.md) | PostgreSQL production |
| [docs/ALEMBIC_SETUP.md](docs/ALEMBIC_SETUP.md) | Миграции БД |
| [docs/PROMETHEUS_GRAFANA_SETUP.md](docs/PROMETHEUS_GRAFANA_SETUP.md) | Мониторинг |
| [docs/CI_CD_SETUP.md](docs/CI_CD_SETUP.md) | CI/CD |
| [docs/PROXY_SETUP.md](docs/PROXY_SETUP.md) | Настройка прокси |

### Безопасность

| Документ | Описание |
|----------|----------|
| [docs/2FA_IMPLEMENTATION_2026_08_09.md](docs/2FA_IMPLEMENTATION_2026_08_09.md) | 2FA авторизация |
| [docs/WEB_ADMIN_AUTH.md](docs/WEB_ADMIN_AUTH.md) | Аутентификация в веб-админке |
| [docs/AUTH_GUIDE.md](docs/AUTH_GUIDE.md) | Руководство по аутентификации |

---

## Тестирование

```bash
# Все тесты
pytest tests/ -v

# С покрытием
pytest tests/ -v --cov=services --cov=database

# По категориям
pytest tests/test_repositories/ -v   # Репозитории
pytest tests/test_agents/ -v         # AI агенты
pytest tests/test_categorization/ -v # Категоризация
pytest tests/test_news/ -v           # Обработка новостей
pytest tests/test_rss/ -v           # RSS парсер
pytest tests/test_auth/ -v          # 2FA
pytest tests/services/ -v           # Сервисы
```

### Статистика тестов

| Категория | Файлов | Строк |
|-----------|--------|-------|
| **Всего** | 63 | ~11 600 |
| Репозитории | 4 | — |
| AI агенты | 3 | — |
| Категоризация | 2 | — |
| Сервисы | 10 | — |
| Интеграционные | 5 | — |

---

## 📝 Лицензия

MIT License

## 👥 Авторы

- PyPy-dot
- AI-агент Стефания
