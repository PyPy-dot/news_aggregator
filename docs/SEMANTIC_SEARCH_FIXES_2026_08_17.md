# Исправления и доработки семантического поиска

**Дата:** 2026-08-17  
**Версия:** 3.4.0  
**Статус:** ✅ Завершено

---

## Проблема

После первоначальной реализации семантический поиск в веб-админке возвращал нерелевантные результаты:
- Поиск «Салават» в постах выдавал 5 лишних записей
- Поиск «Кишинёв» в сгенерированных выдавал записи про «скидка 50%»
- Поиск «Test» показывал шумовые семантические результаты

Причины:
1. `persist_directory` параметр в `VectorSearchEngine` игнорировался (`None if None else None`)
2. `min_score=0.2` в API-эндпоинтах — слишком низкий порог, пропускал шум
3. `search_morph()` возвращал `True` для пустого/короткого запроса (< 3 символа) — матчил все записи
4. Текстовые совпадения (LIKE) шли **после** семантических — точное совпадение пряталось под шумом
5. Старый `_search_morph` дублировался в каждом файле с разными багами
6. Текстовый LIKE был привязан к SQLite (не работал на PostgreSQL/MySQL)

---

## Что исправлено

### 1. Абстрактный слой поиска — `services/search_db.py` (новый модуль)

Единый модуль для DB-agnostic поиска, работающий через `services/database` абстракцию:

| Функция | SQLite | PostgreSQL | MySQL |
|---------|--------|------------|-------|
| `ilike()` | OR(LIKE lower/upper) | `ILIKE` | `LIKE` |
| `text_search_condition()` | множественные LIKE | ILIKE | LIKE |
| `apply_filter()` | LIKE с регистрами | ILIKE | LIKE |
| `search_morph()` | Python n-gram (fallback) | тот же | тот же |

**Определение типа СУБД:** `_get_db_type()` → `services.database.get_database_service().db_type`

### 2. Фикс `persist_directory` — `search_engine.py`

```python
# Было:
self.vector_store = ChromaVectorStore(
    persist_directory=None if persist_directory is None else None  # BUG
)

# Стало:
persist_dir: Optional[Path] = Path(persist_directory) if persist_directory else None
self.vector_store = ChromaVectorStore(
    persist_directory=persist_dir,
    embedding_service=self.embeddings,  # для валидации дименсии
)
```

### 3. Валидация размерности эмбеддинга

- `ChromaVectorStore.add()` — `_validate_embedding_dim()` проверяет `len(embedding) == embedding_service.embedding_dim`
- `VectorSearchEngine.add_event/news/post()` — `_validate_embedding()` на уровне бизнес-логики
- Защита от несовместимости при смене модели эмбеддингов

### 4. `search_morph()` — исправлены баги

```python
# Было:
if not needle_tokens:
    return True  # Пустой запрос матчит ВСЁ

# Стало:
if not needle_tokens:
    return False  # Пустой/короткий запрос не матчит

# Новый: защита от None
haystack = str(haystack or "")
needle = str(needle or "")
```

### 5. Стратегия объединения результатов — `routes/news.py`

**Порядок:**
1. Текстовые совпадения (LIKE/morph) → score=1.0, всегда в топе
2. Семантические результаты как дополнение:
   - При наличии текстовых хитов: семантика с `score >= 0.4`, не более `limit - len(text_ids)` штук
   - При отсутствии текстовых хитов: семантика `score >= 0.3`, основной источник

**min_score в ChromaDB запросах:** поднят с 0.2 до **0.3**

### 6. Централизация `search_morph`

Удалены локальные копии `_search_morph` из:
- `routes/news.py` → использует `services.search_db.search_morph`
- `routes/channels.py` → использует `services.search_db.search_morph`
- `routes/users.py` → заменён локальный `_search_morph` на общий

### 7. Настройки из `config.settings`

```python
# В settings.py
vector_search_persist_directory: str = Field(default='vector_store')
vector_search_events_limit: int = Field(default=5)
vector_search_posts_limit: int = Field(default=10)
vector_search_min_score_events: float = Field(default=0.7)
vector_search_min_score_posts: float = Field(default=0.6)

# VectorSearchEngine использует их через _get_settings()
```

---

## Пороги min_score по контексту

| Контекст | Порог | Где |
|----------|-------|-----|
| API-поиск пользователя (posts/generated) | **0.3** | `routes/news.py` |
| Семантика как дополнение к тексту | **0.4** | `routes/news.py` merge logic |
| Семантический поиск каналов | **0.3** | `routes/channels.py` |
| Генерация новостей (контекст) | **0.7** / **0.6** | `orchestrator.py`, `strategies/urgent.py` |
| Группировка постов в события | **0.75** | `context.py`, `search_engine.py` |
| Маршрутизация AI-агентов | **0.75** | `ai_agent/vector_routers.py` |

---

## Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `services/search_db.py` | **Новый** — абстрактный слой поиска |
| `services/vector_search/search_engine.py` | Фикс persist_directory, валидация дименсии, настройки из config |
| `services/vector_search/chroma_client.py` | Валидация дименсии в `add()`/`add_batch()` |
| `services/vector_search/service.py` | Передача `persist_directory` через конструктор |
| `config/settings.py` | Новый параметр `vector_search_persist_directory` |
| `services/core/container.py` | Передача `persist_directory` из settings |
| `services/web_admin/routes/news.py` | Новый merge-алгоритм, `text_search_condition`, `apply_filter`, `search_morph` |
| `services/web_admin/routes/channels.py` | `search_morph` из общего модуля, `min_score=0.3` |
| `services/web_admin/routes/users.py` | `search_morph` + `text_search_condition` вместо локального `_search_morph` |

---

## Тестирование

Все сценарии проверены на реальной БД:

| Запрос | Таб | До | После |
|--------|-----|-----|-------|
| «Салават» | posts | 6 (1 релевантный + 5 шума) | 1 (релевантный) |
| «Test» | posts | 5 (1 релевантный + 4 шума) | 1 (релевантный) |
| «Кишинёв» | generated | 30 (2 релевантных + 28 акций) | 2 (релевантные) |
| «взрыв» | generated | 4 (3 релевантных + 1 шум) | 4 (релевантные) |
| «БПЛА» | posts | 8 (все релевантные) | 8 (все релевантные) |
| «Украина» | generated | 49 (21 текстовых + 42 семантических) | 10 (3 текстовых + 7 семантических) |

---

## Миграция

Никаких изменений схемы БД не требуется. Хранилище ChromaDB совместимо.

После деплоя:
1. Перезапустить приложение — настройки загрузятся из `.env`
2. Кэш поиска очистится автоматически (ключи изменились)
3. При необходимости — `POST /api/vector-index/reindex`
