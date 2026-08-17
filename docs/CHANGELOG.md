# История изменений News Aggregator

Хронологическая запись всех значимых изменений проекта.

---

## 2026-08-17 — v4.2.0 — Унифицированный мульти-источниковый пайплайн

### Мульти-источниковая категоризация (Telegram + RSS + Web)

Единый пайплайн обработки для всех источников. Раньше RSS создавал `posts` напрямую
с хардкодом `channel_id=-1001`, а Web вообще не был подключён к процессу обработки.

**Архитектура после:**
```
Источник → Сырая таблица → CategorizationQueue → Categorizer → Analyst
  → Обновление сырой таблицы → Orchestrator (batch по категориям)
  → Editor → Archivist → generated_news (source_ids: ["tg_5", "rss_13", "web_10"])
```

### Database — модели и миграция

- **`GeneratedNews.source_ids`** — JSON-список исходных новостей с префиксом источника
- **`EventContext.source_news_ids`** — список новостей, на основе которых создан контекст
- **`EventContext.post_id`** — больше не привязан FK к `TelegramPost.id` (общий контекст для всех источников)
- **`RSSNews`** — новые поля: `urgency`, `category_confidence`, `rate`, `generated_news_id`; убран `post_id` (FK к posts)
- **`WebNews`** — новые поля: `urgency`, `category_confidence`, `rate`, `generated_news_id`; убран `post_id` (FK к posts)
- **Миграция** `migrate_multisource_2026_08_17.py` — пересоздание `events` без FK, новые поля во всех таблицах

### CategorizationQueue — мульти-источник

- **`CategorizationTask`** — поля `source_type` (telegram/rss/web), `source_id`; `channel_id` теперь опциональный
- **`CategorizationProcessor`** — диспатчер по `source_type`: Telegram идёт по старой логике, RSS/Web обновляют сырые таблицы через `update_category()`

### RSS — через общую очередь

- **`RSSProcessorService.categorize_and_process_news()`** — больше не создаёт `posts` напрямую;
  кладёт задачи в `CategorizationQueue` для единой обработки

### Web — полный пайплайн

- **`WebNewsRepository`** — репозиторий с полным API (create, get_unprocessed, mark_processed, update_category)
- **`WebSourceRepository`** — CRUD источников (create, get_active, get_sources_due_for_check, toggle, delete)
- **`WebProcessorService`** — парсинг → `web_news` → `CategorizationQueue`
- **Scheduler `_run_web_parser()`** — запуск каждые 5 минут (как RSS)
- **Route `/web/`** — CRUD источников, ручной парсинг, список новостей

### Orchestrator — мульти-источниковый

- **`_collect_unprocessed_all_sources()`** — собирает из `posts`, `rss_news`, `web_news`
- **`_process_multi_source_batch()`** — Editor генерирует сводку из всех источников одной категории;
  Archivist создаёт контекст события с `source_news_ids`
- **`_mark_batch_processed()`** — отмечает источники как обработанные в соответствующих таблицах
- **`generated_news.source_ids`** — `["tg_5", "rss_13", "web_10"]`

### Изменённые файлы (16)

| Файл | Изменения |
|------|-----------|
| `database/models.py` | Новые поля, убраны FK |
| `database/factory.py` | +web_sources(), +web_news() |
| `database/migrations/migrate_multisource_2026_08_17.py` | **новый** миграция |
| `database/repositories/web_news.py` | **новый** репозиторий |
| `database/repositories/web_sources.py` | **новый** репозиторий |
| `database/repositories/rss_news.py` | update_category(), get_unprocessed_with_category() |
| `database/repositories/news.py` | source_ids параметр |
| `database/repositories/events.py` | source_news_ids, post_id nullable |
| `services/categorization/queue.py` | source_type, source_id |
| `services/categorization/processor.py` | мульти-источниковая логика |
| `services/news/orchestrator.py` | мульти-источниковый batch |
| `services/news/helpers.py` | source_ids параметр |
| `services/rss/processor.py` | через CategorizationQueue |
| `services/web/processor.py` | **новый** процессор |
| `services/scheduler/scheduler.py` | +_run_web_parser() |
| `services/web_admin/routes/web.py` | CRUD источников |

