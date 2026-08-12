# 🏗️ Архитектура News Aggregator

**Версия:** 4.0.0  
**Дата обновления:** 2026-08-11  
**Статус:** ✅ Актуализирована под v4.0.0 (глубокий рефакторинг, NewsOrchestrator, EventBus)

---

## 📋 Обзор

**News Aggregator** — модульная система сбора, анализа и публикации новостей с использованием AI-агентов. Источники новостей: Telegram-каналы (UserBot), RSS/Atom ленты, web-сайты.

### Архитектурные принципы

| Принцип | Реализация |
|---------|------------|
| **Single Responsibility** | Каждый сервис имеет одну ответственность |
| **Dependency Injection** | Зависимости через конструкторы |
| **Repository Pattern** | Абстракция доступа к данным |
| **Strategy Pattern** | 3 стратегии обработки новостей |
| **Event-Driven** | EventBus с приоритетами |
| **Explicit Dependencies** | Минимум глобальных состояний |

---

## 🏛️ Уровни архитектуры

```
┌─────────────────────────────────────────────────────────────────┐
│                   PRESENTATION LAYER — СБОР НОВОСТЕЙ            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────┐│
│  │  Admin Bot  │  │  Listener   │  │  Scheduler  │  │ Web   ││
│  │  (aiogram)  │  │  Bot        │  │  + RSS      │  │Admin  ││
│  │             │  │  (Telethon) │  │  + Web      │  │FastAPI││
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────┘│
│                                                                  │
│  ┌──────────────┐ ┌───────────────┐ ┌──────────────────────┐  │
│  │ RSS Parser   │ │  Web Parser   │ │  Payment Service     │  │
│  │ (feedparser) │ │  (requests+   │ │  (Telegram Stars)    │  │
│  │ 20+ лент     │ │  BeautifulSoup)│ │                      │  │
│  └──────────────┘ └───────────────┘ └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
┌─────────────────────────────────┐     ┌─────────────────────────┐
│       APPLICATION LAYER         │     │    DOMAIN LAYER         │
│  ┌───────────────────────────┐  │     │  ┌───────────────────┐  │
│  │  NewsOrchestrator         │  │     │  │  Strategies       │  │
│  │  (координация)            │  │     │  │  - Urgent         │  │
│  └───────────────────────────┘  │     │  │  - Scheduled      │  │
│  ┌───────────────────────────┐  │     │  │  - Trusted        │  │
│  │  EventBus                 │  │     │  └───────────────────┘  │
│  │  (события с приоритетами) │  │     └─────────────────────────┘
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  AgentTaskQueue           │  │
│  │  (очередь AI агентов)     │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
        │                                   │
        ▼                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                              │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ Categorization   │  │ News             │  │ Notification  │ │
│  │ ──────────────── │  │ ───────────────  │  │ ───────────── │ │
│  │ • Queue          │  │ • Generation     │  │ • Service     │ │
│  │ • Classifier     │  │ • Context        │  │               │ │
│  │ • Saver          │  │ • Moderation     │  │               │ │
│  │ • Processor      │  │ • Helpers        │  │               │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ Vector Search    │  │ Payment          │  │ LLM Provider  │ │
│  │ ──────────────── │  │ ───────────────  │  │ ───────────── │ │
│  │ • Embeddings     │  │ • Service        │  │ • Ollama      │ │
│  │ • ChromaDB       │  │ • Stars Provider │  │ • qwen2.5:7b  │ │
│  │ • Search Engine  │  │ • Test Provider  │  │               │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Repository  │  │  Database   │  │   Vector    │            │
│  │   Pattern   │  │  (SQLite)   │  │   Store     │            │
│  │  (8 repos)  │  │             │  │  (ChromaDB) │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Модули

### Core (ядро)

```
services/core/
├── container.py            # DI контейнер (явное создание)
├── database.py             # DatabaseService (сессии)
├── llm_provider.py         # LLM абстракция (Ollama, OpenAI, Anthropic)
├── circuit_breaker.py      # Circuit Breaker (защита от сбоев)
├── redis_queue.py          # RedisTaskQueue (распределённая очередь)
└── celery_worker.py        # Celery Worker (обработка задач)
```

**Ответственность:**
- Управление зависимостями (Container) — **явное создание в main.py**
- Управление сессиями БД (DatabaseService) — singleton через `get_database_service()`
- LLM провайдер с fallback (Ollama → OpenAI → Anthropic)
- Circuit Breaker для защиты от каскадных сбоев
- Распределённая очередь задач (Redis)

---

### Categorization (категоризация)

```
services/categorization/
├── __init__.py
├── queue.py            # CategorizationQueue + CategorizationTask
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

