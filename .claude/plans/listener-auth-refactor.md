# План: Рефакторинг авторизации ListenerBot

## Контекст

Авторизация listener'а в Telegram сейчас **поломана**:
- Модалка дублирована в `console.html` (инлайн) и существует как компонент `listener-auth-modal.html`
- Общается с бэкендом через HTTP polling (каждые 1-3 сек) — медленно и ненадёжно
- `settings.html` не имеет модалки вообще
- Консольный ввод через `sys.stdin` не работает в Docker/деamon-режиме
- Протухшая сессия не обрабатывается корректно — файл не удаляется до начала нового процесса

## Что будет работать после рефакторинга

1. **Протухшая/отсутствующая сессия** → автоматическое удаление старого файла → создание новой сессии → запуск процесса авторизации
2. **Двуэтапная авторизация**: код из TG → облачный пароль
3. **Параллельные каналы ввода**: консоль (stdin) + веб (модалка через WebSocket)
4. **Модалка** — один универсальный компонент, подключённый через include во все шаблоны кроме `login.html`
5. **WebSocket** для real-time обмена состоянием (замена polling)
6. **При успехе** — модалка закрывается автоматически

---

## Архитектура

```
                    ┌──────────────┐
                    │   Frontend   │
                    │   (Modal)    │
                    └──────┬───────┘
                           │ WebSocket
                    ┌──────▼───────┐
                    │  WebSocket   │
   HTTP fallback ──▶│  (listener   │──── asyncio.Queue ────▶ run_auth_process()
   (submit code/    │  auth)       │                      (listener_auth.py)
    password)       └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  ListenerBot │
                    │   (bot.py)   │
                    └──────────────┘
```

---

## Шаг 1: WebSocket-менеджер для авторизации

**Файл:** `services/web_admin/routes/listener_auth_ws.py` (новый)

Что делает:
- `WebSocketEndpoint` на `/ws/listener-auth`
- Подключается к глобальному `_auth_state` из `listener_auth.py`
- При подключении клиента: немедленно отправляет текущее состояние
- Watcher-петля: отслеживает изменения `_auth_state` и пушит дифф клиентам
- Двусторонняя связь:
  - **Backend → Frontend**: `{"type": "state_change", "state": {...}}`, `{"type": "completed"}`, `{"type": "error"}`
  - **Frontend → Backend**: `{"type": "submit_code", "code": "12345"}`, `{"type": "submit_password", "password": "..."}`, `{"type": "cancel"}`
- HTTP эндпоинты (`submit_code`, `submit_password`) остаются как fallback — они тоже работают

Ключевые моменты:
- WebSocket-клиенты хранятся в `set` — при событии рассылаем всем
- Watcher использует тот же `asyncio.Event` механизм, что и сейчас (`_code_event`, `_password_event`)
- backward-compatible: если клиент подключен только через HTTP, он продолжает работать через polling `/status`

## Шаг 2: Улучшение `listener_auth.py`

**Файл:** `services/web_admin/routes/listener_auth.py` (модификация)

Изменения:

### 2a. Автоматическая обработка протухшей сессии
В `run_auth_process()`:
- Перед `send_code_request()` проверить, существует ли старый файл сессии
- Если `is_user_authorized()` выбрасывает `AuthKeyUnregisteredError` — **немедленно** удалить файл сессии, пересоздать клиент, отправить событие `{type: "session_recreated"}`
- Добавить явную проверку: если файл сессии старше N дней (настраивается, по умолчанию 30), предупредить и предложить пересоздать

### 2b. Безопасное удаление и пересоздание сессии
Вынести `_remove_session_file()` и `_recreate_client()` в публичные утилиты с правильной логикой:
- `_remove_session_file()` — удаляет `.session` и `.session-journal`
- `_recreate_client(listener)` — disconnect → delete files → новый TelegramClient → connect → `_client_initialized = True`

### 2c. Обработка отсутствия stdin
В `wait_for_code()` и `wait_for_password()`:
- Проверить `sys.stdin.isatty()` и доступность stdin
- Если stdin недоступен (Docker, daemon) — пропустить консольный канал, работать только через веб
- Логировать: "⌨️ Консольный ввод недоступен, ожидаем ввод через веб"

