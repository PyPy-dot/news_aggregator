# История проекта News Aggregator

## Финальная сводка (v1.0)

**Статус:** Готов к продакшену

Проект прошёл полный цикл рефакторинга и готов к использованию.

### Что было сделано

#### Фаза 1: Рефакторинг AI агентов
- ✅ Разделены на 5 отдельных модулей
- ✅ Создан базовый класс `BaseAgent`
- ✅ Добавлена типизация всех функций
- ✅ Улучшена обработка ошибок

#### Фаза 2: Конфигурация
- ✅ Переезд на pydantic-settings
- ✅ Централизованное управление настройками
- ✅ Валидация при старте
- ✅ Автодополнение в IDE

#### Фаза 3: Repository Pattern
- ✅ 5 репозиториев по доменам
- ✅ Базовый класс `BaseRepository`
- ✅ Фабрика репозиториев
- ✅ Удалён `database/requests.py`

#### Фаза 4: Планировщик
- ✅ Обновлён для использования репозиториев
- ✅ Явные зависимости
- ✅ Улучшена обработка ошибок

#### Фаза 5: Telegram бот
- ✅ Создан `services/bot/utils.py`
- ✅ Обновлены `commands.py`
- ✅ Добавлены команды модерации

#### Фаза 6: Тесты
- ✅ Настроен pytest
- ✅ Тесты репозиториев (channels, posts)
- ✅ Тесты базового агента
- ✅ Тесты планировщика
- ✅ Фикстуры и моки

#### Фаза 7: Документация
- ✅ README.md — полное руководство
- ✅ REFACTORING_PLAN.md — план рефакторинга
- ✅ REFACTORING_SUMMARY.md — итоги рефакторинга
- ✅ FINAL_SUMMARY.md — эта сводка

#### Фаза 8: Очистка
- ✅ Удалён `services/ai_agent/bot.py`
- ✅ Удалён `database/requests.py`
- ✅ Обновлён `services/util.py`

### Итоговая структура

```
news_aggregator/
├── main.py                      # Точка входа
├── README.md                    # Документация
├── .env                         # Переменные окружения
│
├── config/                      # ✅ Novoе
│   ├── __init__.py
│   └── settings.py              # Pydantic настройки
│
├── database/
│   ├── __init__.py
│   ├── models.py                # SQLAlchemy модели
│   ├── factory.py               # Фабрика репозиториев
│   ├── repositories/            # ✅ Novoе
│   │   ├── base.py
│   │   ├── channels.py
│   │   ├── posts.py
│   │   ├── events.py
│   │   └── news.py
│   └── migrate_*.py             # Миграции БД
│
├── services/
│   ├── ai_agent/
│   │   ├── agents/              # ✅ Novoе
│   │   │   ├── base.py
│   │   │   ├── categorizer.py
│   │   │   ├── analyst.py
│   │   │   ├── editor.py
│   │   │   └── archivist.py
│   │   ├── events.py
│   │   └── routers.py
│   │
│   ├── bot/
│   │   ├── utils.py             # ✅ Novoе
│   │   └── handlers/
│   │       ├── commands.py      # ✅ Обновлён
│   │       └── ...
│   │
│   ├── listener/
│   │   └── bot.py               # ✅ Обновлён
│   │
│   └── scheduler/
│       └── scheduler.py         # ✅ Обновлён
│
├── prompts/
│   ├── categorizer.txt
│   ├── analyst.txt
│   ├── editor.txt
│   └── archivist.txt
│
├── tests/                       # ✅ Novoе
│   ├── conftest.py
│   ├── test_agents/
│   │   └── test_base_agent.py
│   ├── test_repositories/
│   │   ├── test_channels.py
│   │   └── test_posts.py
│   └── test_scheduler/
│       └── test_scheduler.py
│
└── docs/
    ├── REFACTORING_PLAN.md
    ├── REFACTORING_SUMMARY.md
    └── FINAL_SUMMARY.md
```

### Метрики

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| Самый большой файл | 500+ строк | ~150 строк | **3x меньше** |
| AI агентов в одном файле | 4 | 0 | **Разделены** |
| Репозиториев | 0 | **5** | ✅ |
| Тестов | 0 | **15+** | ✅ |
| Типизация | ~30% | **100%** | ✅ |
| Документация | Минимальная | **Полная** | ✅ |