**Компоненты:**

| Компонент | Ответственность |
|-----------|----------------|
| **CategorizationQueue** | Очередь задач с async/await (maxlen=10) |
| **NewsClassifier** | Парсинг AI ответов, извлечение category/urgency/text |
| **NewsSaver** | Сохранение постов и событий в БД |
| **CategorizationProcessor** | Координация: AI → парсинг → сохранение |

**Изменения в v3.0:**
- ❌ Удалена обёртка `services/telegram/categorization.py`
- ✅ ListenerBot использует модуль напрямую

---

### News (обработка новостей)

```
services/news/
├── __init__.py
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

**Поток данных:**
```
Scheduler (расписание из БД) → NewsOrchestrator → Strategy
                                                 │
                    ┌────────────────────────────┼──────────────┐
                    │                            │              │
                    ▼                            ▼              ▼
            UrgentNewsStrategy          ScheduledNews     TrustedSource
            (срочные 4-5)               (плановые 1-3)    (доверенные)
                    │                            │              │
                    ▼                            ▼              ▼
            Analyst → EventBus            Сохранение      Публикация
            Editor → Archivist            в БД            напрямую
            Moderation
```

**Компоненты:**

| Компонент | Ответственность |
|-----------|----------------|
| **NewsOrchestrator** | Координация через стратегии, EventBus |
| **NewsGenerationService** | Генерация (Editor + Archivist), уведомления |
| **EventContextService** | Поиск похожих событий/постов (векторный поиск) |
| **ModerationNotificationService** | Уведомления админам о модерации |

**Изменения в v3.0:**
- ✅ Устранено глобальное состояние `_notification_service`
- ✅ NotificationService передаётся через конструктор

---

### AI Agent (агенты)

```
services/ai_agent/
├── __init__.py
├── agent_queue.py          # AgentTaskQueue (локальная или Redis)
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

**Микросервис AI-агентов:**
```
microservices/ai-agent-service/
├── app/
│   └── main.py             # FastAPI приложение (порт 8002)
├── Dockerfile
└── requirements.txt
```

**AI Агенты:**

| Агент | Задача | Промпт |
|-------|--------|--------|
| **Categorizer** | Первичная классификация, фильтрация рекламы | `prompts/categorizer.txt` |
| **Analyst** | Анализ категории, тэгирование, извлечение фактов | `prompts/analyst.txt` |
| **Editor** | Генерация новости в журналистском стиле | `prompts/editor.txt` |
| **Archivist** | Структурирование контекста для векторного поиска | `prompts/archivist.txt` |

**EventBus:**
- Приоритетная очередь (heapq)
- Ограничение параллелизма (Semaphore)
- Обработчики с приоритетами

**AgentTaskQueue:**
- Единая очередь для всех AI агентов
- Приоритеты: CRITICAL, HIGH, NORMAL, LOW
- История выполненных задач
- **v3.9.0:** Поддержка Redis (распределённая очередь)

**AIAgentRemoteClient:**
- HTTP клиент к микросервису AI-агентов
- Автоматический fallback на локальные агенты
- Retry logic при ошибках

---

### Telegram (боты и уведомления)

```
services/telegram/
├── __init__.py         # NotificationService (categorization удалён)
├── connection.py       # Утилиты подключения
└── notification.py     # NotificationService
```

**NotificationService:**
- Уведомления админам (срочные новости, модерация)
- Уведомления подписчикам (с учётом предпочтений)
- **Изменения в v3.0:** Бот передаётся только через конструктор

---

### Bot (Admin Bot)

```
services/bot/
├── __init__.py
├── bot.py              # BotService (aiogram)
├── utils.py
└── handlers/
    ├── __init__.py
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
    └── tasks.py        # Задачи планировщика
```

**BotService:**
- Создание и управление aiogram ботом
- Инициализация NotificationService с ботом
- **Изменения в v3.0:** Удалён singleton `_bot_service`

---

### Listener (UserBot) — мониторинг Telegram-каналов

