# План: Вкладка «Каналы» — аналог страницы пользователей

## Контекст

В системе две таблицы каналов:
- **`channels`** — источники мониторинга (откуда считываем посты): `channel_id`, `title`, `description`, `trust_rating`, `is_trusted`, `tags`
- **`publishers`** — каналы публикации (куда публикуем новости): `id`, `channel_id`, `title`, `description`, `is_active`, `category`

Сейчас `routes/channels.py` — заглушка, страницы `channels.html` нет.

## Что делаем

### 1. Бэкенд — `services/web_admin/routes/channels.py`

Полная переработка с двумя наборами API, по одному на каждую таблицу:

**Channels (источники мониторинга):**
- `GET /api/channels` — список с пагинацией, сортировкой, фильтрами (is_trusted, поиск по названию)
- `GET /api/channels/{id}` — detail
- `PUT /api/channels/{id}` — редактирование (title, description, trust_rating, is_trusted, tags)
- `DELETE /api/channels/{id}` — удаление

**Publishers (каналы публикации):**
- `GET /api/publishers` — список с пагинацией, сортировкой, фильтрами (is_active, category)
- `GET /api/publishers/{id}` — detail
- `PUT /api/publishers/{id}` — редактирование (title, description, is_active, category)
- `DELETE /api/publishers/{id}` — удаление

### 2. HTML-страница — `services/web_admin/templates/channels.html`

Новый шаблон, структура как у `users.html`:
- Два таба: **«Источники»** / **«Публикация»**
- Каждый таб: таблица с сортировкой + панель фильтров + пагинация
- Модальное окно редактирования для каждой сущности
- Кнопка удаления с подтверждением

**Источники (channels):** ID · Telegram ID · Название · Доверие (badge) · Рейтинг · Теги · Действия
**Публикация (publishers):** ID · Telegram ID · Название · Категория · Активен (badge) · Создан · Действия

### 3. Регистрация страницы в `app.py`

Добавить роут на `/channels` → `channels.html` (сейчас его нет — только `/api/channels` из app.py для создания).

### 4. Убрать дублирующийся эндпоинт создания канала

Сейчас `POST /api/channels` (создание) лежит в `app.py`. Переносим его в `routes/channels.py` как `POST /api/channels` и `POST /api/publishers` соответственно. `resolve-channel-link` тоже переезжает.

## Файлы для изменения

| Файл | Действие |
|------|----------|
| `services/web_admin/routes/channels.py` | **Полная перезапись** — два набора CRUD API |
| `services/web_admin/templates/channels.html` | **Новый** — страница с двумя табами, аналог users.html |
| `services/web_admin/api/app.py` | Добавить HTML-роут `/channels`, убрать `POST /api/channels`, `POST /api/channels/resolve-link`, `GET /api/publishers/list` (переезжают в channels.py) |

## Подход

- Стиль, CSS, паттерны — 1-в-1 как `users.html` (Tailwind, пагинация, модальные окна)
- Пагинация, сортировка, фильтры — те же утилиты что в users
- Модальное редактирование inline (оверлей как role/subscription модальки в users)
- Теги — рендер как в users.html через `renderTags()`