### 2d. Event-шина для WebSocket
Добавить `_on_state_change(callback)` — регистрировать callback на изменение состояния, чтобы WebSocket-менеджер мог подписаться:
```python
_state_change_listeners: list[Callable] = []

def set_auth_step(step, message=None, error=None):
    # ... existing logic ...
    for cb in _state_change_listeners:
        try: cb(_auth_state.copy())  # fire-and-forget
        except: pass
```

## Шаг 3: Унификация модалки

### 3a. Чистка `console.html`
- **Удалить** инлайн-модалку (строки 380-449)
- **Удалить** дублирующийся JS для модалки (строки ~861-1130)
- **Добавить** `{% include 'components/listener-auth-modal.html' %}` перед `</body>`
- Кнопка «Telegram» остаётся — она вызывает `openListenerAuthFromConsole()`

### 3b. Добавить модалку в `settings.html`
- Добавить `{% include 'components/listener-auth-modal.html' %}` перед `</body>`

### 3c. Улучшить `listener-auth-modal.html`
- Переписать JS на **WebSocket-first** с HTTP fallback:
  1. При `DOMContentLoaded`: подключиться к `/ws/listener-auth`
  2. Если WebSocket недоступен → fallback на polling `/api/listener/auth/status` (каждые 2 сек)
  3. При получении `state_change` → обновить UI
  4. При `completed` → показать успех → закрыть через 2 сек
  5. При `error` → показать ошибку
- Добавить `autocomplete="off"` на поля ввода
- Добавить визуальный индикатор подключения (WebSocket connected/disconnected)
- Enter в полях → submit

### 3d. Проверить `index.html`
- Уже есть include — убедиться, что он работает корректно
- Убрать дублирующийся JS, если есть

## Шаг 4: Интеграция WebSocket в app.py

**Файл:** `services/web_admin/api/app.py` (модификация)

- Подключить WebSocket роут: `app.include_router(ws_router, prefix="/ws")`
- Добавить `/ws/listener-auth` в исключения AuthMiddleware (или сделать WebSocket авторизацию через query param)
- WebSocket endpoint не требует авторизации веба — он работает на уровне listener-сессии

## Шаг 5: Улучшение `bot.py`

**Файл:** `services/listener/bot.py` (модификация)

### 5a. Обработка протухшей сессии при инициализации
В `initialize()`:
- После обнаружения `AuthKeyUnregisteredError` или старого файла — вызвать `_handle_expired_session()`
- `_handle_expired_session()`:
  1. Удалить старый файл сессии
  2. Пересоздать клиент с чистой сессией
  3. Подключиться
  4. Запустить `run_auth_process()` через listener_auth модуль

### 5b. Удалить дублированную логику
- Убрать дублированное удаление сессии в блоках except — центрировать через `_handle_expired_session()`

## Шаг 6: Тестирование

1. **Сценарий 1**: Файла сессии нет → клиент создан → модалка появилась → введён код → введён пароль → авторизация успешна → модалка закрылась
2. **Сценарий 2**: Файл сессии старый → автоматически удалён → новая сессия → модалка → авторизация
3. **Сценарий 3**: Авторизация через WebSocket → real-time обновление
4. **Сценарий 4**: WebSocket недоступен → fallback на polling
5. **Сценарий 5**: Отмена авторизации → модалка закрылась
6. **Сценарий 6**: Пароль неверный → ошибка в модалке

---

## Файлы, которые меняются

| Файл | Действие |
|------|----------|
| `services/web_admin/routes/listener_auth_ws.py` | **Создать** — WebSocket endpoint |
| `services/web_admin/routes/listener_auth.py` | **Изменить** — event-шина, обработка протухшей сессии, fallback stdin |
| `services/web_admin/templates/components/listener-auth-modal.html` | **Переписать** — WebSocket-first JS |
| `services/web_admin/templates/console.html` | **Изменить** — удалить дубли, добавить include |
| `services/web_admin/templates/settings.html` | **Изменить** — добавить include модалки |
| `services/web_admin/templates/index.html` | **Проверить** — уже есть include |
| `services/web_admin/api/app.py` | **Изменить** — подключить WebSocket роут |
| `services/listener/bot.py` | **Изменить** — централизовать обработку протухшей сессии |

## Риски и смягчение

1. **WebSocket может быть заблокирован прокси/корпоративным firewall** → HTTP polling остаётся как fallback
2. **Пересоздание сессии может вызвать FloodWait** → логировать ошибку и показать в модалке, не спамить
3. **Race condition при параллельной отправке кода** → `submit_code()` и `submit_password()` атомарны (уже проверены по step)