```
services/listener/
├── __init__.py
├── bot.py              # ListenerBot (Telethon)
├── auth_service.py     # Авторизация через бота
└── handlers/
    └── auth.py          # Хендлеры авторизации
```

**ListenerBot:**
- Мониторинг Telegram-каналов (Telethon)
- Динамическое добавление/удаление каналов
- Отправка задач в CategorizationQueue
- Поддержка 2FA при авторизации

---

### Scheduler (планировщик)

```
services/scheduler/
└── scheduler.py        # Scheduler
```

**Scheduler** — управляемый календарь задач на основе таблицы `tasks`:

| Задача | Описание |
|--------|----------|
| **Утренняя обработка** | `daily_morning` — время из БД (по умолчанию 09:00 МСК) |
| **Вечерняя обработка** | `daily_evening` — время из БД (по умолчанию 21:00 МСК) |
| **Обработка событий** | Каждые 48 часа (настраивается в `settings.event_processing_interval_hours`) |
| **Обработка задач** | Каждые 30 секунд — проверка таблицы `tasks` |
| **RSS-парсинг** | Каждые 5 минут — проверка активных RSS источников |

**Модель Task (`database/models.py`):**
- `task_type` — тип задачи (`daily_morning`, `daily_evening`, `direct_generation`, `scheduled_processing`)
- `scheduled_at` — запланированное время выполнения
- `status` — pending/active/completed/failed/expired/canceled
- `recurring` — флаг периодической задачи
- `recurrence_pattern` — периодичность в днях (1=ежедневно)
- `publisher_channel_id` — канал публикации (для прямой генерации)

**Логика работы:**
1. Планировщик создаёт периодические задачи (`daily_morning`/`daily_evening`) при запуске
2. Каждые 30 секунд проверяет таблицу `tasks` на наличие задач со статусом `pending`
3. Задачи выполняются в порядке очереди, статус обновляется на `active`
4. Периодические задачи возвращаются в статус `pending` с новым `scheduled_at`
5. Одноразовые задачи завершаются терминальным статусом (`completed`/`failed`/`expired`)

---

### Monitoring (мониторинг)

```
monitoring/
├── prometheus/
│   ├── prometheus.yml      # Конфигурация scraping
│   └── alerts.yml          # 30+ правил алертов
└── grafana/
    ├── dashboards/
    │   ├── ai_agents.json            # Дашборд AI агентов
    │   ├── llm_circuit_breaker.json  # Дашборд LLM и CB
    │   └── infrastructure.json       # Инфраструктурный дашборд
    └── provisioning/
        ├── datasources/      # Prometheus datasource
        └── dashboards/       # Провижининг дашбордов
```

**Компоненты:**

| Компонент | Описание |
|-----------|----------|
| **Prometheus** | Сбор метрик (15s интервал), хранение (15 дней) |
| **Alertmanager** | Обработка алертов (email, Telegram, Slack) |
| **Grafana** | Визуализация метрик, дашборды |

**Метрики:**
- `agent_queue_size` — размер очереди задач
- `agent_tasks_total` — всего задач (по статусам)
- `agent_task_duration` — длительность выполнения
- `circuit_breaker_state` — состояние CB
- `llm_requests_total` — LLM запросы
- `vector_search_duration` — задержка поиска

---

### Vector Search (векторный поиск)

```
services/vector_search/
├── __init__.py
├── embeddings.py       # EmbeddingService (sentence-transformers)
├── chroma_client.py    # ChromaVectorStore (ChromaDB)
└── search_engine.py    # VectorSearchEngine
```

**Компоненты:**

| Компонент | Ответственность |
|-----------|----------------|
| **EmbeddingService** | Генерация эмбеддингов (sentence-transformers) |
| **ChromaVectorStore** | Хранение и поиск векторов (ChromaDB) |
| **VectorSearchEngine** | Поиск похожих событий и постов |

**Использование:**
- Поиск контекста для генерации новостей
- Поиск похожих событий (min_score=0.7)
- Поиск похожих постов (min_score=0.6)

---

### Payment (платежи)

```
services/payment/
├── __init__.py
├── abstractions.py     # PaymentProvider, PaymentLink, PaymentData
├── service.py          # PaymentService
├── test_provider.py    # TestPaymentProvider (тестовый)
└── telegram_stars_provider.py  # TelegramStarsProvider
```

