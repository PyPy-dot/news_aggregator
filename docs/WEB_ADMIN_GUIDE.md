# Web Admin — Руководство

**Версия:** 2.0
**Дата обновления:** 2026-08-16

---

## Обзор

Веб-интерфейс администрирования News Aggregator на базе FastAPI + Jinja2 + Tailwind CSS. Запускается на порту `8001` автоматически при старте приложения.

### Стек

| Компонент | Технология |
|-----------|-----------|
| Backend | FastAPI + uvicorn |
| Шаблонизатор | Jinja2 |
| CSS | Tailwind CSS (CDN) |
| Аутентификация | JWT (python-jose) + bcrypt |
| Хранение сессий | SQLite (`.web_admin_session.db`) |
| WebSocket | Для авторизации ListenerBot |

---

## Структура проекта

```
services/web_admin/
├── api/
│   ├── app.py              # FastAPI приложение (52 endpoint'а)
│   └── auth.py             # JWT утилиты для Telegram авторизации
├── routes/                 # 13 роутеров
│   ├── auth.py             # Вход/выход
│   ├── channels.py         # Каналы-источники
│   ├── console.py          # Консоль управления (11 endpoint'ов)
│   ├── dashboard.py        # Дашборд
│   ├── listener_auth.py    # Авторизация ListenerBot (6 endpoint'ов)
│   ├── listener_auth_ws.py # WebSocket для авторизации
│   ├── news.py             # Новости
│   ├── rss.py              # RSS источники
│   ├── settings.py         # Настройки .env
│   ├── tasks.py            # Задачи (12 endpoint'ов)
│   ├── users.py            # Пользователи
│   └── web.py              # Web источники
├── health_router.py        # Health check API (7 endpoint'ов)
├── session_manager.py      # Сессии + JWT (SQLite, 400 строк)
├── service.py              # WebAdminService (обёртка uvicorn)
├── config.py               # Конфигурация + load_dotenv
├── log_handler.py          # Логирование
└── templates/              # Jinja2 шаблоны
    ├── index.html          # Главная панель
    ├── console.html        # Консоль управления
    ├── settings.html       # Настройки
    ├── login.html          # Страница входа
    └── components/
        ├── footer.html         # Футер с глобальным статусом
        ├── listener-auth-modal.html
        └── notifications-modal.html  # Уведомления
```

---

## Страницы

### Главная (`/`)

Дашборд с обзором системы:

- **Статистика** — карточки: новости, каналы, пользователи, задачи (автообновление каждые 30 сек)
- **Статус сервисов** — 6 компонентов с единым форматом статусов:
  - Admin Bot, Listener Bot, Scheduler — через ServiceManager (с uptime)
  - AI Агенты, База данных, ChromaDB — через Health Check (с latency)
- **Быстрые действия** — создать новость, добавить канал, открыть консоль
- **Последние новости** — список последних 5 новостей
- **Глобальный статус** — индикатор в футере (зелёный/жёлтый/серый/красный)

### Консоль (`/console`)

Управление сервисами и выполнение команд:

- **Управление сервисами** — старт/стоп/рестарт для Bot, Listener, Scheduler
- **Python REPL** — выполнение Python-кода через `exec()` с ограниченным контекстом
- **SQL Console** — выполнение SQL-запросов к БД
- **Логи** — просмотр логов приложения с фильтрацией по источнику и очисткой
- **Listener Auth** — авторизация ListenerBot через WebSocket

### Настройки (`/settings`)

Редактирование переменных окружения:

- **Горячее применение** — изменения в `.env` применяются без перезапуска через `reload_settings()`
- **Группировка** — Telegram, Database, LLM, Web Admin, Payment, Queue
- **Защита** — паролем защищённые поля (JWT_SECRET, ENCRYPTION_KEY)
- **Перезапуск** — полная перезагрузка приложения при критических изменениях

### Новости (`/news`)

Управление новостями, модерация, фильтрация по категориям и статусам.

### Каналы (`/channels`)

Управление каналами-источниками: добавление, удаление, настройка доверия.

### Пользователи (`/users`)

Список пользователей бота, управление подписками, ролями, предпочтениями.

### Задачи (`/tasks`)

