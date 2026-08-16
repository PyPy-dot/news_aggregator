# 🏗️ Архитектура News Aggregator

**Версия:** 4.0.0
**Дата обновления:** 2026-08-16
**Статус:** ✅ Актуализирована — ServiceManager, Health Check, Web Admin v2

---

## 📋 Обзор

**News Aggregator** — модульная система сбора, анализа и публикации новостей с использованием AI-агентов. Источники: Telegram-каналы (UserBot), RSS/Atom ленты, web-сайты.

### Статистика проекта

| Метрика | Значение |
|---------|----------|
| Строк кода (services) | ~34 500 |
| Строк кода (database) | ~5 100 |
| Модулей | 16 |
| API endpoint'ов | 52 |
| Репозиториев | 11 |
| Моделей БД | 11 |
| Файлов тестов | 63 |
| Строк тестов | ~11 600 |

### Архитектурные принципы

| Принцип | Реализация |
|---------|------------|
| **Single Responsibility** | Каждый сервис — одна ответственность |
| **Dependency Injection** | Зависимости через конструкторы (Container) |
| **Repository Pattern** | Абстракция доступа к данным (11 репозиториев) |
| **Strategy Pattern** | 3 стратегии обработки новостей |
| **Event-Driven** | EventBus с приоритетами |
| **Lazy Startup** | Сервисы стартуют по запросу через ServiceManager |

---

## 🏛️ Уровни архитектуры