**Провайдеры:**

| Провайдер | Описание |
|-----------|----------|
| **TestProvider** | Тестовый режим (бесплатно) |
| **TelegramStarsProvider** | Telegram Stars (нативная оплата) |

**Настройки:**
- `payment_provider` — выбор провайдера (test / telegram_stars)
- `subscription_price_rub` — цена подписки (99 руб)
- `subscription_duration_days` — длительность (30 дней)

---

## 🗄️ База данных

### Модели (database/models.py)

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

### Ключевые поля

**TelegramPost:**
- `category` — категория новости
- `urgency` — срочность (1-5)
- `checked_at` (Boolean) — обработан ли аналитиком
- `category_confidence` — уверенность категории (0.0-1.0)
- `source_trust_rating` — рейтинг доверия источника
- `bypass_ara` — обошёл ли цикл АРА
- `publisher_channel_id` — канал публикации (если напрямую)

**GeneratedNews:**
- `text` — сгенерированный текст
- `moderation_status` — pending/approved/rejected/edited
- `bypass_ara` — обошёл ли цикл АРА
- `publisher_channel_id` — канал публикации
- `published_at` — время публикации

**User:**
- `user_id_encrypted` — зашифрованный ID (AES-256-GCM)
- `user_id_hash` — HMAC-SHA256 хэш (для поиска)
- `role` — user / admin
- `has_subscription` — наличие подписки
- `subscription_started_at` / `subscription_ends_at` — даты подписки
- `preferred_categories` / `preferred_tags` — предпочтения (JSON)

**Task** — календарь задач планировщика:
- `task_type` — тип задачи (`daily_morning`, `daily_evening`, `direct_generation`, `scheduled_processing`)
- `description` — описание задачи
- `post_id` — ID поста (для прямой генерации)
- `news_id` — ID новости (для плановой обработки)
- `scheduled_at` — запланированное время выполнения
- `status` — pending/active/completed/failed/expired/canceled
- `recurring` — флаг периодической задачи
- `recurrence_pattern` — периодичность в днях (1=ежедневно, 2=раз в 2 дня)
- `publisher_channel_id` — ID канала публикации
- `created_at` / `completed_at` — время создания/завершения

### Репозитории (database/repositories/)

| Репозиторий | Файл |
|-------------|------|
| **BaseRepository** | `base.py` |
| **ChannelRepository** | `channels.py` |
| **PostRepository** | `posts.py` |
| **EventRepository** | `events.py` |
| **NewsRepository** | `news.py` |
| **PublisherRepository** | `publishers.py` |
| **UserRepository** | `users.py` |
| **CategoryRepository** | `categories.py` |
| **TaskRepository** | `tasks.py` |

---

## 🔄 Жизненный цикл задач (таблица `tasks`)

### Статусы задач

```
┌─────────────────────────────────────────────────────────────────┐
│                    ЖИЗНЕННЫЙ ЦИКЛ ЗАДАЧИ                        │
└─────────────────────────────────────────────────────────────────┘

ПЕРИОДИЧЕСКАЯ ЗАДАЧА (recurring=True):
┌─────────┐    ┌─────────┐    ┌─────────┐
│ pending │───▶│ active  │───▶│ pending │───▶ ...
└─────────┘    └─────────┘    └─────────┘
                  │
                  ▼
            (выполнение)
                  │
                  ▼
            reset_recurring_task()
            (новое scheduled_at)

ОДНОРАЗОВАЯ ЗАДАЧА (recurring=False):
┌─────────┐    ┌─────────┐    ┌──────────────┐
│ pending │───▶│ active  │───▶│ completed    │
└─────────┘    └─────────┘    │ failed       │
                  │            │ expired      │
                  │            │ canceled     │
                  ▼            └──────────────┘
            (выполнение)
                  │
                  ▼
            mark_completed()
            или mark_failed()
```

### Переходы статусов

| Из статуса | В статус | Условие | Метод |
|------------|----------|---------|-------|
| `pending` | `active` | Время наступило, взято в работу | `mark_active()` |
| `active` | `pending` | Периодическая задача выполнена | `reset_recurring_task()` |
| `active` | `completed` | Одноразовая задача выполнена | `mark_completed()` |
| `active` | `failed` | Ошибка выполнения | `mark_failed()` |
| `pending` | `expired` | Время вышло, не успели взять | `mark_expired()` |
| `*` | `canceled` | Отменено админом | `mark_canceled()` |