---

## Рефакторинг AI агентов и архитектуры

### Цели рефакторинга

1. **Устранить дублирование** — повторяющийся код в обработчиках
2. **Улучшить архитектуру** — чёткое разделение ответственности
3. **Добавить типизацию** — type hints для всех функций
4. **Упростить тестирование** — dependency injection
5. **Улучшить логирование** — единый формат, разные уровни
6. **Добавить обработку ошибок** — graceful degradation

### Приоритеты

#### Критический (ломает архитектуру)

| Файл | Проблема | Решение |
|------|----------|---------|
| `services/listener/bot.py` | "Божественный" класс — 450+ строк | Разделить на модули: `handlers/`, `processors/` |
| `services/ai_agent/bot.py` | 4 агента в одном файле | Вынести в отдельные файлы |
| `database/requests.py` | 500+ строк, смешаны обязанности | Разделить по доменам: posts, events, news |

### Новая структура проекта (план)

```
news_aggregator/
├── main.py
├── config/
│   ├── __init__.py
│   ├── settings.py          # Настройки из env
│   └── constants.py         # Константы (таймауты, лимиты)
│
├── database/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy модели
│   ├── engine.py            # Движок БД, сессии
│   └── repositories/        # Repository pattern
│       ├── __init__.py
│       ├── base.py          # Базовый репозиторий
│       ├── channels.py      # Каналы
│       ├── posts.py         # Посты
│       ├── events.py        # События
│       └── news.py          # Новости
│
├── services/
│   ├── ai_agent/
│   │   ├── __init__.py
│   │   ├── base.py          # Базовый агент
│   │   ├── agents/          # Специализированные агенты
│   │   │   ├── __init__.py
│   │   │   ├── categorizer.py
│   │   │   ├── analyst.py
│   │   │   ├── editor.py
│   │   │   └── archivist.py
│   │   ├── events.py        # Система событий
│   │   └── routers.py       # EventBus
│   │
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── bot.py           # Telegram bot
│   │   ├── config.py        # Конфиг бота
│   │   ├── keyboards/       # Клавиатуры
│   │   │   ├── __init__.py
│   │   │   ├── inline.py
│   │   │   └── reply.py
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── commands.py
│   │       ├── messages.py
│   │       ├── callbacks.py
│   │       └── states.py
│   │
│   ├── listener/
│   │   ├── __init__.py
│   │   ├── bot.py           # UserBot
│   │   ├── config.py
│   │   └── handlers/        # Обработчики событий
│   │       ├── __init__.py
│   │       └── new_message.py
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── scheduler.py     # Планировщик
│   │   └── strategies/      # Стратегии обработки
│   │       ├── __init__.py
│   │       ├── urgent.py    # Срочные новости
│   │       └── scheduled.py # Плановые новости
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py       # Настройка логирования
│       ├── text.py          # Утилиты текста
│       └── time.py          # Утилиты времени
│
├── prompts/
│   ├── categorizer.txt
│   ├── analyst.txt
│   ├── editor.txt
│   └── archivist.txt
│
├── migrations/              # Скрипты миграций
│   └── ...
│
└── tests/                   # Тесты
    ├── __init__.py
    ├── conftest.py
    ├── test_analyst.py
    ├── test_editor.py
    └── test_scheduler.py
```

### Ключевые изменения

#### 1. Repository Pattern для БД

**Было:**
```python
# database/requests.py
async def add_tg_post(channel_id, text, category, urgency):
    async with async_session() as session:
        # ... 50 строк кода
```

**Стало:**
```python
# database/repositories/posts.py
class PostRepository(BaseRepository):
    async def create(self, post_data: PostCreate) -> TelegramPost:
        """Создать новый пост"""
        post = TelegramPost(**post_data.dict())
        self.session.add(post)
        await self.session.commit()
        return post
    
    async def get_unanalyzed(self, hours: int = 48) -> list[TelegramPost]:
        """Получить необработанные посты"""
        # ...
```

**Преимущества:**
- ✅ Единый интерфейс для всех операций
- ✅ Легко тестировать (mock репозитория)
- ✅ Группировка по доменам

#### 2. Dependency Injection для агентов