Управление задачами планировщика:
- Создание одноразовых и периодических задач
- Отмена, перепланирование, удаление
- Статистика задач по статусам
- Быстрые кнопки: daily morning / daily evening

### RSS ленты (`/rss`)

Управление RSS источниками: добавление URL, настройка интервалов.

### Web парсинг (`/web`)

Управление web источниками: URL, заголовки, CSS-селекторы.

---

## API Endpoint'ы

### Health Check (health_router.py)

| Метод | Path | Описание |
|-------|------|----------|
| GET | `/api/health` | Краткий статус (для load balancer) |
| GET | `/api/health/full` | Полная проверка всех компонентов |
| GET | `/api/health/{component}` | Проверка конкретного компонента |
| GET | `/api/health/live` | Liveness probe (k8s) |
| GET | `/api/health/ready` | Readiness probe (k8s) |
| GET | `/api/health/metrics` | Метрики в формате Prometheus |

### Главная (app.py)

| Метод | Path | Описание |
|-------|------|----------|
| GET | `/` | Главная страница |
| GET | `/api/stats` | Статистика (новости, каналы, пользователи, задачи) |
| GET | `/api/services/status` | Статусы сервисов + уведомления |
| GET | `/api/news/recent` | Последние новости |
| POST | `/api/news/generate` | Быстрая генерация новости |
| POST | `/api/channels` | Создание канала |
| POST | `/api/notifications/read` | Пометить уведомления как прочитанные |

### Консоль (routes/console.py)

| Метод | Path | Описание |
|-------|------|----------|
| GET | `/console` | Страница консоли |
| POST | `/api/execute` | Выполнение shell-команды |
| POST | `/api/python` | Выполнение Python-кода |
| POST | `/api/sql` | Выполнение SQL-запроса |
| GET | `/api/logs` | Последние строки логов |
| GET | `/api/logs/sources` | Источники логов |
| POST | `/api/logs/clear` | Очистка логов |
| GET | `/api/status` | Статус сервисов |
| POST | `/api/{service}/start` | Запуск сервиса |
| POST | `/api/{service}/stop` | Остановка сервиса |
| POST | `/api/{service}/restart` | Рестарт сервиса |

### Задачи (routes/tasks.py)

| Метод | Path | Описание |
|-------|------|----------|
| GET | `/tasks` | Список задач |
| GET | `/tasks/stats` | Статистика задач |
| POST | `/tasks/create` | Создание задачи |
| POST | `/tasks/create-direct` | Прямая генерация |
| POST | `/tasks/create-periodic` | Периодическая задача |
| GET | `/tasks/{task_id}` | Задача по ID |
| POST | `/tasks/{task_id}/cancel` | Отмена задачи |
| POST | `/tasks/{task_id}/reschedule` | Перепланирование |
| DELETE | `/tasks/{task_id}` | Удаление задачи |
| POST | `/tasks/cleanup` | Очистка застарелых задач |
| GET | `/tasks/meta/task-types` | Метаданные типов задач |
| POST | `/tasks/quick/daily-morning` | Быстрая утренняя задача |
| POST | `/tasks/quick/daily-evening` | Быстрая вечерняя задача |

### Настройки (routes/settings.py)

| Метод | Path | Описание |
|-------|------|----------|
| GET | `/settings` | Страница настроек |
| GET | `/api/env` | Список переменных окружения |
| POST | `/api/env` | Обновление переменных |
| POST | `/api/env/restart` | Перезапуск приложения |

### Listener Auth (routes/listener_auth.py)

| Метод | Path | Описание |
|-------|------|----------|
| GET | `/api/listener/auth/status` | Статус авторизации |
| POST | `/api/listener/auth/start` | Начало авторизации |
| GET | `/api/listener/auth/check` | Проверка статуса |
| POST | `/api/listener/auth/code` | Ввод кода |
| POST | `/api/listener/auth/password` | Ввод пароля |
| POST | `/api/listener/auth/cancel` | Отмена авторизации |

| Метод | Path | Описание |
|-------|------|----------|
| WS | `/listener-auth` | WebSocket для авторизации |

---

## Аутентификация

### Механизм

