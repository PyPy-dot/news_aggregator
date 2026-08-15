# История изменений News Aggregator

Хронологическая запись всех значимых изменений проекта.

---

## 2026-08-16 — v4.0.0 (hotfix) — Health Check, ServiceManager, Web Admin

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
- ✅ docs/ARCHITECTURE.md — полная актуализация (ServiceManager, Health Check, Web Admin)
- ✅ docs/WEB_ADMIN_GUIDE.md — полная переработка (52 endpoint'а, 7+ страниц)
- ✅ docs/CHANGELOG.md — добавлена запись за 2026-08-16

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