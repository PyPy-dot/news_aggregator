# Мульти-источниковая категоризация — реализация v4.2.0

**Дата:** 2026-08-17
**Статус:** ✅ Выполнено

---

## 📋 Обзор

Все три источника новостей (Telegram, RSS, Web) проходят через **единый пайплайн**
категоризации. Каждый источник хранит сырые данные в своей таблице, обогащается
через общую очередь, а затем объединяется в сводки через Orchestrator.

### До рефакторинга

```
Telegram:  Listener → Queue → Categorizer → Analyst → posts (checked_at=False) → Orchestrator
RSS:       Parser → rss_news → direct AI → posts (channel_id=-1001)  → сломанный путь
Web:       Parser → web_news → НЕ ПОДКЛЮЧЁН
```

### После рефакторинга

```
Telegram:  Listener → Queue → Categorizer → Analyst → posts (checked_at=False)
RSS:       Parser → rss_news → Queue → Categorizer → Analyst → rss_news (enriched)
Web:       Parser → web_news → Queue → Categorizer → Analyst → web_news (enriched)
                                                              │
                                                              ▼
                                               ┌─────────────────────────┐
                                               │    Orchestrator (batch)  │
                                               │  собирает из всех 3     │
                                               │  таблиц по категории    │
                                               └───────────┬─────────────┘
                                                           │
                                              Vector Search (events)
                                                 Editor → сводка
                                               Archivist → контекст
                                                           │
                                              generated_news
                                            source_ids: ["tg_5", "rss_13", "web_10"]
```

---

## 🗄️ Схема БД

### Таблицы «сырых» новостей (параллельные, не связанные FK)

| Таблица | Источник | Флаг «необработана» |
|---------|----------|---------------------|
| `posts` | Telegram | `checked_at = False` |
| `rss_news` | RSS | `processed = False` AND `category IS NOT NULL` |
| `web_news` | Web | `processed = False` AND `category IS NOT NULL` |

### Новые поля

| Таблица | Поле | Тип | Описание |
|---------|------|-----|----------|
| `generated_news` | `source_ids` | TEXT (JSON) | `["tg_5", "rss_13", "web_10"]` |
| `events` | `source_news_ids` | TEXT (JSON) | `["tg_5", "rss_13"]` — новости на основе которых создан контекст |
| `events` | `post_id` | INTEGER (nullable) | Больше без FK к `TelegramPost` |
| `rss_news` | `urgency` | INTEGER | Срочность 1-5 от AI |
| `rss_news` | `category_confidence` | REAL | Уверенность категории |
| `rss_news` | `rate` | INTEGER | Рейтинг 0-100 |
| `rss_news` | `generated_news_id` | INTEGER | ID сводки, в которую вошла |
| `web_news` | `urgency` | INTEGER | Аналогично |
| `web_news` | `category_confidence` | REAL | Аналогично |
| `web_news` | `rate` | INTEGER | Аналогично |
| `web_news` | `generated_news_id` | INTEGER | Аналогично |

---

## 🔄 Пайплайн обработки

### Шаг 1: Парсинг

Каждый источник парсит новости в свою таблицу:

- **Telegram:** `ListenerBot → CategorizationQueue.add(task)` — напрямую в очередь
- **RSS:** `Scheduler._run_rss_parser()` → `RSSProcessorService.parse_source()` → `rss_news`
- **Web:** `Scheduler._run_web_parser()` → `WebProcessorService.parse_source()` → `web_news`

### Шаг 2: Отправка в очередь категоризации

```python
# Telegram — напрямую
task = CategorizationTask(
    source_type='telegram',
    channel_id=channel_id,
    prompt=text,
    original_text=text,
    title=channel_title,
    desc=channel_desc,
)

# RSS
task = CategorizationTask(
    source_type='rss',
    source_id=rss_news.id,   # ID в rss_news
    prompt=f"{title}\n\n{description}",
    original_text=...,
    title=source.name,
    desc=source.description,
)

# Web
task = CategorizationTask(
    source_type='web',
    source_id=web_news.id,   # ID в web_news
    prompt=f"{title}\n\n{description}",
    original_text=...,
    title=source.name,
    desc=source.description,
)
```

