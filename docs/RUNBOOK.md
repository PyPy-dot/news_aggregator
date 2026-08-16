# 🚀 Runbook: Запуск и обслуживание News Aggregator

**Версия:** 4.0.0  
**Дата:** 2026-08-16

---

## 📋 Быстрый старт

### 1. Установка зависимостей

```bash
cd news_aggregator

# Создаём виртуальное окружение (если нет)
python3 -m venv .venv
source .venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt
```

### 2. Настройка окружения

```bash
# Копируем .env.example в .env
cp .env.example .env

# Редактируем .env
nano .env
```

**Обязательные переменные:**

| Переменная | Описание | Пример |
|------------|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | `123456:ABC-DEF...` |
| `TELEGRAM_API_ID` | Telegram API ID | `39156045` |
| `TELEGRAM_API_HASH` | Telegram API hash | `6a097519...` |
| `TELEGRAM_PHONE_NUMBER` | Номер для UserBot | `+79991234567` |
| `ADMIN_ID` | Ваш Telegram ID | `123456789` |
| `WEB_ADMIN_JWT_SECRET` | JWT секрет для веб-админки | `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | Ключ шифрования (32+ символов) | `openssl rand -hex 32` |

**Как получить:**
- **BOT_TOKEN**: [@BotFather](https://t.me/BotFather) → `/newbot`
- **API_ID/API_HASH**: [my.telegram.org](https://my.telegram.org) → API development
- **ADMIN_ID**: [@userinfobot](https://t.me/userinfobot) или [@myidbot](https://t.me/myidbot)

### 3. Инициализация базы данных

```bash
# Применяем миграции
python3 -m alembic upgrade head

# (Опционально) Создаём админа вручную, если миграция не сработала
python3 -c "
from database.migrations.migrate_add_users_table import migrate
migrate()
"
```

### 4. Запуск приложения

```bash
# Запускаем основное приложение
python3 main.py
```

**Ожидаемый вывод:**
```
[INFO] 🔧 Инициализация приложения...
[INFO] ✅ БД подключена: SQLITE (или PostgreSQL)
[INFO] ✅ Web Admin запущен: http://localhost:8001
[INFO] ✅ ServiceManager инициализирован
[INFO] 📍 Сервисы остановлены - нажмите 'Старт' в консоли для запуска
```

**Сервисы запускаются лениво** через веб-админку (`http://localhost:8001/console`):
- Откройте консоль → нажмите **Старт** для запуска всех сервисов
- Или запускайте отдельные сервисы: Bot, Listener, Scheduler

---

## 🔧 Управление сервисами

### ServiceManager (через веб-админку)

Сервисы управляются через консоль админки (`http://localhost:8001/console`):

- **Старт** — запуск всех сервисов (Bot, Listener, Scheduler)
- **Стоп** — остановка всех сервисов
- **Бот / Лисенер / Шедулер** — индивидуальный рестарт

Статусы обновляются автоматически каждые 5 секунд.

### Остановка

Нажмите `Ctrl+C` в терминале — приложение корректно остановит все сервисы через ServiceManager.stop_all().

### Перезапуск

```bash
# Остановите текущий процесс (Ctrl+C)
# Запустите заново
python3 main.py
```

### Логи

```bash
# Логи в реальном времени
tail -f logs/news_aggregator_$(date +%Y-%m-%d).log

# Последние 100 строк
tail -100 logs/news_aggregator_$(date +%Y-%m-%d).log
```

---

## 🐛 Диагностика проблем

### 1. Ошибка: `database is locked`

**Симптомы:**
```
sqlite3.OperationalError: database is locked
```

**Причина:** Несколько процессов пытаются писать в SQLite одновременно.

**Решение:**
1. Остановите все экземпляры приложения
2. Удалите файл блокировки (если есть):
   ```bash
   rm -f db.sqlite3-journal
   ```
3. Проверьте, что приложение запущено в одном экземпляре:
   ```bash
   ps aux | grep "python3 main.py" | grep -v grep
   ```

### 2. Ошибка: `FloodWaitError`

**Симптомы:**
```
telethon.errors.rpcerrorlist.FloodWaitError: A wait of XXXXX seconds is required
```

**Причина:** Telegram ограничивает частые запросы авторизации.

**Решение:**
- Подождите указанное время (обычно несколько часов)
- Используйте другой номер телефона для тестов
- Для продакшена: авторизуйтесь один раз и сохраните сессию

### 3. Ошибка: `Conflict: terminated by other getUpdates`

**Симптомы:**
```
aiogram.exceptions.TelegramConflictError: Conflict: terminated by other getUpdates request
[WARNING] Sleep for X seconds and try again... (tryings = 0, 1, 2, 3)
```

**Причина:** Бот запущен в нескольких местах одновременно. Telegram разрешает только одно активное подключение к боту.

**Решение:**

**Вариант 1: Найти и остановить другой экземпляр**
```bash
# Проверьте локальные процессы
ps aux | grep "python.*main" | grep -v grep

# Остановите все экземпляры
pkill -f "python.*main.py"

# Проверьте, не запущен ли бот в Docker
docker ps | grep news-aggregator
```