---

## 2026-08-17 — v4.1.0 — Семантический поиск, Web Admin страницы, реиндексация

### Семантический поиск — исправления и абстрактный слой

- ✅ **Новый модуль `services/search_db.py`** — DB-agnostic слой поиска (ILIKE для PostgreSQL, LIKE для SQLite/MySQL)
- ✅ **Фикс `persist_directory`** в `VectorSearchEngine` — хранилище теперь сохраняется на диск (было `None if None else None`)
- ✅ **Валидация размерности эмбеддинга** — `_validate_embedding_dim()` в ChromaClient и бизнес-логике
- ✅ **`search_morph()` исправлен** — пустой/короткий запрос (< 3 символа) больше не матчит всё; защита от `None`
- ✅ **Централизация `search_morph`** — удалены локальные дубли из routes/news, channels, users
- ✅ **Merge-алгоритм результатов** — текстовые совпадения (score=1.0) всегда в топе, семантика как дополнение
- ✅ **min_score поднят** с 0.2 до 0.3 в API-эндпоинтах
- ✅ **Настройки из `config/settings.py`** — `vector_search_*` параметры через settings, не хардкод
- ✅ **Скрипт `scripts/reindex_chroma.py`** — полная переиндексация ChromaDB из БД

**Результат поиска (до → после):**

| Запрос | До | После |
|--------|-----|-------|
| «Салават» | 6 (1 релевантный) | 1 |
| «Кишинёв» | 30 (2 релевантных) | 2 |
| «Украина» | 49 (21 + 42 дубли) | 10 |

### Web Admin — новые страницы

- ✅ **`/channels`** — управление каналами-источниками (поиск, фильтры, доверие, теги)
- ✅ **`/news`** — список новостей с модерацией (posts / generated, текстовый + семантический поиск)
- ✅ **`/users`** — управление пользователями (подписки, роли, 2FA)
- ✅ **`auth_dependency.py`** — единая JWT-зависимость для всех route-модулей
- ✅ **Дашборд** — превью текста новости вместо заголовка, улучшенные модальные окна быстрых действий
- ✅ **Настройки** — параметр `TELEGRAM_USE_IPV6` в `.env.example`

### Database

- ✅ **`TaskRepository`** — улучшенная валидация дат для календаря задач
- ✅ **`UserRepository`** — метод `fix_empty_datetime_fields()` для коррекции пустых строк в datetime
- ✅ **DI контейнер** — передача `persist_directory` из settings в VectorSearchEngine

### Изменённые файлы (36)

- `services/search_db.py` — новый модуль
- `services/web_admin/auth_dependency.py` — новый модуль
- `services/web_admin/routes/channels.py` — полный рефакторинг (875 строк)
- `services/web_admin/routes/news.py` — полный рефакторинг (962 строки)
- `services/web_admin/routes/users.py` — полный рефакторинг (509 строк)
- `services/web_admin/templates/channels.html` — новый шаблон (956 строк)
- `services/web_admin/templates/news.html` — новый шаблон (1138 строк)
- `services/web_admin/templates/users.html` — новый шаблон (844 строки)
- `services/vector_search/search_engine.py` — persist_directory, валидация дименсии
- `services/vector_search/chroma_client.py` — валидация эмбеддинга
- `services/news/helpers.py` — улучшенная логика (90 строк изменений)
- `scripts/reindex_chroma.py` — новый скрипт реиндексации
- `config/settings.py`, `services/core/container.py` — настройки vector_search

---

## 2026-08-16 — v4.0.0 (hotfix) — Health Check, ServiceManager, Web Admin

### Bugfix — Консоль управления