```
┌─────────────────────────────────────────────────────────────────┐
│                   PRESENTATION LAYER — УПРАВЛЕНИЕ                │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌────────┐│
│  │  Admin Bot  │  │  Listener   │  │  Scheduler   │  │ Web    ││
│  │  (aiogram)  │  │  Bot        │  │  + RSS       │  │ Admin  ││
│  │             │  │  (Telethon) │  │  + Web       │  │        ││
│  └─────────────┘  └─────────────┘  └──────────────┘  │FastAPI ││
│                                                         └───────┘│
│  ┌──────────────┐ ┌───────────────┐ ┌──────────────────┐       │
│  │ RSS Parser   │ │  Web Parser   │ │  ServiceManager  │       │
│  │ (feedparser) │ │  (requests+   │ │  (lazy start/    │       │
│  │              │ │  BeautifulSoup)│ │   stop/restart)  │       │
│  └──────────────┘ └───────────────┘ └──────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
┌─────────────────────────────────┐     ┌───────────────────────┐
│       APPLICATION LAYER         │     │    DOMAIN LAYER       │
│  ┌───────────────────────────┐  │     │  ┌─────────────────┐  │
│  │  NewsOrchestrator         │  │     │  │  Strategies     │  │
│  │  (координация)            │  │     │  │  - Urgent       │  │
│  └───────────────────────────┘  │     │  │  - Scheduled    │  │
│  ┌───────────────────────────┐  │     │  │  - Trusted      │  │
│  │  EventBus                 │  │     │  └─────────────────┘  │
│  │  (события с приоритетами) │  │     └───────────────────────┘
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  AgentTaskQueue           │  │
│  │  (очередь AI агентов)     │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                              │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ Categorization   │  │ News           │  │ Notification   │  │
│  │ ──────────────── │  │ ────────────── │  │ ────────────── │  │
│  │ • Queue          │  │ • Generation   │  │ • Service      │  │
│  │ • Classifier     │  │ • Context      │  │                │  │
│  │ • Saver          │  │ • Moderation   │  │                │  │
│  │ • Processor      │  │ • Helpers      │  │                │  │
│  └──────────────────┘  └────────────────┘  └────────────────┘  │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ Vector Search    │  │ Payment        │  │ LLM Provider   │  │
│  │ ──────────────── │  │ ────────────── │  │ ────────────── │  │
│  │ • Embeddings     │  │ • Service      │  │ • Ollama       │  │
│  │ • ChromaDB       │  │ • Stars        │  │ • Fallback     │  │
│  │ • HNSW config    │  │ • Test         │  │ • CircuitBreak │  │
│  │ • Auto-reindex   │  │                │  │ • Cache        │  │
│  └──────────────────┘  └────────────────┘  └────────────────┘  │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ Health Check     │  │ Monitoring     │  │ Logging        │  │
│  │ ──────────────── │  │ ────────────── │  │ ────────────── │  │
│  │ • 10 компонентов │  │ • Prometheus   │  │ • RotatingFile │  │
│  │ • API endpoints  │  │ • Grafana      │  │ • JSON format  │  │
│  └──────────────────┘  └────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                            │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐           │
│  │ Repository   │  │  Database    │  │   Vector    │           │
│  │   Pattern    │  │  Abstraction │  │   Store     │           │
│  │  (11 repos)  │  │  (SQLite/Pg) │  │  (ChromaDB) │           │
│  └─────────────┘  └──────────────┘  └─────────────┘           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐           │
│  │   Redis     │  │   Alembic    │  │  Celery     │           │
│  │  (Queue)    │  │  (Migrations)│  │  (Workers)  │           │
│  └─────────────┘  └──────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Модули

### Main (точка входа)

**`main.py`** — класс `Application`:
- Инициализация DI контейнера и сервисов
- Запуск Web Admin (единственный сервис, стартующий автоматически)
- Регистрация сервисов в ServiceManager
- Обработка сигналов (SIGINT, SIGTERM)
- Корректное завершение (graceful shutdown)

**Порядок запуска:**
1. `Application.initialize()` — DI контейнер, сервисы
2. `Application.run()` — Web Admin + регистрация в ServiceManager
3. Сервисы стартуют **лениво** через консоль админки
4. `Application.shutdown()` — ServiceManager.stop_all() → очередь → Web Admin → ресурсы

---

### Core (ядро)

```
services/core/
├── container.py            # DI контейнер (явное создание)
├── database.py             # DatabaseService (обёртка над абстрактным слоем)
├── llm_provider.py         # LLM абстракция (Ollama, OpenAI, Anthropic + Fallback)
├── circuit_breaker.py      # Circuit Breaker (защита от каскадных сбоев)
├── redis_queue.py          # RedisTaskQueue (распределённая очередь)
└── celery_worker.py        # Celery Worker (обработка задач)
```

---

### ServiceManager (управление сервисами)

**`services/service_manager.py`**

Singleton для управления жизненным циклом сервисов из веб-админки:

| Метод | Описание |
|-------|----------|
| `start_service(name)` | Запуск сервиса |
| `stop_service(name)` | Остановка сервиса |
| `restart_service(name)` | Перезапуск с очисткой ресурсов |
| `get_all_statuses()` | Статусы всех сервисов (state, healthy, uptime, last_error) |
| `start_all()` / `stop_all()` | Массовый запуск/остановка |

**Состояния сервисов:** `stopped` → `starting` → `running` → `stopping` / `crashed`

**Особенности рестарта бота:**
- `dp.stop_polling()` для graceful shutdown polling
- Ожидание завершения задачи (15 сек таймаут)
- Пауза 5 сек для очистки Telegram сессии на сервере
- `force_close()` → `shutdown()` → сборка мусора

---

### Categorization (категоризация)

```
services/categorization/
├── queue.py            # CategorizationQueue (локальная + Redis дубликат)
├── classifier.py       # NewsClassifier + ClassificationResult
├── saver.py            # NewsSaver
└── processor.py        # CategorizationProcessor
```

**Поток данных:**
```
ListenerBot → CategorizationQueue → CategorizationProcessor
                                    ├─ CategorizerAgent (AI)
                                    ├─ NewsClassifier (парсинг)
                                    ├─ NewsSaver (БД)
                                    └─ NotificationService (уведомления)
```

**CategorizationQueue:**
- Локальная очередь (`deque`, maxlen=10) — основной потребитель
- Redis — дублирующий бэкэнд для распределённых воркеров
- `add()` пишет в локальную очередь + дублирует в Redis
- `get()` читает из локальной очереди

---

### News (обработка новостей)

```
services/news/
├── orchestrator.py     # NewsOrchestrator + стратегии
├── generation.py       # NewsGenerationService
├── context.py          # EventContextService
├── moderation.py       # ModerationNotificationService
├── helpers.py          # Helper-функции (векторный поиск)
└── strategies/
    ├── base.py         # NewsProcessingStrategy (абстрактный)
    ├── urgent.py       # UrgentNewsStrategy (срочность 4-5)
    ├── scheduled.py    # ScheduledNewsStrategy (срочность 1-3)
    └── trusted.py      # TrustedSourceStrategy (доверенные источники)
