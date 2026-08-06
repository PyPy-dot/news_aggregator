# News Aggregator

Система автоматического сбора и обработки новостей из Telegram-каналов с AI-классификацией.

## 🚀 Быстрый старт

### Требования
- Python 3.12+
- Ollama (локальный сервер LLM)
- Telegram Bot Token
- Telegram API credentials

### Установка

1. **Клонируйте репозиторий:**
```bash
git clone <repository-url>
cd news_aggregator
```

2. **Создайте виртуальное окружение:**
```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

3. **Установите зависимости:**
```bash
pip install -r requirements.txt
```

4. **Настройте окружение:**
Создайте файл `.env`:
```env
# Telegram Bot
BOT_TOKEN=your_bot_token

# Ключ шифрования для user_id (обязательно замените на свой в продакшене!)
ENCRYPTION_KEY=your_secret_encryption_key_min_32_chars

# Telegram API (для UserBot)
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=+7xxxxxxxxxx

# Каналы
CHANNEL_ID=-100xxxxxxxxxx
PARSE_CHANNEL_ID=-100xxxxxxxxxx
```

> **Важно:** После первого запуска выполните `/start` в боте с аккаунта администратора, затем вручную добавьте роль `admin` в таблице `users` через SQL:
> ```sql
> UPDATE users SET role='admin', has_subscription=1, subscription_started_at=datetime('now'), subscription_ends_at=NULL WHERE user_id_encrypted='<encrypted_id>';
> ```
> Или используйте миграцию `migrate_add_users_table.py`, которая автоматически добавляет ADMIN_ID из .env как администратора.

5. **Запустите миграции:**
```bash
python -m database.migrate_add_analyzed_fields
python -m database.migrate_add_moderation_fields
python -m database.migrate_add_news_tables
python -m database.migrate_add_trust_fields
python -m database.migrate_update_news_schema
python -m database.migrate_add_users_table  # Новая миграция для пользователей
```

6. **Запустите Ollama:**
```bash
ollama serve
ollama pull qwen2.5:7b
```

7. **Запустите бота:**
```bash
python main.py
```

## 📊 Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                         main.py                          │
│  Запускает два асинхронных процесса параллельно          │
└─────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
┌───────────────────┐                   ┌───────────────────────┐
│   Bot (aiogram)   │                   │  ListenerBot          │
│   Telegram Bot    │                   │  (Telethon UserBot)   │
│   - Админка       │                   │  - Слушит каналы      │
│   - Управление    │                   │  - Ловит новые посты  │
└───────────────────┘                   └───────────────────────┘
                                                   │
                                                   ▼
                                        ┌───────────────────────┐
                                        │   AI Agents           │
                                        │   (Ollama + LLM)      │
                                        │   - Categorizer       │
                                        │   - Analyst           │
                                        │   - Editor            │
                                        │   - Archivist         │
                                        └───────────────────────┘
                                                   │
                                                   ▼
                                        ┌───────────────────────┐
                                        │   Scheduler           │
                                        │   - 09:00 МСК         │
                                        │   - 21:00 МСК         │
                                        └───────────────────────┘
                                                   │
                                                   ▼
                                        ┌───────────────────────┐
                                        │   Database            │
                                        │   (SQLite + SQLAlchemy)│
                                        │   - Channels          │
                                        │   - Posts             │
                                        │   - Events            │
                                        │   - GeneratedNews     │
                                        └───────────────────────┘
```

## 🤖 AI Агенты

### 1. Categorizer
**Задача:** Первичная классификация и очистка от рекламы
- Определяет категорию новости
- Оценивает срочность (1-5)
- Удаляет рекламные вставки

### 2. Analyst
**Задача:** Глубокий анализ и тэгирование
- Оценка категории + confidence (0.0-1.0)
- Определение: продолжение события или новое
- Извлечение тэгов (5-10 штук)

### 3. Editor
**Задача:** Генерация новости в журналистском стиле
- Заголовок (до 80 символов)
- Текст (200-400 слов)
- Саммари (1 предложение)
- Тэги новости (3-5 штук)

### 4. Archivist
**Задача:** Структурирование контекста
- Выжимка для векторного поиска
- Контекст события (участники, место, последствия)
- Связи с другими событиями

