# Таблица пользователей (users)

## Обзор

Добавлена таблица `users` для управления пользователями бота с системой ролей и подписок.

## Структура таблицы

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id_encrypted TEXT UNIQUE NOT NULL,        -- Зашифрованный ID Telegram (AES-256-GCM)
    role VARCHAR(20) NOT NULL DEFAULT 'user',      -- 'user' или 'admin'
    created_at DATETIME NOT NULL,                  -- Дата регистрации
    has_subscription BOOLEAN NOT NULL DEFAULT 0,   -- Наличие подписки
    subscription_started_at DATETIME,              -- Дата начала подписки
    subscription_ends_at DATETIME,                 -- Дата окончания (NULL = бессрочно)
    preferred_tags TEXT NOT NULL DEFAULT '[]',     -- Предпочтительные теги (JSON)
    preferred_categories TEXT NOT NULL DEFAULT '[]' -- Предпочтительные категории (JSON)
)
```

## Миграция

Запуск миграции:
```bash
source .venv/Scripts/activate
python -m database.migrate_add_users_table
```

Миграция:
1. Создаёт таблицу `users`
2. Читает `ADMIN_ID` из `.env` (для обратной совместимости)
3. Шифрует `ADMIN_ID` using AES-256-GCM
4. Добавляет администратора с бессрочной подпиской

## Шифрование

ID пользователей шифруется с использованием **AES-256-GCM**.

### Ключ шифрования

Переменная окружения `ENCRYPTION_KEY`:
```env
ENCRYPTION_KEY=your_secret_encryption_key_min_32_chars
```

> **Важно:** В продакшене обязательно задайте свой уникальный ключ!

### Функции шифрования

Доступны в `services/util.py`:
- `encrypt_user_id(user_id: int) -> str` — зашифровать ID
- `decrypt_user_id(encrypted: str) -> int` — расшифровать ID

## UserRepository

Новый репозиторий `database/repositories/users.py`:

```python
from database.repositories.users import UserRepository
from database.models import async_session

async with async_session() as session:
    user_repo = UserRepository(session)
    
    # Получить пользователя по Telegram ID
    user = await user_repo.get_by_telegram_id(telegram_id)
    
    # Получить или создать пользователя
    user = await user_repo.get_or_create_user(telegram_id)
    
    # Проверить права администратора
    is_admin = await user_repo.is_admin(telegram_id)
    
    # Проверить активную подписку
    has_sub = await user_repo.has_active_subscription(telegram_id)
    
    # Обновить подписку
    await user_repo.update_subscription(
        telegram_id,
        has_subscription=True,
        started_at=datetime.now(),
        ends_at=None  # Бессрочно
    )
    
    # Обновить предпочтения
    await user_repo.update_preferences(
        telegram_id,
        preferred_tags=["Политика", "Экономика"],
        preferred_categories=["Новости", "Аналитика"]
    )
```

## Проверка прав администратора

Фильтры `AdminM` и `AdminQ` в `services/bot/handlers/filters.py` теперь проверяют роль из БД:

```python
from services.bot.handlers.filters import AdminM, AdminQ

# Использование в роутерах
@admin.message(AdminM(), Command('start'))
async def start(message: Message):
    # Доступно только администраторам
    ...
```

## Регистрация пользователей

Пользователи автоматически регистрируются при команде `/start`:

```python
@admin.message(Command('start'))
async def start(message: Message):
    async with async_session() as session:
        user_repo = UserRepository(session)
        await user_repo.get_or_create_user(telegram_id=message.from_user.id)
    
    await message.answer('👋 Привет!')
```

## Роли

### User (по умолчанию)
- Создаётся при первом запуске бота
- `has_subscription = False`
- Нет доступа к админским командам

### Admin
- Добавляется через миграцию или вручную в БД
- `has_subscription = True`
- `subscription_ends_at = NULL` (бессрочная)
- Доступ к командам: `/approve_news`, `/reject_news`, `/edit_channels`, и др.

## Добавление администратора вручную

Через SQL:
```sql
-- Сначала нужно зашифровать user_id через Python
-- Затем вставить в БД
INSERT INTO users (user_id_encrypted, role, created_at, has_subscription, subscription_started_at)
VALUES ('<encrypted_id>', 'admin', datetime('now'), 1, datetime('now'));
```

Через Python:
```python
from services.util import encrypt_user_id
from database.models import async_session
from database.repositories.users import UserRepository
from datetime import datetime, timezone

async with async_session() as session:
    user_repo = UserRepository(session)
    
    # Создаём администратора
    encrypted_id = encrypt_user_id(telegram_id)
    # ... далее через SQL INSERT или обновить существующего
```

## Подписки

### Типы подписок
1. **Бессрочная** — `subscription_ends_at = NULL` (у админов по умолчанию)
2. **Временная** — `subscription_ends_at = конкретная дата`

### Проверка активности
```python
user = await user_repo.get_by_telegram_id(telegram_id)
if user.has_active_subscription:
    # Подписка активна
    ...
```

## Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `ENCRYPTION_KEY` | Ключ шифрования user_id (мин. 32 символа) | `my_secret_key_32chars_minimum` |
| `ADMIN_ID` | Legacy: ID админа для миграции | `400233435` |

## Изменения в проекте

### Удалено
- `ADMIN_ID` из `config/settings.py`
- `ADMIN_ID` из `services/bot/config.py`
- Прямая проверка `message.from_user.id == ADMIN_ID`

### Добавлено
- Таблица `users` в БД
- `User` модель в `database/models.py`
- `UserRepository` в `database/repositories/users.py`
- Функции шифрования в `services/util.py`
- Фильтры `AdminM`/`AdminQ` с проверкой из БД
- Регистрация пользователей при `/start`

### Обновлён
- `database/factory.py` — добавлен метод `users()`
- `services/bot/handlers/commands.py` — регистрация + проверка прав
- `services/bot/utils.py` — функции approve/reject используют Telegram ID
- `README.md` — документация по новым переменным окружения