- ✅ Исправлена кнопка «Стоп» в консоли — `disabled` логика была инвертирована (`some` → `every`): кнопка теперь активна когда есть запущенные сервисы, отключена когда все остановлены
- ✅ Добавлен фолбек `|| 'stopped'` для отсутствующих статусов сервисов — `undefined` больше не ломает проверку

### Web Admin — рефакторинг шаблонов

- ✅ Вынесен `base.html` — единый layout (header, sidebar, footer, modals) для всех страниц
- ✅ Компонент `components/sidebar.html` — навигация вынесена в отдельный шаблон
- ✅ Консоль, главная, настройки — наследуются от base.html

### Health Check — проверка здоровья компонентов

- ✅ Исправлен `check_database_health()` — добавлен import `get_database_service`, безопасный доступ к `db_type`
- ✅ Исправлен `check_vector_search_health()` — кэширование ChromaDB клиента, исправлен путь к `_client`
- ✅ Исправлен `check_ollama_health()` — кэширование провайдера
- ✅ Исправлен `check_categorization_queue_health()` — кэширование очереди
- ✅ Все health-компоненты кэшированы — не пересоздаются при каждом запросе

### ServiceManager —统一管理 сервисов

- ✅ Проверка жизненности (`is_alive()`) — сервисы с реальным статусом
- ✅ Uptime для всех сервисов (uptime_sec, started_at)
- ✅ last_error — отслеживание последних ошибок
- ✅ Статусы: `stopped` → `starting` → `running` → `stopping` / `crashed`

### Web Admin v2 — доработка интерфейса

- ✅ Единый формат статусов на всех страницах (OK · 2ч 15м / Ошибка / Остановлен)
- ✅ Глобальный статус в футере — исправлен баг с «Загрузка» (баг в замыкании `k`)
- ✅ Health check обновляется каждые 10 сек через polling
- ✅ Панель уведомлений — ошибки/предупреждения/инфо с фильтрами
- ✅ Статус `crashed` добавлен на все страницы
- ✅ Все страницы используют `d.statuses` (state + healthy) вместо `d.services` (bool)

### Логирование

- ✅ Добавлены исключения для httpx, httpcore, ollama — подавлен шум от health check запросов
- ✅ Понижен уровень «Bot найден» с INFO до DEBUG
- ✅ Понижен уровень «BotService не зарегистрирован» с ERROR до DEBUG

### CategorizationQueue

- ✅ Исправлен разрыв Redis/локальная очередь — `add()` теперь пишет сначала в локальную очередь
- ✅ Redis используется как дублирующий бэкэнд, не основной
- ✅ Убран warning-спам из `get()`

### Web Admin — аутентификация

- ✅ Исправлено имя переменной: `JWT_SECRET` → `WEB_ADMIN_JWT_SECRET`
- ✅ `.env.example` и `routes/settings.py` обновлены
- ✅ `SessionManager` загружает `.env` самостоятельно (pydantic не пишет неизвестные поля в os.environ)

### Документация

