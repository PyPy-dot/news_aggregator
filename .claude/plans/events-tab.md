# План: Вкладка «Контекст» (events)

## Контекст

Таблица `EventContext`:
- `id`, `post_id` (FK posts), `context_data` (JSON строка), `event_category`, `tags`, `last_processed_at`, `created_at`

Вкладка Новости использует шаблонный подход: один таб → кнопка + content блок + TAB_CONFIG + state + renderTable + FILTER_FIELDS.

## Что добавляю

### 1. Backend — `routes/news.py`

Два новых эндпоинта:
- `GET /news/api/events` — список с пагинацией/сортировкой (id, post_id, context_data, event_category, tags, last_processed_at, created_at)
- `DELETE /news/api/events/{event_id}` — удаление

### 2. Фронтенд — `templates/news.html`

**Новый таб «Контекст»:**
- Кнопка в навбаре с иконкой `fa-project-diagram`
- Таблица: ID · Post ID · Категория · Контекст (truncate) · Теги · Обработана · Создан · Действие
- Фильтры: event_category, tags
- Рендер: `renderEvents(items)` — контекст truncate 150, теги через renderTags, last_processed_at как дата
- API: `/news/api/events`
- state, sortState, TAB_CONFIG, FILTER_FIELDS — новый entry