## 📁 Структура проекта

```
news_aggregator/
├── main.py                 # Точка входа
├── config/
│   ├── __init__.py
│   └── settings.py         # Настройки (pydantic)
│
├── database/
│   ├── __init__.py
│   ├── models.py           # SQLAlchemy модели
│   ├── factory.py          # Фабрика репозиториев
│   ├── repositories/       # Repository pattern
│   │   ├── base.py
│   │   ├── channels.py
│   │   ├── posts.py
│   │   ├── events.py
│   │   └── news.py
│   └── migrate_*.py        # Миграции БД
│
├── services/
│   ├── ai_agent/
│   │   ├── agents/         # AI агенты
│   │   │   ├── base.py
│   │   │   ├── categorizer.py
│   │   │   ├── analyst.py
│   │   │   ├── editor.py
│   │   │   └── archivist.py
│   │   ├── events.py       # Система событий
│   │   └── routers.py      # EventBus
│   │
│   ├── bot/                # Telegram бот
│   │   ├── handlers/
│   │   └── utils.py
│   │
│   ├── listener/           # UserBot (Telethon)
│   └── scheduler/          # Планировщик
│
├── prompts/                # Промпты для AI
│   ├── categorizer.txt
│   ├── analyst.txt
│   ├── editor.txt
│   └── archivist.txt
│
├── tests/                  # Тесты
│   ├── conftest.py
│   ├── test_agents/
│   ├── test_repositories/
│   └── test_scheduler/
│
└── .env                    # Переменные окружения
```

## 📋 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/get_photo_id` | Получить ID фото |
| `/edit_channels` | Добавить/удалить канал |
| `/trusted_channels` | Управление доверенными источниками |
| `/last_posts` | Последние посты |
| `/generated_news` | Сгенерированные новости |
| `/pending_moderation` | Новости на модерации |
| `/approve_news <ID>` | Одобрить новость |
| `/reject_news <ID>` | Отклонить новость |

## 🧪 Тесты

### Запуск тестов:
```bash
pytest tests/ -v
```

### Запуск с покрытием:
```bash
pytest tests/ -v --cov=services --cov=database
```

### Запуск конкретных тестов:
```bash
pytest tests/test_repositories/test_channels.py -v
pytest tests/test_agents/test_base_agent.py -v
```

## 🔧 Конфигурация

### Переменные окружения (.env)

| Переменная | Описание | Пример |
|------------|----------|--------|
| `BOT_TOKEN` | Токен Telegram бота | `123456:ABC-DEF1234...` |
| `ENCRYPTION_KEY` | Ключ шифрования user_id (мин. 32 символа) | `my_secret_key_32chars_minimum` |
| `API_ID` | API ID Telegram | `39156045` |
| `API_HASH` | API Hash Telegram | `6a097519dfd5...` |
| `PHONE_NUMBER` | Номер для UserBot | `+79619357425` |
| `CHANNEL_ID` | ID канала для публикаций | `-1004463318403` |
| `PARSE_CHANNEL_ID` | ID канала для парсинга | `-1001973203607` |

> **Примечание:** `ADMIN_ID` больше не используется — администраторы управляются через таблицу `users` в БД. Для первоначальной настройки используйте миграцию `migrate_add_users_table.py`, которая автоматически добавляет администратора из переменной `ADMIN_ID` (если она указана в .env для обратной совместимости).

### Настройки планировщика

В `config/settings.py` можно изменить:
- `morning_hour` — час утреннего запуска (по умолчанию 9)
- `evening_hour` — час вечернего запуска (по умолчанию 21)

## 📊 Логика обработки новостей

### Срочность 4-5 (срочные)
```
1. Пост получен
2. Проверка: is_trusted?
   ├─ Да → Сразу публикация (approved)
   └─ Нет → Админу на модерацию (pending)
```

### Срочность 1-3 (несрочные)
```
1. Пост получен
2. Сохранение в БД (ожидает планировщика)
3. Планировщик (09:00 или 21:00 МСК):
   ├─ Запуск АРА (Аналитик → Редактор → Архивариус)
   ├─ Сохранение новости
   └─ Админу на модерацию
```

## 🎯 Рефакторинг

