# News Aggregator

Автоматизированная система сбора, анализа и публикации новостей с использованием AI-агентов.

**Источники новостей:**
- Telegram-каналы (мониторинг через UserBot)
- RSS/Atom ленты (feedparser, 20+ лент)
- Web-сайты (requests + BeautifulSoup4)

**Версия:** 4.0.0  
**Последнее обновление:** 2026-08-11

---

### 📢 Новое в версии 4.0.0 (2026-08-11)

- ✅ **Глубокий рефакторинг архитектуры** — NewsOrchestrator, стратегии обработки, Event Bus
- ✅ **Listener Bot (Telethon)** — выделен в отдельный сервис, мониторинг Telegram
- ✅ **Модульная категоризация** — `services/telegram/categorization.py`
- ✅ **Улучшенная векторная поиск** — оптимизированный ChromaDB клиент, автопереиндексация
- ✅ **Расширенное тестирование** — тесты orchestrator, notification, direct news
- ✅ **Очистка кодовой базы** — удалены мёртвые файлы, упрощена структура

### 📢 Новое в версии 3.9.0 (2026-08-10)

- ✅ **Распределённая очередь (Redis/Celery)** — горизонтальное масштабирование, персистентность задач
- ✅ **Интеграционные тесты** — 70+ тестов с Ollama и ChromaDB, GitHub Actions CI/CD
- ✅ **Prometheus + Grafana** — полный мониторинг, 3 дашборда, 30+ алертов
- ✅ **AI-агенты микросервис** — отдельный сервис с HTTP API и automatic fallback

### 📢 Новое в версии 3.5.0 (2026-08-09)

- ✅ **2FA авторизация (TOTP)** — безопасность администраторов (Google Authenticator / Authy)
- ✅ **Учёт регистра тэгов** — case-insensitive поиск, нормализация к lowercase
- ✅ **RSS парсинг** — парсинг RSS/Atom лент (feedparser, 20+ лент, каждые 5 мин)
- ✅ **Web парсинг** — парсинг сайтов через requests + bs4
- ✅ **Web админка** — FastAPI + JWT + Tailwind CSS (базовая реализация)
- ✅ **Docker контейнеризация** — 7 сервисов, docker-compose для dev и prod

---

## 📋 Оглавление