```

---

### AI Agent (агенты)

```
services/ai_agent/
├── agent_queue.py          # AgentTaskQueue (локальная или Redis)
├── cache.py                # LLM Cache
├── remote_client.py        # AIAgentRemoteClient (клиент к микросервису)
├── agents/
│   ├── base.py             # BaseAgent (работа с LLM)
│   ├── categorizer.py      # CategorizerAgent
│   ├── analyst.py          # AnalystAgent
│   ├── editor.py           # EditorAgent
│   └── archivist.py        # ArchivistAgent
├── events.py               # EventType, Event
├── routers.py              # EventBus (шина событий)
└── vector_routers.py       # Обработчики векторного поиска
```

---

### Telegram (боты и уведомления)

```
services/telegram/
├── __init__.py         # NotificationService
├── connection.py       # Утилиты подключения
└── notification.py     # NotificationService (уведомления)
```

---

### Bot (Admin Bot)

```
services/bot/
├── bot.py              # BotService (aiogram, lazy init)
├── utils.py
└── handlers/
    ├── router.py       # Главный роутер
    ├── access.py       # Проверка прав админа
    ├── callbacks.py    # Callback query handlers
    ├── callbacks_admin.py
    ├── callbacks_channels.py
    ├── callbacks_moderation.py
    ├── callbacks_preferences.py
    ├── commands.py     # Команды бота
    ├── direct_news.py  # Прямая генерация новостей
    ├── filters.py      # Фильтры сообщений
    ├── keyboards.py    # Клавиатуры
    ├── messages.py     # Текстовые handlers
    ├── payment.py      # Обработка платежей
    ├── publisher.py    # Публикация в каналы
    ├── publishers.py   # Управление каналами
    ├── states.py       # FSM состояния
    ├── subscription.py # Подписки
    ├── tasks.py        # Задачи планировщика
    └── two_factor_auth.py
```

---

### Listener (UserBot)

```
services/listener/
├── bot.py              # ListenerBot (Telethon)
├── auth_service.py     # Авторизация через бота
└── handlers/
    └── auth.py          # Хендлеры авторизации
```

---

### Scheduler (планировщик)

```
services/scheduler/
└── scheduler.py        # Scheduler
```

**Задачи планировщика:**

| Задача | Интервал | Описание |
|--------|----------|----------|
| `daily_morning` | по расписанию | Утренняя обработка (по умолчанию 09:00 МСК) |
| `daily_evening` | по расписанию | Вечерняя обработка (по умолчанию 21:00 МСК) |
| Обработка событий | 48 часов | Настройка: `event_processing_interval_hours` |
| Проверка задач | 30 секунд | Таблица `tasks` |
| RSS-парсинг | 5 минут | Активные RSS источники |

---

### Health Check (мониторинг здоровья)

```
services/monitoring/
├── health_check.py     # HealthChecker + 8 встроенных проверок
├── metrics.py          # Prometheus метрики
└── __init__.py
```

**Проверяемые компоненты:**

| Компонент | Критичность | Метод проверки |
|-----------|------------|----------------|
| **database** | CRITICAL | `SELECT 1` через session_context |
| **telegram_bot** | CRITICAL | `bot.get_me()` через Telegram API |
| **ollama** | HIGH | `/api/tags` — доступность |
| **llm_fallback** | HIGH | Проверка всех провайдеров |
| **vector_search** | HIGH | `client.list_collections()` |
| **circuit_breakers** | MEDIUM | Состояние всех breaker'ов |
| **listener** | HIGH | Проверка подключения ListenerBot (Telethon) |
| **scheduler** | MEDIUM | Подсчёт задач по статусам |
| **categorization_queue** | MEDIUM | Наличие очереди |

**API:**
- `GET /api/health` — краткий статус
- `GET /api/health/full` — полная проверка
- `GET /api/health/{component}` — конкретный компонент
- `GET /api/health/live` — liveness probe
- `GET /api/health/ready` — readiness probe

---

### Vector Search

```
services/vector_search/
├── embeddings.py       # EmbeddingService (sentence-transformers)
├── chroma_client.py    # ChromaVectorStore (ChromaDB)
├── search_engine.py    # VectorSearchEngine
├── service.py          # VectorSearchService (DI)
├── hnsw_config.py      # Оптимизация HNSW параметров
└── auto_reindex.py     # Автопереиндексация
```

---

### Web Admin

```
services/web_admin/
├── api/
│   ├── app.py          # FastAPI приложение (роуты + middleware)
│   └── auth.py         # JWT утилиты (Telegram авторизация)
├── routes/
│   ├── auth.py         # Вход/выход
│   ├── channels.py     # Каналы
│   ├── console.py      # Консоль управления (11 endpoint'ов)
│   ├── dashboard.py    # Дашборд
│   ├── listener_auth.py # Авторизация Listener (6 endpoint'ов)
│   ├── listener_auth_ws.py # WebSocket для авторизации
│   ├── news.py         # Новости
│   ├── rss.py          # RSS
│   ├── settings.py     # Настройки (.env)
│   ├── tasks.py        # Задачи (12 endpoint'ов)
│   ├── users.py        # Пользователи
│   └── web.py          # Web источники
├── health_router.py    # Health check API
├── session_manager.py  # Сессии + JWT (SQLite)
├── service.py          # WebAdminService (uvicorn)
├── config.py           # Конфигурация + load_dotenv
├── log_handler.py      # Логирование
└── templates/
    ├── base.html       # Единый layout (header, sidebar, footer, modals)
    ├── index.html      # Главная панель (extends base)
    ├── console.html    # Консоль управления (extends base)
    ├── settings.html   # Настройки (extends base)
    ├── login.html      # Страница входа
    ├── news.html       # Новости
    ├── channels.html   # Каналы
    ├── users.html      # Пользователи
    ├── tasks.html      # Задачи
    ├── rss.html        # RSS
    ├── web.html        # Web источники
    └── components/
        ├── sidebar.html             # Навигационная панель
        ├── footer.html              # Футер с глобальным статусом
        ├── listener-auth-modal.html
        └── notifications-modal.html
