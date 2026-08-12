# 📘 PROJECT_CONTEXT.md — Контекст проекта News Aggregator

**Версия документа:** 3.9.0  
**Дата создания:** 2026-08-08  
**Последнее обновление:** 2026-08-10 (v3.9.0 — все 10 задач выполнены!)

> **Назначение:** Этот файл содержит ключевую информацию о проекте для сохранения контекста между сессиями. Обновляется при внесении значимых изменений.

---

## 🎯 Краткое описание проекта

**News Aggregator v3.5.0** — автоматизированная система сбора, анализа и публикации новостей с использованием AI-агентов.

### Источники новостей
1. ✅ **Telegram-каналы** — мониторинг через UserBot (Telethon)
2. ✅ **RSS/Atom ленты** — feedparser, 20+ лент, автопроверка каждые 5 минут
3. ✅ **Web-сайты** — requests + BeautifulSoup4

### Интерфейсы
1. ✅ **Telegram бот** — администрирование, управление, модерация
2. ✅ **Web админка** — FastAPI + JWT + Tailwind CSS (базовая реализация)

---

## 🔧 Ключевые изменения в v3.9.0 (2026-08-10)

### 1. Распределённая очередь (P0)
- RedisTaskQueue — распределённая очередь с приоритетами
- Celery Worker — обработка задач с мониторингом
- Автоматическое переключение Redis/локальная очередь
- 25 тестов

### 2. Интеграционные тесты (P1)
- 70+ тестов (Ollama, ChromaDB, E2E)
- docker-compose.test.yml — тестовый стенд
- GitHub Actions CI/CD workflow
- Еженедельный schedule

### 3. Prometheus + Grafana (P1)
- Сбор метрик со всех сервисов
- 30+ правил алертов
- 3 Grafana дашборда
- Интеграция circuit breaker метрик

### 4. AI-агенты микросервис (P2)
- FastAPI микросервис (порт 8002)
- HTTP API для categorize, analyze, generate_news
- AIAgentRemoteClient с automatic fallback
- 20 тестов

---

## 🔧 Ключевые изменения в v3.5.0 (2026-08-09)

### 1. 2FA авторизация (P0)
- TwoFactorAuthService (TOTP, QR-коды, резервные коды)
- Telegram хендлеры: /2fa setup, disable, status
- БД: totp_secret, totp_enabled, totp_backup_codes
- 17 тестов

### 2. Учёт регистра тэгов (P1)
- Case-insensitive: нормализация к lowercase
- Все репозитории: UserRepository, PostRepository, ChannelRepository, EventRepository
- 15 тестов

### 3. RSS парсинг (P1)
- feedparser для RSS 2.0, RSS 1.0, Atom 1.0
- Таблицы: rss_sources, rss_news
- Автопроверка каждые 5 минут (scheduler)
- 11 тестов

### 4. Web парсинг (P2)
- requests + bs4 для статических сайтов
- Таблицы: web_sources, web_news
- Конфигурация парсеров через JSON

### 5. Web админка (P2)
- FastAPI + JWT авторизация + 2FA
- 10 роутов: dashboard, news, channels, users, tasks, rss, web, console, settings
- HTML шаблоны с Tailwind CSS

### 6. Docker контейнеризация (P1)
- Dockerfile (multi-stage)
- docker-compose.yml (7 сервисов: app, web-admin, db, chromadb, ollama, redis, nginx)
- docker-compose.prod.yml с resource limits
- .dockerignore, nginx.conf, .env.example

---

## 🏗️ Архитектура (кратко)

```
main.py (Application)
├── Admin Bot (aiogram) + Web Admin (FastAPI)
├── Listener Bot (Telethon)
└── Scheduler + RSS/Web парсеры
        │
        ▼
NewsOrchestrator (3 стратегии: Urgent, Scheduled, Trusted)
        │
├── AI Agents (Categorizer → Analyst → Editor → Archivist)
├── Vector Search (ChromaDB + sentence-transformers)
└── LLM (Ollama, qwen2.5:7b)
```

### Модули

| Модуль | Ответственность |
|--------|----------------|
| **Core** | DI контейнер, DatabaseService |
| **Categorization** | Очередь, классификатор, процессор |
| **News** | Оркестратор, генерация, стратегии |
| **AI Agent** | 4 агента + EventBus + AgentQueue |
| **Auth** | 2FA (TOTP) |
| **RSS** | Парсинг RSS/Atom лент |
| **Web** | Парсинг сайтов (requests + bs4) |
| **Web Admin** | FastAPI + JWT + Tailwind CSS |
| **Bot** | Telegram бот (aiogram, 15+ handlers) |
| **Listener** | Telegram UserBot (Telethon) |
| **Scheduler** | Планировщик + RSS/Web задачи |
| **Vector Search** | ChromaDB, эмбеддинги |
| **Payment** | Платежи (Stars / Test) |

---

## 📊 База данных