**Было:**
```python
class ListenerBot:
    def __init__(self):
        self.analyst_agent = AnalystAgent()
        self.editor_agent = EditorAgent()
```

**Стало:**
```python
class ListenerBot:
    def __init__(
        self,
        analyst: AnalystAgent,
        editor: EditorAgent,
        archivist: ArchivistAgent,
    ):
        self.analyst = analyst
        self.editor = editor
        self.archivist = archivist
```

**Преимущества:**
- ✅ Легко подменять агенты моками
- ✅ Явные зависимости
- ✅ Проще тестировать

---

## Итоги рефакторинга

### Выполненные изменения

#### 1. AI Agents — разделение на модули

**Было:**
```
services/ai_agent/bot.py (450+ строк, 4 агента в одном файле)
```

**Стало:**
```
services/ai_agent/agents/
├── __init__.py
├── base.py           # Базовый класс BaseAgent
├── categorizer.py    # CategorizerAgent
├── analyst.py        # AnalystAgent
├── editor.py         # EditorAgent
└── archivist.py      # ArchivistAgent
```

**Преимущества:**
- ✅ Каждый агент в отдельном файле (~100 строк)
- ✅ Базовый класс переиспользуется
- ✅ Легко тестировать по отдельности
- ✅ Понятная структура для новых разработчиков

#### 2. Configuration — pydantic-settings

**Было:**
```python
# Разрозненные конфиги в разных файлах
import services.listener.config as conf
BOT_TOKEN = "..."
```

**Стало:**
```
config/
├── __init__.py
└── settings.py  # Settings на pydantic
```

**Использование:**
```python
from config import settings

settings.bot_token
settings.admin_id
settings.api_id
settings.model_name
settings.morning_hour  # 9 (утренний запуск)
settings.evening_hour  # 21 (вечерний запуск)
```

**Преимущества:**
- ✅ Типизация всех настроек
- ✅ Валидация при старте
- ✅ Автодополнение в IDE
- ✅ Единый источник истины

#### 3. Database — Repository Pattern

**Было:**
```
database/requests.py (500+ строк, все функции в одном файле)
```

**Стало:**
```
database/
├── __init__.py
├── models.py
├── factory.py
└── repositories/
    ├── __init__.py
    ├── base.py           # BaseRepository
    ├── channels.py       # ChannelRepository
    ├── posts.py          # PostRepository
    ├── events.py         # EventRepository
    └── news.py           # NewsRepository
```

**Использование:**
```python
from database import RepositoryFactory, async_session

factory = RepositoryFactory(async_session())

# Каналы
channels_repo = factory.channels()
channel = await channels_repo.get_by_telegram_id(channel_id)
await channels_repo.set_trusted(channel_id, True)

# Посты
posts_repo = factory.posts()
unanalyzed = await posts_repo.get_unanalyzed(hours=48)
await posts_repo.mark_analyzed(post_id, news_id)

# События
events_repo = factory.events()
events = await events_repo.get_for_scheduler(hours=48)
await events_repo.mark_processed(event_id)

# Новости
news_repo = factory.news()
pending = await news_repo.get_pending(limit=20)
await news_repo.approve(news_id, admin_id)
```

**Преимущества:**
- ✅ Разделение по доменам
- ✅ Единый интерфейс для всех операций
- ✅ Легко мокать для тестов
- ✅ Меньше конфликтов при слиянии

---

## Реализация системы АРА + Планировщик + Модерация

### Архитектура v2

#### Основные изменения:
1. **3 специализированных агента (АРА)**: Аналитик → Редактор → Архивариус
2. **Планировщик**: обработка новостей 2 раза в сутки (09:00 и 21:00 МСК)
3. **Срочные новости (4-5)**: обходят планировщик, обрабатываются немедленно
4. **Модерация**: все новости идут на модерацию админу перед публикацией
5. **Тэгирование**: автоматические тэги для новостей и событий

### Полный пайплайн обработки

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ListenerBot получает пост из Telegram                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Категоризация (быстрый агент, 1 запрос к LLM)                │
│    - Определяет категорию и срочность (1-5)                     │
│    - Очищает текст от рекламы                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
              Срочность 4-5       Срочность 1-3
                    │                   │
                    ▼                   ▼