**Вариант 2: Подождать освобождения сессии**
- Telegram освобождает сессию через ~10-15 минут после последнего подключения
- Просто подождите и попробуйте запустить снова

**Вариант 3: Использовать другой токен для разработки**
- Создайте тестового бота в @BotFather
- Используйте отдельный токен для локальной разработки

**Вариант 4: Проверить сервер**
- Если бот развёрнут на сервере, остановите его там перед локальным запуском
```bash
# На сервере
sudo systemctl stop news-aggregator
# или
docker-compose -f docker-compose.prod.yml down
```

### 4. Ошибка: `ConnectionError: Failed to connect to Ollama`

**Симптомы:**
```
ConnectionError: Failed to connect to Ollama
```

**Причина:** Ollama сервер не запущен.

**Решение:**
```bash
# Запустите Ollama
ollama serve

# Загрузите модель (если нет)
ollama pull qwen2.5:7b
```

### 5. Приложение не запускается

**Проверьте:**
1. Заполнен ли `.env` файл
2. Установлены ли зависимости (`pip install -r requirements.txt`)
3. Применены ли миграции (`alembic upgrade head`)
4. Запущен ли Ollama (если используется AI)

**Логи для диагностики:**
```bash
# Полные логи приложения
cat logs/news_aggregator_$(date +%Y-%m-%d).log

# Проверка импортов
python3 -c "
import config.settings
import database
import services.bot.bot
print('✅ Все импорты работают')
"
```

---

## 📊 Мониторинг

### Проверка статуса

```bash
# Проверка, запущено ли приложение
ps aux | grep "python3 main.py" | grep -v grep

# Проверка портов
lsof -i :8000  # Main app
lsof -i :8001  # Web Admin
lsof -i :11434 # Ollama
```

### Проверка базы данных

```bash
# Подключение к SQLite
sqlite3 db.sqlite3

# Проверка таблиц
.tables

# Проверка админов
SELECT id, role, has_subscription FROM users WHERE role='admin';

# Проверка задач
SELECT id, task_type, status, scheduled_at FROM tasks ORDER BY created_at DESC LIMIT 10;
```

### Проверка AI агентов

```bash
# Проверка модели Ollama
curl http://localhost:11434/api/tags

# Тестовый запрос
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:7b",
  "prompt": "Hello",
  "stream": false
}'
```

---

## 🔐 Безопасность

### Рекомендации для продакшена

1. **Измените пароли:**
   - `DB_PASSWORD` в `.env`
   - `JWT_SECRET` (сгенерируйте новый: `openssl rand -hex 32`)

2. **Ограничьте доступ к `.env`:**
   ```bash
   chmod 600 .env
   ```

3. **Используйте PostgreSQL вместо SQLite:**
   ```bash
   DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
   ```

4. **Настройте firewall:**
   ```bash
   # Разрешите только необходимые порты
   sudo ufw allow 8000  # Main app
   sudo ufw allow 8001  # Web Admin
   sudo ufw allow 11434 # Ollama (локально)
   ```

5. **Регулярные бэкапы:**
   ```bash
   # Бэкап базы данных
   cp db.sqlite3 backups/db_$(date +%Y%m%d_%H%M%S).sqlite3
   
   # Бэкап .env
   cp .env backups/env_$(date +%Y%m%d_%H%M%S).env
   ```

---

## 📦 Обновление

### Обновление кода

```bash
# Остановите приложение
# (Ctrl+C)

# Обновите код из git
git pull origin master

# Установите новые зависимости
pip install -r requirements.txt

# Примените миграции
alembic upgrade head

# Запустите приложение
python3 main.py
```

### Обновление модели Ollama

```bash
# Обновите модель
ollama pull qwen2.5:7b

# Перезапустите приложение
# (Ctrl+C, затем python3 main.py)
```

---

## 🆘 Экстренная помощь

### Приложение не отвечает

```bash
# Найдите PID
ps aux | grep "python3 main.py" | grep -v grep

# Принудительно остановите
kill -9 <PID>

# Проверьте, освободился ли порт
lsof -i :8000
lsof -i :8001

# Запустите заново
python3 main.py
```

### Повреждена база данных

```bash
# Восстановите из бэкапа
cp backups/db_20260810_120000.sqlite3 db.sqlite3

# Или создайте заново
rm db.sqlite3
alembic upgrade head
```

### Потерян .env файл

```bash
# Восстановите из бэкапа
cp backups/env_20260810_120000.env .env

# Или создайте заново
cp .env.example .env
nano .env  # Заполните переменные
```

---

## 📞 Контакты

При возникновении проблем:
1. Проверьте логи в `logs/`
2. Проверьте этот runbook
3. Обратитесь к документации в `docs/`

---

**Поддерживаемые версии:**
- Python: 3.12+
- Ollama: latest
- Telegram Bot API: aiogram 3.x
- Telegram UserBot: Telethon 1.30+