### Таблицы (12)

| Таблица | Модель | Описание |
|---------|--------|----------|
| `channels` | Channel | Каналы Telegram (источники) |
| `posts` | TelegramPost | Посты из каналов |
| `generated_news` | GeneratedNews | Сгенерированные новости |
| `events` | EventContext | Контексты событий |
| `publishers` | Publisher | Каналы публикации |
| `users` | User | Пользователи (шифрование + 2FA) |
| `news_categories` | NewsCategory | Справочник категорий |
| `tasks` | Task | Задачи планировщика |
| `rss_sources` | RSSSource | RSS источники |
| `rss_news` | RSSNews | RSS новости |
| `web_sources` | WebSource | Web источники |
| `web_news` | WebNews | Web новости |

### 2FA поля в User
- `totp_secret` (VARCHAR 256) — TOTP секрет
- `totp_enabled` (BOOLEAN) — включена ли 2FA
- `totp_backup_codes` (TEXT) — JSON массив резервных кодов

---

## 🤖 AI Агенты

| Агент | Промпт | Задача |
|-------|--------|--------|
| **Categorizer** | `prompts/categorizer.txt` | Первичная классификация, очистка от рекламы |
| **Analyst** | `prompts/analyst.txt` | Оценка категории + confidence, тэгирование |
| **Editor** | `prompts/editor.txt` | Генерация новости в журналистском стиле |
| **Archivist** | `prompts/archivist.txt` | Структурирование контекста для векторного поиска |

### Модель
- **Основная:** `qwen2.5:7b` (Ollama, localhost:11434)

---

## ⚙️ Конфигурация

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `event_processing_interval_hours` | 48 | Интервал обработки событий |
| `agent_model` | `qwen2.5:7b` | Модель для AI агентов |
| `vector_search_events_limit` | 5 | Лимит похожих событий |
| `channel_trust_window_size` | 100 | Окно для расчёта рейтинга канала |
| `payment_provider` | `test` | Платёжный провайдер |
| `subscription_price_rub` | 99.0 | Цена подписки |
| `subscription_duration_days` | 30 | Длительность подписки |

---

## 🐳 Docker

### 7 сервисов
```
app         — основное приложение (8000)
web-admin   — Web админка (8001)
db          — PostgreSQL (5432)
chromadb    — ChromaDB (8002)
ollama      — Ollama (11434)
redis       — Redis (6379)
nginx       — Reverse Proxy (80)
```

### Быстрый старт
```bash
cp .env.example .env
nano .env  # заполнить TELEGRAM_BOT_TOKEN
docker-compose up -d
docker-compose exec app alembic upgrade head
docker-compose exec ollama ollama pull qwen2.5:7b
```

**Production:** `docker-compose -f docker-compose.prod.yml up -d`

---

## 🧪 Тестирование

- **Всего тестов:** 250+
- **Покрытие:** ~90%
- **Новые модули (v3.5.0):** 43 теста

### Запуск
```bash
pytest tests/ -v
pytest tests/ -v --cov=services --cov=database
```

---

## ⚠️ Известные проблемы

### 1. Глобальные функции доступа к боту
**Файл:** `services/bot/bot.py`  
**Проблема:** `get_bot_instance()` и `get_notification_service_ref()` в хендлерах  
**Статус:** Требуется значительный рефакторинг хендлеров

### 2. Web админка — incomplete
**Статус:** Базовая реализация, нужны CRUD для всех разделов и Dashboard

### 3. RSS/Web парсинг — Telegram хендлеры
**Статус:** Нужны команды /rss list, add, remove для управления

---

## 📚 Структура документации

```
PROJECT_CONTEXT.md      — этот файл (актуальный контекст)
README.md               — главная документация, быстрый старт, Docker
docs/
├── ARCHITECTURE.md     — детальная архитектура
├── DOCKER_SETUP_2026_08_09.md           — Docker
├── 2FA_IMPLEMENTATION_2026_08_09.md     — 2FA
├── TAGS_CASE_INSENSITIVE_2026_08_09.md  — учёт регистра
├── RSS_PARSING_IMPLEMENTATION_2026_08_09.md  — RSS парсинг
├── WEB_PARSING_BASE_2026_08_09.md       — Web парсинг
├── WEB_ADMIN_BASE_2026_08_09.md         — Web админка
├── LLM_CACHE_IMPLEMENTATION.md          — кэширование LLM
├── AUTO_REINDEX_IMPLEMENTATION.md       — автопереиндексация
├── MICROSERVICES_ARCHITECTURE.md        — микросервисы
├── POSTGRESQL_SETUP.md                  — PostgreSQL
├── ALEMBIC_SETUP.md                     — миграции
archive/                                 — устаревшие документы
archive_session_2026_08_09/              — сессионные отчёты
```

---

**Конец документа**  
*Версия: 3.5.0 | Обновлено: 2026-08-09 | 6/6 задач выполнено (100%)*