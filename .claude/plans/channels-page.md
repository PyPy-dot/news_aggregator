# План: Вкладка «Каналы» — аналог страницы пользователей

## Контекст

В системе две таблицы каналов:
- **`channels`** — источники мониторинга (откуда считываем посты): `channel_id`, `title`, `description`, `trust_rating`, `is_trusted`, `tags`
- **`publishers`** — каналы публикации (куда публикуем новости): `id`, `channel_id`, `title`, `description`, `is_active`, `category`

Сейчас `routes/channels.py` — заглушка, страницы `channels.html` нет.

## Главный принцип

**Один общий список каналов**, мерджим `channels` + `publishers` в единую таблицу с колонкой **«Тип»**:
- 🔵 *Источник* — из таблицы `channels` (откуда читаем посты)
- 🟢 *Публикация* — из таблицы `publishers` (куда публикуем)

Это удобнее: пользователь видит все каналы в одном месте и сразу понимает назначение каждого.

### 1. Бэкенд — `services/web_admin/routes/channels.py`

Полная переработка. **Единый API** с поддержкой обоих типов:

**Общий список (мердж):**
- `GET /api/merged` — объединённый список channels + publishers с пагинацией/сортировкой/фильтрами. Каждая запись содержит `type: "channel" | "publisher"`.
- `POST /api/search` — поиск по названию/описанию через LIKE + n-gram (как в users)

**Channels (источники):**
- `PUT /api/channels/{id}` — редактирование (title, description, trust_rating, is_trusted, tags)
- `DELETE /api/channels/{id}` — удаление

**Publishers (публикация):**
- `PUT /api/publishers/{id}` — редактирование (title, description, is_active, category)
- `DELETE /api/publishers/{id}` — удаление

**Справочники:**
- `GET /api/publishers/list` — перенос из `app.py`, простой список для dropdown

### 2. HTML-страница — `services/web_admin/templates/channels.html`

Новый шаблон, одна таблица с объединёнными каналами:

**Колонки:** ID · **Тип** (badge) · Telegram ID · Название · Описание · Теги/Категория · Действия

- 🔵 *Источник* — синяя badge
- 🟢 *Публикация* — зелёная badge

**Фильтры:**
- Выпадающий список по типу (Все / Источник / Публикация)
- Поиск по названию (LIKE + n-gram)

**Модальное окно редактирования** — адаптивное: для источников показывает trust_rating, is_trusted, tags; для publishers — is_active, category.

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