```

---

### Database (абстрактный слой)

```
services/database/
├── config.py             # DatabaseConfig
├── enums.py              # DatabaseType, ConnectionStatus
├── exceptions.py         # Исключения
├── interfaces.py         # IDatabaseService, IProvider
├── factory.py            # DatabaseServiceFactory
├── postgresql_admin.py   # Администрирование PostgreSQL
└── providers/
    ├── base.py           # BaseDatabaseService
    ├── sqlite.py         # SQLiteDatabaseService
    ├── postgresql.py     # PostgreSQLDatabaseService
    └── mysql.py          # MySQLDatabaseService
```

---

## 🗄️ База данных

### Модели (`database/models.py`)

| Модель | Таблица | Описание |
|--------|---------|----------|
| **Channel** | `channels` | Каналы Telegram (источники) |
| **TelegramPost** | `posts` | Посты из каналов |
| **GeneratedNews** | `generated_news` | Сгенерированные новости |
| **EventContext** | `events` | Контексты событий |
| **Publisher** | `publishers` | Каналы публикации |
| **User** | `users` | Пользователи бота |
| **NewsCategory** | `news_categories` | Справочник категорий |
| **Task** | `tasks` | Задачи планировщика |
| **RSSSource** | `rss_sources` | RSS источники |
| **RSSNews** | `rss_news` | RSS новости |
| **WebSource** | `web_sources` | Web источники |
| **WebNews** | `web_news` | Web новости |

### Репозитории (`database/repositories/`)

| Репозиторий | Файл |
|-------------|------|
| BaseRepository | `base.py` |
| ChannelRepository | `channels.py` |
| PostRepository | `posts.py` |
| EventRepository | `events.py` |
| NewsRepository | `news.py` |
| PublisherRepository | `publishers.py` |
| UserRepository | `users.py` |
| CategoryRepository | `categories.py` |
| TaskRepository | `tasks.py` |
| RSSSourceRepository | `rss_sources.py` |
| RSSNewsRepository | `rss_news.py` |

---

## 🔄 Жизненный цикл задач (таблица `tasks`)

### Статусы задач

```
ПЕРИОДИЧЕСКАЯ ЗАДАЧА (recurring=True):
pending ──▶ active ──▶ pending ──▶ ...