### Проверка просроченных задач

Планировщик проверяет просроченные одноразовые задачи перед каждой обработкой:
- Если `scheduled_at < now` и `recurring=False` → статус `expired`
- Это предотвращает выполнение задач, которые не успели взять в работу

---

## 🔄 Поток обработки новостей

### Срочная новость (срочность 4-5)

```
┌──────────────┐
│ Listener Bot │
└──────┬───────┘
       │ Новый пост
       ▼
┌──────────────────┐
│ Categorization   │
│ Queue            │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Categorization   │
│ Processor        │
└──────┬───────────┘
       │
       ├─────────────────────┐
       │                     │
       ▼                     ▼
┌─────────────┐       ┌─────────────┐
│ NewsSaver   │       │ Analyst     │
│ (сохранить) │       │ (анализ)    │
└──────┬──────┘       └──────┬──────┘
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
         ┌────────────────┐
         │ UrgentNews     │
         │ Strategy       │
         └───────┬────────┘
                 │
                 ▼
         ┌────────────────┐
         │ EventBus       │
         │ GENERATE_NEWS  │
         └───────┬────────┘
                 │
                 ▼
         ┌────────────────┐
         │ Editor         │
         │ (генерация)    │
         └───────┬────────┘
                 │
                 ▼
         ┌────────────────┐
         │ Archivist      │
         │ (контекст)     │
         └───────┬────────┘
                 │
                 ▼
         ┌────────────────┐
         │ Moderation     │
         │ (уведомление)  │
         └────────────────┘
```

### Плановая новость (срочность 1-3)

```
┌──────────────┐
│ Listener Bot │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Categorization   │
│ Processor        │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ AnalystAgent     │  ← Анализ на этапе категоризации!
│ (категория +     │
│  confidence+тэги)│
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ ScheduledNews    │
│ Strategy         │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Сохранение в БД  │
│ checked_at=false │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Scheduler        │
│ (ожидание времени│
│  из tasks表)     │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Таблица `tasks`  │
│ daily_morning/   │
│ daily_evening    │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ NewsOrchestrator │
│ process_pending_ │
│ news_batch()     │  ← Analyst НЕ запускается!
└──────┬───────────┘
       │
       ▼
┌─────────────┐
│ Editor      │
│ (генерация) │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Archivist   │
│ (контекст)  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Moderation  │
└─────────────┘
```

**Важно:** Analyst НЕ запускается в планировщике — он уже сработал в дуэте с Categorizer на этапе категоризации.

**Таблица `tasks` — календарь задач:**
- Периодические задачи (`daily_morning`/`daily_evening`) создаются при запуске планировщика
- Время выполнения хранится в поле `scheduled_at` (настраивается через БД)
- Планировщик проверяет таблицу каждые 30 секунд
- Задачи переходят по статусам: `pending` → `active` → `pending` (периодические) или `completed`/`failed` (одноразовые)

### Доверенный источник (срочность 4-5 + is_trusted=true)

```
┌──────────────┐
│ Listener Bot │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Categorization   │
│ Processor        │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Analyst          │
│ (анализ)         │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ TrustedSource    │
│ Strategy         │
└──────┬───────────┘
       │
       ├──────────────────┐
       │                  │
       ▼                  ▼
┌─────────────┐   ┌─────────────┐
│ Публикация  │   │ Уведомление │
│ в канал     │   │ подписчикам │
└─────────────┘   └─────────────┘
```

---

## 🧩 EventBus

### Архитектура

```
┌─────────────────────────────────────────┐
│              EventBus                   │
│  ┌─────────────────────────────────┐   │
│  │  Priority Queue                 │   │
│  │  (heapq, PrioritizedEvent)      │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Handlers (по приоритету)       │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Semaphore (concurrency limit)  │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Типы событий

```python
class EventType(Enum):
    NEW_NEWS = auto()           # Новый пост
    CATEGORIZED = auto()        # Категория определена
    SAVE_NEWS = auto()          # Сохранить новость
    CREATE_CONTEXT = auto()     # Создать контекст
    VALIDATE_CATEGORY = auto()  # Проверка категории
    GENERATE_NEWS = auto()      # Генерация новости