Проект прошёл полный рефакторинг:
- ✅ AI агенты разделены на 5 модулей
- ✅ Repository Pattern для БД
- ✅ Конфигурация на pydantic-settings
- ✅ Типизация всех функций
- ✅ Тесты (pytest)

Подробности в [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)

## 🔍 Векторный поиск

Проект включает систему векторного поиска для нахождения похожих событий и новостей.

### Архитектура

```
services/vector_search/
├── embeddings.py        # SentenceTransformers эмбеддинги
├── chroma_client.py     # ChromaDB хранилище
├── search_engine.py     # Высокоуровневый API поиска
└── __init__.py
```

### Компоненты

| Компонент | Описание |
|-----------|----------|
| **EmbeddingService** | Генерация эмбеддингов через sentence-transformers (модель: paraphrase-multilingual-MiniLM-L12-v2) |
| **ChromaVectorStore** | Постоянное хранение векторов в ChromaDB |
| **VectorSearchEngine** | API для поиска похожих событий/новостей/постов |

### Использование

```python
from services.vector_search import VectorSearchEngine

# Инициализация
search_engine = VectorSearchEngine()

# Добавление события
search_engine.add_event(
    id="event_123",
    text="Описание события...",
    event_category="politics",
    post_id=456,
    summary="Краткая выжимка",
    tags=["тег1", "тег2"],
)

# Поиск похожих событий
similar = search_engine.find_similar_events(
    query_text="Землетрясение в регионе",
    category_filter="disaster",
    limit=5,
    min_score=0.7,
)

# Статистика
stats = search_engine.get_stats()
# {'events': 10, 'news': 5, 'posts': 20}
```

### Интеграция с обработкой новостей

Векторный поиск автоматически интегрирован в обработку новостей через:
- `services/listener/helpers.py` — функции `find_similar_events()`, `find_similar_posts()`
- `services/ai_agent/vector_routers.py` — обработчики EventBus
- `services/listener/bot.py` — регистрация обработчиков

### Зависимости

```bash
pip install sentence-transformers chromadb
```

Модель загружается автоматически при первом запуске (~400 MB).

### Хранилище

Векторы хранятся в папке `vector_store/` (создаётся автоматически).

---

## 📊 Логирование

Проект использует централизованную систему логирования.

### Настройка

Логирование настраивается в `main.py`:

```python
from services.logging_config import setup_logging

setup_logging(
    level=logging.INFO,
    log_to_file=True,
    max_bytes=10 * 1024 * 1024,  # 10 MB
    backup_count=7
)
```

### Лог-файлы

- Расположение: `logs/news_aggregator_YYYY-MM-DD.log`
- Ротация: при достижении 10 MB
- Хранение: 7 последних файлов

### Использование в модулях

```python
from services import get_logger

logger = get_logger(__name__)
logger.info("Сообщение")
logger.error("Ошибка", exc_info=True)
```

### Утилиты логирования

```python
from services import log_error, ExecutionTimer

# Логирование ошибки с трассировкой
try:
    risky_operation()
except Exception as e:
    log_error(e, context={'user_id': 123})

# Замер времени выполнения
with ExecutionTimer("operation_name"):
    perform_operation()
```

---

## 🚀 CI/CD

Проект использует GitHub Actions для автоматического тестирования.

### Workflow

При push/PR запускаются:

1. **Linting & Type Checking**
   - Ruff (lint + format)
   - MyPy (type checking)

2. **Tests**
   - pytest с покрытием
   - Coverage report

3. **Security Scan** (только PR)
   - Проверка зависимостей на уязвимости

4. **Build Check**
   - Проверка импортов

### Запуск локально

```bash
# Linting
ruff check .
ruff format . --check

# Type checking
mypy . --ignore-missing-imports

# Tests
pytest tests/ -v --cov=services --cov=database
```

### Конфигурация

- `pyproject.toml` — настройки Ruff
- `mypy.ini` — настройки MyPy
- `.github/workflows/ci.yml` — workflow GitHub Actions

## 📝 Лицензия

MIT License

## 👥 Авторы

- PyPy-dot

## 📝 Лицензия

MIT License

## 👥 Авторы

- PyPy-dot
