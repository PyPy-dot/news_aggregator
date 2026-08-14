# Web Admin Authentication — Система аутентификации

**Версия:** 1.0.0  
**Дата:** 2026-08-13

## Обзор

Реализована классическая система аутентификации для Web Admin панели на основе:
- Логин/пароль с хэшированием (bcrypt)
- JWT токены с временем жизни 3 часа
- Продление сессии при активности
- Хранение учётных данных в файле `.web_admin_session.json`

## Компоненты

### 1. Session Manager (`services/web_admin/session_manager.py`)

Управляет сессиями и учётными данными:

```python
from services.web_admin.session_manager import get_session_manager

manager = get_session_manager()

# Проверка существования учётки
if not manager.credentials_exist():
    manager.create_credentials("admin", "password123")

# Проверка пароля
if manager.verify_password("password123"):
    token = manager.create_token("admin")

# Проверка токена
payload = manager.verify_token(token)
if payload:
    print(f"Пользователь: {payload['sub']}")
```

**Функции:**
- `credentials_exist()` — проверка существования учётки
- `create_credentials(username, password)` — создание учётки (хэширование bcrypt)
- `verify_password(password)` — проверка пароля
- `create_token(username)` — создание JWT токена (3 часа)
- `verify_token(token)` — проверка токена
- `refresh_token(token)` — продление сессии
- `reset_credentials()` — сброс учётки

### 2. Файл сессии (`.web_admin_session.db`)

SQLite база данных в корне проекта:

```
.web_admin_session.db
├── credentials (таблица)
│   ├── id (PRIMARY KEY)
│   ├── username (UNIQUE)
│   ├── password_hash
│   ├── created_at
│   └── updated_at
└── sessions (таблица, опционально)
    ├── id
    ├── username
    ├── token_hash
    ├── created_at
    ├── expires_at
    └── last_activity
```

**Преимущества SQLite:**
- Надёжное хранение с транзакциями
- Возможность расширения (сессии, логи, история)
- Бинарный формат (не текстовый как JSON)
- Поддержка SQL запросов

### 3. Консольный Setup (`services/web_admin/service.py`)

При первом запуске запрашивает логин/пароль через консоль:

```
============================================================
🔐 ПЕРВЫЙ ЗАПУСК WEB ADMIN — СОЗДАНИЕ УЧЁТНОЙ ЗАПИСИ
============================================================

Введите данные для входа в админ-панель:

  Логин (мин. 3 символа): admin
  Пароль (мин. 6 символов): ******
  Подтвердите пароль: ******

🔧 Создание учётной записи...
✅ Учётная запись 'admin' успешно создана!

Теперь вы можете войти в админ-панель:
   URL: http://localhost:8001
   Логин: admin

============================================================
```

**Требования:**
- Логин: мин. 3 символа
- Пароль: мин. 6 символов

### 4. Маршруты аутентификации (`services/web_admin/routes/auth.py`)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/auth/login` | GET | Страница входа |
| `/auth/login` | POST | Обработка формы входа |
| `/auth/logout` | GET/POST | Выход из системы |

**Логика:**
1. GET `/auth/login` — показывает форму входа
2. POST `/auth/login` — проверяет логин/пароль
3. При успехе — устанавливает cookie с JWT токеном
4. При неудаче — показывает форму с ошибкой

### 5. Cookie сессии

| Параметр | Значение |
|----------|----------|
| Name | `web_admin_session` |
| Max-Age | 3 часа (10800 секунд) |
| HttpOnly | True (не доступно через JS) |
| Secure | False (True в production с HTTPS) |
| SameSite | Lax |

## Как это работает

### Первый запуск

```bash
python main.py
```

1. Web Admin Service проверяет файл `.web_admin_session.json`
2. Если нет — запрашивает логин/пароль через консоль
3. Хэширует пароль (bcrypt, salt rounds=12)
4. Сохраняет в файл
5. Открывает браузер на странице входа