### Шаг 3: CategorizationProcessor

```python
async def process(self, task: CategorizationTask):
    ai_response = await self.categorizer.send_question(task.prompt)
    classification = self.classifier.parse_ai_response(ai_response)

    if classification.is_advertisement:
        return  # пропуск

    if classification.urgency >= 4:
        await self._handle_urgent_news(task, classification)
    else:
        await self._handle_scheduled_news(task, classification)
```

Для Telegram: полная логика (создание поста → Analyst → публикация/уведомления).
Для RSS/Web: обновление сырой таблицы (`update_category()`) + Analyst для тегов/confidence.

### Шаг 4: Orchestrator — плановая обработка

Каждый раз, когда scheduler запускает `scheduled_processing`:

```python
async def process_pending_news_batch(self, hours=48):
    # 1. Собираем из всех источников
    all_items = await self._collect_unprocessed_all_sources(hours=hours)

    # 2. Группируем по категориям
    categories = {}
    for item in all_items:
        cat = item.get('category') or 'Общее'
        categories.setdefault(cat, []).append(item)

    # 3. Для каждой категории: Editor → Archivist → generated_news
    for category, items in categories.items():
        await self._process_multi_source_batch(items, category)
```

### Шаг 5: Генерация сводки

```
items (из разных источников, одна категория)
    → Vector Search (похожие events)
    → EditorAgent (объединяет все источники в одну новость)
    → add_generated_news(source_ids=["tg_5", "rss_13", "web_10"])
    → ArchivistAgent (новое событие или продолжение)
    → events.create_event(source_news_ids=["tg_5", "rss_13", "web_10"])
    → mark_batch_processed() (отмечаем все источники)
```

---

## 🏗️ Компоненты

### CategorizationTask

```python
@dataclass
class CategorizationTask:
    source_type: str = 'telegram'   # "telegram" | "rss" | "web"
    source_id: Optional[int] = None # ID в сырой таблице (rss_news.id, web_news.id)
    channel_id: int = 0             # Только для Telegram
    prompt: str = ''
    original_text: str = ''
    title: str = ''                 # Название источника
    desc: str = ''                  # Описание источника
```

### WebProcessorService

```python
web_processor = WebProcessorService(repo_factory=factory)

# Парсинг одного источника
received, added = await web_processor.parse_source(source_id=1)

# Все активные источники
stats = await web_processor.process_all_active_sources(limit=20)

# Отправка в очередь категоризации
queued = await web_processor.categorize_and_process_news(limit=50)
```

### Web Admin API

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/web/` | Список источников |
| POST | `/web/sources` | Создать источник |
| POST | `/web/sources/{id}/parse` | Ручной парсинг |
| POST | `/web/sources/{id}/toggle` | Активировать/деактивировать |
| DELETE | `/web/sources/{id}` | Удалить |
| GET | `/web/news` | Список новостей |

---

## 🧪 Тестирование

```bash
# Репозитории (posts, channels, events)
pytest tests/test_repositories/ -v

# RSS
pytest tests/test_rss/ -v

# Категоризация
pytest tests/test_categorization/ -v

# Новости и агенты
pytest tests/test_news/ tests/test_agents/ -v
```

Результат: 108 passed, 2 failed (UserRepository tags — до-рефакторинговая проблема), 17 errors (Redis — не настроен).

---

## 📊 Метрики

| Метрика | Значение |
|---------|----------|
| Новых файлов | 4 |
| Изменённых файлов | 12 |
| Новых строк | +1544 |
| Удалённых строк | -104 |
| Новых репозиториев | 2 (WebNews, WebSource) |
| Новых API endpoint'ов | 6 (/web/*) |
| Новых полей БД | 10 |