┌─────────────────────────┐   ┌─────────────────────────────────┐
│ 3a. НЕМЕДЛЕННАЯ         │   │ 3b. ПЛАНИРОВЩИК                 │
│     обработка           │   │     - Ждёт 09:00 или 21:00 МСК  │
│     (обход планировщика)│   │     - Собирает пачку новостей   │
│                         │   │     - Запускает АРА             │
└─────────────────────────┘   └─────────────────────────────────┘
                    │                   │
                    └─────────┬─────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. АРА (Аналитик → Редактор → Архивариус)                       │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Агент 1: Аналитик (2 сек, 800 токенов)                      │ │
│ │ - Оценка категории + confidence (0.0-1.0)                   │ │
│ │ - Определение: продолжение или новое событие                │ │
│ │ - Тэги поста (5-10 штук)                                    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Агент 2: Редактор (3 сек, 1200 токенов)                     │ │
│ │ - Генерация новости (200-400 слов)                          │ │
│ │ - Заголовок (до 80 символов)                                │ │
│ │ - Саммари (1 предложение)                                   │ │
│ │ - Тэги новости (3-5 штук)                                   │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Агент 3: Архивариус (2 сек, 600 токенов)                    │ │
│ │ - Выжимка для векторного поиска (50-100 слов)               │ │
│ │ - Структурирование контекста                                │ │
│ │ - Тэги события (5-10 штук)                                  │ │
│ │ - Связи с другими событиями                                 │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Сохранение в БД                                              │
│    - posts (с category_confidence, tags)                        │
│    - events (с context_data, tags, summary)                     │
│    - generated_news (со статусом pending)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Уведомление админу на модерацию                              │
│    - Новость ждёт подтверждения (approved/rejected)             │
│    - ID админа: из env (ADMIN_ID=400233435)                     │
└─────────────────────────────────────────────────────────────────┘
```

### Три агента (АРА)

#### Агент 1: Аналитик
**Промпт:** `prompts/analyst.txt`

**Задачи:**
1. Оценка категории + confidence (0.0-1.0)
2. Определение: продолжение события или новое
3. Тэги поста (5-10 штук)

**Выход:**
```json
{
    "category": "Политика",
    "confidence": 0.85,
    "is_continuation": true,
    "related_event_id": 42,
    "post_tags": ["Зеленский", "США", "помощь"]
}
```

#### Агент 2: Редактор
**Промпт:** `prompts/editor.txt`

**Задачи:**
1. Генерация новости (200-400 слов)
2. Заголовок (до 80 символов)
3. Саммари (1 предложение)
4. Тэги новости (3-5 штук)

**Выход:**
```json
{
    "title": "Зеленский обсудил помощь с США",
    "text": "Президент Украины...",
    "summary": "Зеленский встретился с советником США.",
    "news_tags": ["Зеленский", "США", "помощь"]
}
```

#### Агент 3: Архивариус
**Промпт:** `prompts/archivist.txt`

**Задачи:**
1. Выжимка для векторного поиска (50-100 слов)
2. Структурирование контекста
3. Тэги события (5-10 штук)
4. Связи с другими событиями

**Выход:**
```json
{
    "embedding_text": "Текст для эмбеддинга...",
    "event_description": "Встреча Зеленского с США",
    "participants": ["Зеленский", "Советник США"],
    "location": "Киев",
    "tags": ["Зеленский", "США", "встреча"],
    "related_event_ids": [42, 43]
}
```

---

## Реализация очереди и системы генерации новостей

### Архитектурные изменения

#### 1. Очередь категоризации (пропускная способность: 2 запроса)
**Файл:** `services/listener/bot.py`

**Реализация:**
- `deque(maxlen=10)` — очередь задач на категоризацию
- `_process_categorization_queue()` — асинхронный обработчик очереди
- Обработка задач по мере поступления, без блокировки основного потока

#### 2. Новые таблицы БД

##### `channels.tags` (TEXT, default '[]')
**Назначение:** JSON-список категорий, которые публикует канал

##### `posts.category_confidence` (FLOAT, default 0.0)
**Назначение:** Оценка правильности категории от валидатора (0.0-1.0)

##### `events` — Контекст события
**Поля:**
- `id` — PRIMARY KEY
- `post_id` — FOREIGN KEY → posts(id)
- `context_data` — JSON строка с контекстом
- `event_category` — категория для группировки
- `created_at` — timestamp

##### `generated_news` — Сгенерированные ЛЛМ новости
**Поля:**
- `id` — PRIMARY KEY
- `text` — сгенерированный текст новости
- `source_post_ids` — JSON список ID постов `[1, 2, 3]`
- `source_event_ids` — JSON список ID событий `[1, 2]`
- `category` — категория сгенерированной новости
- `created_at` — timestamp

---

## Улучшения проекта

### 1. Централизованное логирование

**Файлы:**
- `services/logging_config.py` — модуль настройки логирования
- `services/util.py` — утилиты логирования
- `services/__init__.py` — экспорты

**Возможности:**
- Консольный и файловый хендлеры
- Ротация логов (10 MB, 7 файлов)
- Контекстный менеджер для временного изменения уровня
- Утилиты: `log_error()`, `ExecutionTimer`

**Использование:**
```python
from services import setup_logging, get_logger, ExecutionTimer