```

### Приоритеты

| Приоритет | Значение | Пример |
|-----------|----------|--------|
| **Высокий** | 1 | Срочные новости (4-5) |
| **Нормальный** | 3 | Плановые новости (1-3) |
| **Низкий** | 5 | Фоновые задачи |

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

---

## 📊 Масштабирование

### Горизонтальное

- Несколько инстансов бота (через Redis для очереди)
- Разделение ListenerBot и AdminBot на разные серверы
- Вынос векторного поиска в отдельный сервис

### Вертикальное

- Увеличение лимита параллелизма EventBus (max_concurrency)
- Оптимизация векторного поиска (индексы ChromaDB)
- Кэширование результатов векторного поиска

---

## 🧪 Тестирование

### Уровни

| Уровень | Описание | Пример |
|---------|----------|--------|
| **Unit** | Отдельные компоненты | TestNewsClassifier |
| **Integration** | Взаимодействие | TestCategorizationProcessor |
| **E2E** | Полный цикл | TestNewsCycle |

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
```

### Статистика (v3.0)

| Категория | Тестов | Покрытие |
|-----------|--------|----------|
| **Всего** | 100+ | ~85% |
| **Categorization** | 5 | 100% |
| **News** | 13 | 100% |
| **Repositories** | 20+ | 90% |
| **Services** | 30+ | 85% |

---

## 📝 Принципы разработки

| Принцип | Описание |
|---------|----------|
| **Явные зависимости** | Минимум глобальных состояний, зависимости через конструктор |
| **Иммутабельность** | Данные не изменяются, создаются новые |
| **Асинхронность** | Все I/O операции async/await |
| **Типизация** | Type hints для всех функций и методов |
| **Документирование** | Docstrings для всех классов и публичных методов |

---

## 🔄 Изменения в версии 4.0 (2026-08-11)

### Глубокий рефакторинг архитектуры

| Компонент | Изменение |
|-----------|-----------|
| **NewsOrchestrator** | Новый координатор с паттерном Strategy |
| **EventBus** | Шина событий с приоритетами |
| **Scheduler** | Календарь задач на основе таблицы `tasks` |
| **ListenerBot** | Выделен в отдельный сервис (Telethon) |
| **Модульная категоризация** | `services/categorization/` — отдельный модуль |
| **Векторный поиск** | Оптимизированный ChromaDB клиент |

### Таблица `tasks` — управляемый календарь задач

**До:** Жёстко закодированное расписание в планировщике  
**После:** Гибкое расписание через таблицу `tasks` в БД

| Возможность | Реализация |
|-------------|------------|
| **Периодические задачи** | `daily_morning`/`daily_evening` с настраиваемым временем |
| **Прямая генерация** | `direct_generation` — генерация новости по описанию |
| **Плановая обработка** | `scheduled_processing` — обработка новостей по расписанию |
| **Статусы задач** | pending/active/completed/failed/expired/canceled |
| **Recurrence pattern** | Периодичность в днях для периодических задач |

### Удалённые компоненты

| Файл | Причина |
|------|---------|
| `database/migrate_*.py` | Миграции применены, файлы не нужны |
| `services/bot/config.py` | Конфигурация перенесена в `settings.py` |
| `services/listener/helpers.py` | Мёртвый код |
| `docs/PROJECT_HISTORY.md` | Устаревшая документация |

---

## 🔄 Изменения в версии 3.0 (2026-08-08)

### Устранение глобальных состояний

| Компонент | Было | Стало |
|-----------|------|-------|
| **NotificationService** | `_notification_service` singleton | Явное создание в BotService |
| **BotService** | `_bot_service` singleton | Явное создание в main.py |
| **Container** | `_container` singleton | Явное создание в main.py |

### Удалённые компоненты

| Файл | Причина |
|------|---------|
| `services/telegram/categorization.py` | Дублировал `services/categorization/` |

### Обновлённые зависимости

| Файл | Изменение |
|------|-----------|
| `services/listener/bot.py` | Прямое использование `services/categorization/` |
| `services/news/orchestrator.py` | Получение NotificationService через ссылку |
| `services/bot/handlers/*` | Использование `get_bot_instance()` |

---

**Автор:** AI-агент Стефания  
**Дата актуализации:** 2026-08-11  
**Версия:** 4.0.0