- ✅ README.md — полная актуализация
- ✅ docs/ARCHITECTURE.md — полная актуализация (ServiceManager, Health Check 10 компонентов, Web Admin v2)
- ✅ docs/WEB_ADMIN_GUIDE.md — полная переработка (52 endpoint'а, 7+ страниц)
- ✅ docs/RUNBOOK.md — обновление версии, переменных, ServiceManager
- ✅ docs/CHANGELOG.md — добавлены записи для Stop All fix и шаблонов

---

## 2026-08-11 — v4.0.0 — Глубокий рефакторинг архитектуры и модульность

### Основные изменения

**1. NewsOrchestrator — центральная оркестрация:**
- Новый `services/news/orchestrator.py` (342 строки)
- Делегирование обработки стратегиям: Urgent, Scheduled, Trusted, Event Bus
- Приоритетная очередь задач с Event Bus

**2. Listener Bot — отдельный сервис:**
- Выделен из `services/bot/` в `services/listener/`
- Telethon UserBot для мониторинга Telegram
- Обработчики: команды, сообщения, callback, фильтры, паблишеры
- **Файлы:** `services/listener/bot.py`, `services/listener/handlers/*`

**3. Модульная категоризация:**
- `services/telegram/categorization.py` — централизованная категоризация
- Интеграция с AI-агентами (Categorizer, Analyst)
- Обработка срочности и доверенных источников

**4. Улучшенный векторный поиск:**
- Оптимизированный ChromaDB клиент
- Автопереиндексация с LRU-кэшем эмбеддингов
- HNSW индекс для ускорения поиска

**5. Расширенное тестирование:**
- `tests/test_orchestrator.py` — 245 строк тестов orchestrator
- `tests/test_notification.py` — 162 строки тестов notification
- `tests/test_handlers/test_direct_news.py` — 274 строки тестов
- `tests/test_agents/test_base_agent.py` — обновлённые тесты

**6. Очистка кодовой базы:**
- Удалены мёртвые файлы: `REFACTORING_SUMMARY.md`, `REFACTOR_FIXES_SUMMARY.md`
- Удалены старые миграции из `database/`
- Упрощена структура сервисов

**Статистика v4.0.0:**
- Изменено файлов: 43
- Строк добавлено: 3845
- Строк удалено: 1245
- Тестов добавлено: 681+ строк

---

## 2026-08-10 — v3.9.0 — Распределённая очередь, мониторинг, микросервисы

### Основные изменения

**1. Распределённая очередь (Redis/Celery):**
- `RedisTaskQueue` — распределённая очередь с приоритетами
- `Celery Worker` — обработка задач с мониторингом
- Автоматическое переключение Redis/локальная очередь
- **Файлы:** `services/core/redis_queue.py`, `services/core/celery_worker.py`

**2. Интеграционные тесты и CI/CD:**
- 70+ интеграционных тестов (Ollama, ChromaDB, E2E)
- GitHub Actions workflow с автоматическим запуском
- **Файлы:** `tests/test_integration/*`, `.github/workflows/ci.yml`

**3. Prometheus + Grafana мониторинг:**
- Сбор метрик со всех сервисов
- 30+ правил алертов
- 3 Grafana дашборда (AI Agents, LLM & Circuit Breaker, Infrastructure)
- **Файлы:** `monitoring/prometheus/*`, `monitoring/grafana/dashboards/*`

**4. AI-агенты микросервис:**
- `microservices/ai-agent-service/` — FastAPI микросервис
- HTTP API для categorize, analyze, generate_news, create_context
- `AIAgentRemoteClient` — клиент с automatic fallback
- **Файлы:** `microservices/ai-agent-service/*`, `services/ai_agent/remote_client.py`

**Статистика v3.9.0:**
- Новых файлов: 24
- Строк кода добавлено: ~2500
- Новых тестов: 90+

---

## 2026-08-09 — v3.5.0 — Полная реализация плана развития

### ✅ 6/6 задач выполнено (100%)

#### Новые функции

**2FA авторизация (P0):**
- TOTP-аутентификация (pyotp, Google Authenticator / Authy)
- QR-коды для настройки
- Резервные коды (10 шт)
- Telegram хендлеры: /2fa setup, disable, status
- **Файлы:** `services/auth/two_factor_auth.py`, `services/bot/handlers/two_factor_auth.py`

**Учёт регистра тэгов (P1):**
- Case-insensitive: нормализация к lowercase во всех репозиториях
- **Изменено:** users.py, posts.py, channels.py, events.py

**RSS парсинг (P1):**
- feedparser для RSS/Atom
- Таблицы: rss_sources, rss_news
- Автопроверка каждые 5 мин (scheduler)
- **Файлы:** `services/rss/parser.py`, `services/rss/processor.py`

**Web парсинг (P2):**
- requests + bs4 для статических сайтов
- Таблицы: web_sources, web_news
- **Файлы:** `services/web/parser.py`

**Web админка (P2):**
- FastAPI + JWT + 2FA + Tailwind CSS
- 10 роутов: dashboard, news, channels, users, tasks, rss, web, console, settings
- **Файлы:** `services/web_admin/`

**Docker контейнеризация (P1):**
- 7 сервисов: app, web-admin, db, chromadb, ollama, redis, nginx
- docker-compose.yml (dev) + docker-compose.prod.yml (prod)
- **Файлы:** Dockerfile, docker-compose*.yml, .dockerignore, nginx.conf

#### Статистика v3.5.0
- Создано файлов: 40+
- Написано тестов: 43+ (всего 250+)
- Документации: 10 документов (всего в docs/)

---

## 2026-08-09 — v3.4.0 — Глубокий рефакторинг архитектуры

### Основные изменения

**1. Поддержка PostgreSQL (P2):**
- Автоопределение типа БД (SQLite/PostgreSQL)
- Alembic миграции
- `config/settings.py` — DATABASE_URL

**2. Кэширование LLM ответов (P3):**
- LRU-кэш (1000 записей, TTL 24ч)
- Ускорение: 200-500x
- `services/ai_agent/cache.py`

**3. Автопереиндексация векторного поиска (P3):**
- Фоновая переиндексация по триггерам
- LRU-кэш для эмбеддингов (5000 записей)
- `services/vector_search/auto_reindex.py`

**4. Микросервисная архитектура (P3):**
- Спроектированы 3 сервиса: AI Agent, Vector Search, Notification
- Документация и план миграции (10 недель)

**Статистика:** 14+ файлов, 71 тест, 100% задач выполнено

---

## 2026-08-09 — v3.1.x — Исправления и улучшения

### v3.1.20 — Retry логика уведомлений
- 3 попытки с экспоненциальной задержкой (1с, 2с, 4с)
- Обработка таймаутов в `_send_to_subscriber()`, `notify_urgent_news()`

### v3.1.19 — Рефакторинг PaymentService
- Удалены `set_bot()` в PublisherService и TelegramStarsProvider
- Явная передача зависимостей через конструкторы

### v3.1.18 — Тесты прямой генерации (15 тестов)
- Прямая генерация новостей (11 тестов)
- Публикация доверенных источников (4 теста)

### v3.1.17 — Завершение задач P0-P3
- Замена глобальных ссылок на DI (P0)
- Интеграционные тесты (P1)
- Метрики Prometheus (P2)
- Система логирования с correlation ID (P3)

### v3.1.8-16 — Исправления задач и навигации
- 12 замечаний по UI исправлено
- Прямая генерация с мгновенной публикацией
- Публикация доверенных источников в каналы
- Статусы задач: pending/active/completed/failed/expired

---

## 2026-08-08 — v3.0 — Глубокий рефакторинг архитектуры

### Ключевые изменения

**Устранение глобальных состояний:**
- ❌ `_notification_service` singleton → явное создание в BotService
- ❌ `_bot_service` singleton → явное создание в main.py
- ❌ `_container` singleton → явное создание в main.py
- ❌ `CategorizationService` обёртка → прямой вызов

**DI Контейнер:**
- Container в `services/core/container.py`
- Singleton/factory регистрация
- Поддержка строковых ключей для циклических зависимостей

**Стратегии обработки новостей:**
- UrgentNewsStrategy — срочность 4-5
- ScheduledNewsStrategy — срочность 1-3
- TrustedSourceStrategy — доверенные источники

**Логирование:**
- `services/logging_config.py` — централизованная настройка
- Correlation ID для запросов

**Статистика:** 15+ файлов изменено, удалён 1 файл, устранено 3 глобальных состояния

---

## 2026-08-08 — v2.0 — Базовая архитектура

- Разделение CategorizationService на 4 компонента
- Устранение helper-функций
- Рефакторинг Orchestrator (5 компонентов)
- 29 тестов, 100% покрытие новых модулей

---

## v1.x — Начальная разработка

- Создание базовой архитектуры
- Реализация AI агентов
- Настройка БД и миграций
- Telegram бот и UserBot
- Планировщик задач
- Система платежей и подписок