setup_logging(level=logging.INFO, log_to_file=True)
logger = get_logger(__name__)

with ExecutionTimer("operation"):
    perform_operation()
```

### 2. Векторный поиск

**Файлы:**
- `services/vector_search/embeddings.py` — SentenceTransformers эмбеддинги
- `services/vector_search/chroma_client.py` — ChromaDB хранилище
- `services/vector_search/search_engine.py` — высокоуровневый API
- `services/ai_agent/vector_routers.py` — обработчики EventBus

**Возможности:**
- Генерация эмбеддингов (модель: paraphrase-multilingual-MiniLM-L12-v2)
- Постоянное хранение в ChromaDB
- Поиск похожих событий/новостей/постов
- Фильтрация по категории и порогу сходства

**Использование:**
```python
from services.vector_search import VectorSearchEngine

search_engine = VectorSearchEngine()

# Добавление события
search_engine.add_event(
    id="event_123",
    text="Описание события...",
    event_category="politics",
    post_id=456,
)

# Поиск похожих
similar = search_engine.find_similar_events(
    query_text="Землетрясение",
    category_filter="disaster",
    min_score=0.7,
)
```

### 3. CI/CD (GitHub Actions)

**Workflow включает:**

| Stage | Описание |
|-------|----------|
| **Linting** | Ruff check + format |
| **Type Checking** | MyPy строгая проверка |
| **Tests** | pytest с coverage |
| **Security Scan** | проверка уязвимостей (PR) |
| **Build Check** | проверка импортов |

---

## Реализация Publisher функционала

### Выполненные изменения

#### 1. База данных

**Модели:**
- ✅ Таблица `Publisher` — каналы для публикации
- ✅ Обновлена `GeneratedNews`: `bypass_ara`, `publisher_channel_id`, `published_at`
- ✅ Обновлена `TelegramPost`: `bypass_ara`, `publisher_channel_id`

**Репозиторий:**
- ✅ `database/repositories/publishers.py` — CRUD операции для Publisher

#### 2. Telegram бот

**Хендлеры:**
- ✅ `services/bot/handlers/publishers.py` — управление каналами публикации
- ✅ `/publishers` — меню управления
- ✅ Добавление канала (через `KeyboardButtonRequestChat`)
- ✅ Просмотр списка каналов
- ✅ Активация/деактивация

#### 3. Прямая генерация новостей админом

**Логика работы:**
1. Админ нажимает "✍️ Прямая генерация новости" или вводит `/direct_news`
2. Вводит описание новости (текст, анонс, реклама)
3. Бот отправляет описание LLM (только **EditorAgent**)
4. LLM генерирует новость в журналистском стиле
5. Админ выбирает канал для публикации
6. Новость публикуется и сохраняется в БД с флагом `bypass_ara=True`

**Особенности:**
- ✅ Не участвуют Analyst и Archivist
- ✅ Только EditorAgent для генерации текста
- ✅ Флаг `bypass_ara=True` — новость обошла полный цикл АРА
- ✅ Сохранение в БД с указанием канала публикации
- ✅ Поддержка фото/видео (опционально)

---

## Архитектурные принципы

1. **SOLID** — каждый класс отвечает за одну задачу
2. **DRY** — базовые классы для переиспользования
3. **KISS** — простые решения
4. **Явное лучше неявного** — явные зависимости
5. **Тестируемость** — моки и фикстуры