1. **Первый запуск** — запрос логина и пароля через консоль
2. **Хранение** — SQLite БД (`.web_admin_session.db`), пароли через bcrypt
3. **JWT** — токены с TTL 3 часа, автоматическое продление
4. **Секрет** — `WEB_ADMIN_JWT_SECRET` из `.env`

### Публичные пути (без авторизации)

`/`, `/auth/login`, `/auth/logout`, `/health`, `/docs`, `/openapi.json`

### Auth Middleware

`AuthMiddleware` проверяет JWT-токен в cookie для всех запросов кроме публичных путей.

---

## ServiceManager

Сервисы управляются через ServiceManager — singleton для старта/стопа/рестарта сервисов:

```python
from services.service_manager import get_service_manager

manager = get_service_manager()
await manager.start_service("bot")      # Запуск
await manager.stop_service("bot")       # Остановка
await manager.restart_service("bot")    # Рестарт
await manager.start_all()               # Все сервисы
await manager.stop_all()                # Все сервисы
```

**Формат ответа `get_all_statuses()`:**
```json
{
  "bot": {
    "state": "running",
    "healthy": true,
    "uptime_sec": 7200,
    "started_at": "2026-08-16T00:00:00+00:00",
    "last_error": null
  }
}
```

---

## Глобальный статус

Индикатор в футере на всех страницах, обновляется автоматически:

| Состояние | Цвет | Текст |
|-----------|------|-------|
| Все запущены | 🟢 зелёный + пульсация | Система активна |
| Сбои | 🔴 красный + пульсация | Есть сбои |
| Все остановлены | ⚫ серый | Сервисы остановлены |
| Частично | 🟡 жёлтый | Частичная работа |

Обновляется через polling каждые 10 секунд.

---

## Уведомления

Панель уведомлений (колокольчик в шапке):

- **Типы** — ошибки (красные), предупреждения (жёлтые), инфо (синие)
- **Фильтры** — все / ошибки / предупреждения / инфо
- **Автообновление** — каждые 10 секунд
- **Источники** — сбои сервисов через `/api/services/status`

---

## Health Check API

Проверяет 8 компонентов:

| Компонент | Критичность | Что проверяет |
|-----------|------------|---------------|
| **database** | CRITICAL | Подключение к БД (`SELECT 1`) |
| **telegram_bot** | CRITICAL | `bot.get_me()` через Telegram API |
| **ollama** | HIGH | `/api/tags` — доступность Ollama |
| **llm_fallback** | HIGH | Проверка всех LLM провайдеров |
| **vector_search** | HIGH | `client.list_collections()` в ChromaDB |
| **circuit_breakers** | MEDIUM | Состояние всех circuit breaker'ов |
| **scheduler** | MEDIUM | Подсчёт задач по статусам |
| **categorization_queue** | MEDIUM | Наличие очереди |

**Формат ответа:**
```json
{
  "status": "healthy",
  "components": [
    {
      "name": "database",
      "status": "healthy",
      "severity": "critical",
      "message": "БД подключена (SQLITE)",
      "latency_ms": 1.2,
      "details": {"db_type": "sqlite"}
    }
  ]
}
```

---

## Настройка

### Обязательные переменные

```bash
WEB_ADMIN_JWT_SECRET=your-random-secret-here
```

### Опциональные переменные

```bash
WEB_ADMIN_HOST=0.0.0.0
WEB_ADMIN_PORT=8001
WEB_ADMIN_SESSION_EXPIRE_HOURS=3
```

### Первый запуск

При первом запуске Web Admin запрашивает логин и пароль через консоль:
```
🔐 ПЕРВЫЙ ЗАПУСК WEB ADMIN — СОЗДАНИЕ УЧЁТНОЙ ЗАПИСИ
  Логин (мин. 3 символа): admin
  Пароль: **********
```

---

## Безопасность

| Мера | Реализация |
|------|-----------|
| Пароли | bcrypt хэширование |
| JWT | python-jose, HS256, TTL 3 часа |
| Секрет | `WEB_ADMIN_JWT_SECRET` из `.env` |
| Публичные пути | Только `/`, `/auth/*`, `/health` |
| Auth Middleware | Блокирует все остальные пути без токена |

---

**Автор:** AI-агент Стефания
**Дата актуализации:** 2026-08-16