### Вход в систему

1. Пользователь вводит логин/пароль на `/auth/login`
2. Server проверяет через `SessionManager.verify_password()`
3. При успехе — создаёт JWT токен на 3 часа
4. Устанавливает cookie с токеном
5. Перенаправляет на главную страницу

### Проверка сессии

1. При запросе страницы — `get_optional_user()` извлекает токен из cookie
2. `SessionManager.verify_token()` проверяет:
   - Подпись токена
   - Время истечения
   - Соответствие пользователя
3. Если действителен — пользователь авторизован
4. Если истёк — редирект на `/auth/login`

### Продление сессии

При каждом запросе с действительным токеном:
1. Токен проверяется
2. Если действителен и до истечения < 1 часа — создаётся новый
3. Новый токен устанавливается в cookie
4. Сессия продлевается ещё на 3 часа

**Альтернативно:** Можно продлевать сессию только при явных действиях пользователя (клики, переходы).

## Безопасность

### Хэширование пароля

- **Алгоритм:** bcrypt
- **Salt rounds:** 12 (баланс безопасность/производительность)
- **Хранение:** Только хэш, пароль не восстанавливается

### JWT токен

- **Алгоритм:** HS256
- **Время жизни:** 3 часа
- **Секрет:** Из `WEB_ADMIN_JWT_SECRET` env или генерируется

### Рекомендации для production

1. **Установите `WEB_ADMIN_JWT_SECRET`** в `.env`:
   ```bash
   WEB_ADMIN_JWT_SECRET=your-super-secret-key-here
   ```

2. **Включите HTTPS:**
   ```python
   # В routes/auth.py
   COOKIE_SECURE = True  # Только HTTPS cookies
   ```

3. **Используйте reverse proxy** (nginx):
   ```nginx
   location / {
       proxy_pass http://localhost:8001;
       # SSL настройки...
   }
   ```

## Сброс пароля

Если забыли пароль:

```bash
# Удалите файл сессии (SQLite)
rm .web_admin_session.db

# Перезапустите сервер
python main.py

# Введите новые данные в консоли
```

## API для разработчиков

### Получение текущего пользователя

```python
from fastapi import Depends
from services.web_admin.api.app import get_optional_user, get_required_user

@app.get("/protected")
async def protected_route(user: dict = Depends(get_required_user)):
    return {"username": user["username"]}

@app.get("/public")
async def public_route(user: Optional[dict] = Depends(get_optional_user)):
    if user:
        return {"logged_in": True, "username": user["username"]}
    return {"logged_in": False}
```

### Ручное создание токена

```python
from services.web_admin.session_manager import get_session_manager

manager = get_session_manager()
token = manager.create_token("admin")
```

### Проверка токена

```python
payload = manager.verify_token(token)
if payload:
    username = payload["sub"]
    expires_at = payload["exp"]
```

## Структура файлов

```
services/web_admin/
├── api/
│   └── app.py              # FastAPI приложение + get_optional_user
├── routes/
│   └── auth.py             # Маршруты аутентификации
├── templates/
│   ├── index.html          # Главная страница (с кнопкой выхода)
│   └── login.html          # Страница входа
├── service.py              # WebAdminService + консольный setup
└── session_manager.py      # SessionManager (ядро аутентификации)

.web_admin_session.db       # Файл сессии (SQLite в корне проекта)
```

## Зависимости

```
bcrypt>=4.0.0      # Password hashing
python-jose        # JWT tokens
fastapi            # Web framework
```

## Будущие улучшения

1. **Двухфакторная аутентификация (2FA)** — TOTP коды
2. **История входов** — логирование успешных/неуспешных попыток
3. **Блокировка** — временная блокировка после N неудачных попыток
4. **Смена пароля** — через UI админки
5. **Несколько пользователей** — поддержка нескольких администраторов
6. **Роли** — разные уровни доступа (admin, editor, viewer)