ОДНОРАЗОВАЯ ЗАДАЧА (recurring=False):
pending ──▶ active ──▶ completed / failed / expired / canceled
```

### Переходы статусов

| Из статуса | В статус | Условие | Метод |
|------------|----------|---------|-------|
| `pending` | `active` | Время наступило | `mark_active()` |
| `active` | `pending` | Периодическая задача | `reset_recurring_task()` |
| `active` | `completed` | Одноразовая задача | `mark_completed()` |
| `active` | `failed` | Ошибка | `mark_failed()` |
| `pending` | `expired` | Время вышло | `mark_expired()` |

---

## 🔐 Безопасность

### Шифрование данных

| Параметр | Значение |
|----------|----------|
| **Алгоритм** | AES-256-GCM |
| **Ключ** | `ENCRYPTION_KEY` (32+ символа) |
| **Данные** | `user_id_encrypted` |

### Хэширование

| Параметр | Значение |
|----------|----------|
| **Алгоритм** | HMAC-SHA256 |
| **Цель** | Детерминированный поиск пользователей |
| **Данные** | `user_id_hash` |

### Web Admin аутентификация

- SQLite БД для учётных данных (`.web_admin_session.db`)
- Хэширование паролей через bcrypt
- JWT токены с продлением сессии (3 часа)
- Секрет: `WEB_ADMIN_JWT_SECRET` из `.env`

---

## 📊 Масштабирование

### Горизонтальное
- Несколько инстансов бота (через Redis для очереди)
- Разделение ListenerBot и AdminBot на разные серверы
- Вынос векторного поиска в отдельный сервис

### Вертикальное
- Увеличение лимита параллелизма EventBus (`max_concurrency`)
- Оптимизация векторного поиска (индексы ChromaDB)
- Кэширование результатов векторного поиска

---

## 🧪 Тестирование

### Уровни

| Уровень | Описание | Файлов |
|---------|----------|--------|
| **Unit** | Отдельные компоненты | ~48 |
| **Integration** | Взаимодействие | ~10 |
| **E2E** | Полный цикл | ~5 |

### Запуск

```bash
# Все тесты
pytest tests/ -v

# С покрытием
pytest tests/ -v --cov=services --cov=database

# По категориям
pytest tests/test_categorization/ -v   # Категоризация
pytest tests/test_news/ -v             # Обработка новостей
pytest tests/test_agents/ -v           # AI агенты
pytest tests/test_repositories/ -v     # Репозитории
pytest tests/services/ -v              # Сервисы
pytest tests/test_rss/ -v             # RSS
pytest tests/test_auth/ -v            # 2FA
```

---

## 📝 Принципы разработки

| Принцип | Описание |
|---------|----------|
| **Явные зависимости** | Минимум глобальных состояний, зависимости через конструктор |
| **Иммутабельность** | Данные не изменяются, создаются новые |
| **Асинхронность** | Все I/O операции async/await |
| **Типизация** | Type hints для всех функций и методов |
| **Документирование** | Docstrings для всех классов и публичных методов |
| **Lazy Startup** | Сервисы стартуют по запросу, не автоматически |

---

## 🔄 Изменения в версии 4.0.0 (2026-08-16)

### ServiceManager — управление сервисами
- Сервисы запускаются **лениво** через веб-консоль
- Graceful shutdown с очисткой ресурсов
- Проверка жизненности (`is_alive`), uptime, last_error

### Health Check — проверка здоровья
- 8 компонентов: database, telegram_bot, ollama, llm_fallback, vector_search, circuit_breakers, scheduler, categorization_queue
- API: `/health`, `/health/full`, `/health/{component}`
- Автоматическое обновление каждые 10 секунд

### Web Admin v2
- 52 API endpoint'а
- 7+ страниц (главная, консоль, настройки, новости, каналы, пользователи, задачи, RSS, web)
- Панель уведомлений о сбоях
- Глобальный статус в футере на всех страницах
- Консоль: SQL, Python, логи, управление сервисами

### Логирование
- Централизованная настройка (`logging_config.py`)
- Корреляция ID для отслеживания запросов
- Подавление шума: httpx, SQLAlchemy, aiohttp

---

**Автор:** AI-агент Стефания
**Дата актуализации:** 2026-08-16
**Версия:** 4.0.0