- [Описание](#описание)
- [Архитектура](#архитектура)
- [Быстрый старт (Docker)](#быстрый-старт-docker)
- [Быстрый старт (вручную)](#быстрый-старт-вручную)
- [Конфигурация](#конфигурация)
- [AI Агенты](#ai-агенты)
- [Логика обработки](#логика-обработки)
- [Документация](#документация)
- [Тестирование](#тестирование)

---

## Описание

**News Aggregator** — это система для:
- Мониторинга Telegram-каналов в реальном времени
- Автоматической категоризации и оценки срочности новостей (1-5)
- Генерации сводных новостей через AI-агентов (Analyst → Editor → Archivist)
- Векторного поиска похожих событий (ChromaDB + sentence-transformers)
- Публикации в Telegram-каналы
- **Парсинга RSS/Atom лент** с автопроверкой каждые 5 минут
- **Парсинга веб-сайтов** через requests + BeautifulSoup4
- Web интерфейса администрирования (FastAPI)
- Управления подписками и платежами
- **2FA аутентификации** (TOTP) для администраторов

### Ключевые возможности

| Возможность | Описание |
|------------|----------|
| **Мониторинг** | Отслеживание Telegram-каналов через UserBot (Telethon) |
| **Категоризация** | AI-классификация новостей по категориям и срочности (1-5) |
| **Срочные новости** | Обработка новостей срочностью 4-5 немедленно |
| **Доверенные источники** | Публикация без модерации от проверенных каналов |
| **RSS парсинг** | Парсинг RSS/Atom лент (20+ лент, каждые 5 мин) |
| **Web парсинг** | Парсинг сайтов через requests + bs4 |
| **Векторный поиск** | Поиск похожих событий через ChromaDB |
| **AI-агенты** | 4 агента: Categorizer, Analyst, Editor, Archivist |
| **Подписки** | Платные подписки для пользователей (Telegram Stars) |
| **Прямая генерация** | Генерация новостей админом без источника |
| **2FA** | TOTP-аутентификация для администраторов |
| **Web админка** | FastAPI интерфейс с JWT + 2FA |

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│                    (точка входа, lifecycle)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│  Admin Bot    │   │   Listener Bot  │   │   Scheduler   │
│  (aiogram)    │   │   (Telethon)    │   │  + RSS парсер │
│  + Web Admin  │   │   + RSS/Web     │   │  + Web парсер │
└───────────────┘   └─────────────────┘   └───────────────┘
                           │                      │
        ┌──────────────────┴──────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NewsOrchestrator                              │
│           (делегирует обработку стратегиям)                      │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─────────────────┬─────────────────┬─────────────────────┐
        │                 │                 │                     │
        ▼                 ▼                 ▼                     ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐   ┌──────────────┐
│   Urgent      │ │  Scheduled    │ │   Trusted     │   │  Event Bus   │
│   Strategy    │ │  Strategy     │ │   Strategy    │   │  (priority)  │
└───────────────┘ └───────────────┘ └───────────────┘   └──────────────┘
                                                          │
                        ┌─────────────────────────────────┘
                        │
        ┌───────────────┼─────────────────┬───────────────┐
        ▼               ▼                 ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Categorization│ │    News      │ │   Vector     │ │  LLM Provider│
│   Module     │ │   Module     │ │   Search     │ │  (Ollama)    │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### Стек технологий v3.9.0

| Категория | Технология |
|-----------|-----------|
| **Telegram** | aiogram 3.x, Telethon 1.30+ |
| **Backend** | Python 3.12, FastAPI |
| **Web Admin** | FastAPI + JWT + Tailwind CSS |
| **ORM** | SQLAlchemy 2.0 + Alembic |
| **Database** | SQLite / PostgreSQL |
| **LLM** | Ollama (qwen2.5:7b), OpenAI (GPT-4o), Anthropic (Claude) |
| **Vector DB** | ChromaDB + sentence-transformers |
| **AI Agents** | Categorizer, Analyst, Editor, Archivist (+ микросервис) |
| **Queue** | Redis + Celery |
| **Container** | Docker + Docker Compose |
| **Monitoring** | Prometheus + Grafana |
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
| ChromaDB | http://localhost:8002 | 8002 |
| Ollama | http://localhost:11434 | 11434 |
| **Redis** | **localhost** | **6379** |
| **Prometheus** | **http://localhost:9090** | **9090** |
| **Grafana** | **http://localhost:3000** | **3000** |
| **AI Agent Service** | **http://localhost:8003** | **8002** |

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
git clone <repository-url>
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

---

## Конфигурация

### Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | `123456:ABC-DEF1234...` |
| `TELEGRAM_API_ID` | Telegram API ID | `12345678` |
| `TELEGRAM_API_HASH` | Telegram API hash | `abcdef123456...` |
| `ADMIN_ID` | Telegram ID администратора | `123456789` |
| `ENCRYPTION_KEY` | Ключ шифрования (32+ символа) | `your-secret-key...` |
| `DATABASE_URL` | PostgreSQL URL (опционально) | `postgresql+asyncpg://...` |
| `JWT_SECRET` | JWT секрет (для Web админки) | `openssl rand -hex 32` |

### Настройки ключей

| Настройка | По умолчанию | Описание |
|-----------|--------------|----------|
| `event_processing_interval_hours` | 48 | Интервал обработки событий |
| `agent_model` | `qwen2.5:7b` | Модель для AI агентов |
| `channel_trust_window_size` | 100 | Окно для расчёта рейтинга канала |
| `payment_provider` | `test` | Платёжный провайдер |

---

## AI Агенты

| Агент | Задача | Промпт |
|-------|--------|--------|
| **Categorizer** | Первичная классификация, фильтрация рекламы | `prompts/categorizer.txt` |
| **Analyst** | Оценка категории + confidence, тэгирование | `prompts/analyst.txt` |
| **Editor** | Генерация новости в журналистском стиле | `prompts/editor.txt` |
| **Archivist** | Структурирование контекста для векторного поиска | `prompts/archivist.txt` |

### Модель
- **Основная:** `qwen2.5:7b` (Ollama)

---

## Логика обработки

### Срочность 4-5 (срочные)
```
1. Пост получен
2. Проверка: is_trusted?
   ├─ Да → TrustedSourceStrategy → Analyst → Публикация
   └─ Нет → UrgentNewsStrategy → Analyst → EventBus → Editor → Archivist → Модерация
```

### Срочность 1-3 (несрочные)
```
1. Пост получен
2. CategorizationProcessor → AnalystAgent
3. ScheduledNewsStrategy → БД (checked_at=false)
4. Планировщик (задачи в БД, время из scheduled_at)
```

### RSS и Web парсинг
```
RSS/Web Parser → БД (rss_news / web_news)
    │
    ▼
AI Категоризация → Post (checked_at=false)
    │
    ▼
Планировщик → Editor → Archivist → Модерация
```

---

## Документация

### Основная

| Документ | Описание |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Детальная архитектура системы |
| [docs/DOCKER_SETUP_2026_08_09.md](docs/DOCKER_SETUP_2026_08_09.md) | Docker контейнеризация |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | История изменений проекта |

### v3.9.0 — Новые функции (2026-08-10)

| Документ | Описание |
|----------|----------|
| [docs/REDIS_QUEUE_SETUP.md](docs/REDIS_QUEUE_SETUP.md) | Распределённая очередь Redis/Celery |
| [docs/CI_CD_SETUP.md](docs/CI_CD_SETUP.md) | Интеграционные тесты и CI/CD |
| [docs/PROMETHEUS_GRAFANA_SETUP.md](docs/PROMETHEUS_GRAFANA_SETUP.md) | Мониторинг и алерты |
| [docs/AI_AGENT_MICROSERVICE.md](docs/AI_AGENT_MICROSERVICE.md) | AI-агенты микросервис |

### v3.5.0 — Новые функции

| Документ | Описание |
|----------|----------|
| [docs/2FA_IMPLEMENTATION_2026_08_09.md](docs/2FA_IMPLEMENTATION_2026_08_09.md) | 2FA авторизация (TOTP) |
| [docs/TAGS_CASE_INSENSITIVE_2026_08_09.md](docs/TAGS_CASE_INSENSITIVE_2026_08_09.md) | Учёт регистра тэгов |
| [docs/RSS_PARSING_IMPLEMENTATION_2026_08_09.md](docs/RSS_PARSING_IMPLEMENTATION_2026_08_09.md) | RSS парсинг |
| [docs/WEB_PARSING_BASE_2026_08_09.md](docs/WEB_PARSING_BASE_2026_08_09.md) | Web парсинг |
| [docs/WEB_ADMIN_BASE_2026_08_09.md](docs/WEB_ADMIN_BASE_2026_08_09.md) | Web админка |

### Миграции и инфраструктура

| Документ | Описание |
|----------|----------|
| [docs/POSTGRESQL_SETUP.md](docs/POSTGRESQL_SETUP.md) | Настройка PostgreSQL |
| [docs/ALEMBIC_SETUP.md](docs/ALEMBIC_SETUP.md) | Руководство по миграциям БД |
| [docs/LLM_CACHE_IMPLEMENTATION.md](docs/LLM_CACHE_IMPLEMENTATION.md) | Кэширование LLM |
| [docs/AUTO_REINDEX_IMPLEMENTATION.md](docs/AUTO_REINDEX_IMPLEMENTATION.md) | Автопереиндексация |
| [docs/MICROSERVICES_ARCHITECTURE.md](docs/MICROSERVICES_ARCHITECTURE.md) | Микросервисы (проект) |

---

## Тестирование

```bash
# Все тесты
pytest tests/ -v

# С покрытием
pytest tests/ -v --cov=services --cov=database

# Репозитории
pytest tests/test_repositories/ -v

# AI-агенты
pytest tests/test_agents/ -v

# RSS парсер
pytest tests/test_rss/ -v

# 2FA
pytest tests/test_auth/ -v
```

### Статистика тестов

| Категория | Тестов | Покрытие |
|-----------|--------|----------|
| **Всего тестов** | 237+ | ~90% |
| **Unit тесты** | 147 | 90% |
| **Интеграционные** | 70+ | 85% |
| **Микросервис** | 20+ | 85% |
| **Репозитории** | 29 | 90% |
| **2FA** | 17 | 100% |
| **Case-insensitive** | 15 | 100% |
| **RSS парсер** | 11 | 100% |
| **AI агенты** | 10+ | 85% |
| **Сервисы** | 50+ | 90% |

---

## 📝 Лицензия

MIT License

## 👥 Авторы

- PyPy-dot
- AI-агент Стефания