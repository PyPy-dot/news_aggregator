# Docker Контейнеризация — News Aggregator v3.5.0

**Дата:** 2026-08-09  
**Задача:** PLAN_SUMMARY_v3.5.0.md #6  
**Статус:** ✅ Выполнено

---

## 📋 Описание

Docker контейнеризация для всех компонентов News Aggregator.

**Сервисы (7):**
1. `app` — Основное приложение (бот, listener, scheduler)
2. `web-admin` — Web интерфейс админки
3. `db` — PostgreSQL 15
4. `chromadb` — ChromaDB (векторный поиск)
5. `ollama` — Ollama (LLM)
6. `redis` — Кэш и очереди
7. `nginx` — Reverse proxy

---

## 📁 Созданные файлы

| Файл | Назначение |
|------|------------|
| `Dockerfile` | Образ для app и web-admin |
| `docker-compose.yml` | Development конфигурация |
| `docker-compose.prod.yml` | Production конфигурация |
| `.dockerignore` | Исключения для Docker |
| `nginx.conf` | Nginx конфигурация (dev) |
| `.env.example` | Шаблон переменных окружения |

---

## 🚀 Быстрый старт (Development)

### 1. Клонирование и настройка

```bash
# Копируем .env.example
cp .env.example .env

# Редактируем .env (заполняем TELEGRAM_BOT_TOKEN и др.)
nano .env
```

### 2. Запуск

```bash
# Запускаем все сервисы
docker-compose up -d

# Проверяем статус
docker-compose ps

# Смотрим логи
docker-compose logs -f
```

### 3. Доступ

| Сервис | URL | Порт |
|--------|-----|------|
| Основное приложение | http://localhost | 8000 |
| Web админка | http://localhost:8001 | 8001 |
| PostgreSQL | localhost | 5432 |
| ChromaDB | http://localhost:8002 | 8002 |
| Ollama | http://localhost:11434 | 11434 |
| Redis | localhost | 6379 |
| Nginx | http://localhost | 80 |

---

## 🔒 Production развёртывание

### 1. Настройка

```bash
# Копируем production конфиг
cp .env.example .env

# Заполняем переменные (обязательно измените пароли!)
nano .env
```

### 2. SSL сертификаты (опционально)

```bash
# Создаём директорию для SSL
mkdir -p ssl

# Копируем сертификаты
cp /path/to/fullchain.pem ssl/
cp /path/to/privkey.pem ssl/
```

### 3. Запуск

```bash
# Запускаем с production конфигом
docker-compose -f docker-compose.prod.yml up -d

# Проверяем статус
docker-compose -f docker-compose.prod.yml ps
```

---

## 📊 Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx (80/443)                       │
│                    Reverse Proxy                             │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐            ┌─────────────────┐
    │   App (8000)    │            │ Web Admin (8001)│
    │  Bot, Listener, │            │   FastAPI       │
    │   Scheduler     │            │                 │
    └────────┬────────┘            └────────┬────────┘
             │                               │
             └───────────┬───────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ PostgreSQL  │ │  ChromaDB   │ │    Redis    │
│   (5432)    │ │   (8000)    │ │   (6379)    │
│             │ │             │ │             │
│  - users    │ │  - vectors  │ │  - cache    │
│  - posts    │ │  - events   │ │  - sessions │
│  - channels │ │             │ │             │
│  - rss      │ │             │ │             │
└─────────────┘ └─────────────┘ └─────────────┘
                         │
                         ▼
                ┌─────────────┐
                │   Ollama    │
                │  (11434)    │
                │             │
                │  - qwen2.5  │
                │  - 7b model │
                └─────────────┘
```

---

## 🔧 Управление

### Просмотр логов

```bash
# Все логи
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f app
docker-compose logs -f web-admin
docker-compose logs -f db
```

### Перезапуск сервисов

```bash
# Перезапустить всё
docker-compose restart

# Перезапустить конкретный сервис
docker-compose restart app
```

### Остановка

```bash
# Остановить всё
docker-compose down

# Остановить и удалить тома (осторожно!)
docker-compose down -v
```

### Обновление

```bash
# Собрать новые образы
docker-compose build

# Пересоздать контейнеры
docker-compose up -d --force-recreate
```

---

## 📊 Ресурсы

### Development

| Сервис | CPU | RAM |
|--------|-----|-----|
| app | 1 core | 2 GB |
| web-admin | 0.5 core | 1 GB |
| db | 1 core | 2 GB |
| chromadb | 0.5 core | 1 GB |
| ollama | 2 cores | 4 GB |
| redis | 0.25 core | 0.5 GB |
| **ИТОГО** | **5.25 cores** | **10.5 GB** |

### Production

| Сервис | CPU | RAM |
|--------|-----|-----|
| app | 2 cores | 4 GB |
| web-admin | 1 core | 1 GB |
| db | 2 cores | 4 GB |
| chromadb | 1 core | 2 GB |
| ollama | 4 cores | 8 GB |
| redis | 0.5 core | 1 GB |
| **ИТОГО** | **10.5 cores** | **20 GB** |

---

## 🔐 Безопасность (Production)

### Обязательно измените:

1. **Пароль PostgreSQL** в `.env`
2. **JWT_SECRET** в `.env`
3. **TELEGRAM_BOT_TOKEN** в `.env`

### Рекомендации:

1. Используйте HTTPS (настройте nginx.prod.conf)
2. Включите firewall
3. Обновляйте образы регулярно
4. Настройте мониторинг
5. Делайте бэкапы базы данных

---

## 📝 Следующие шаги

### После развёртывания:

1. **Настройте Telegram бота:**
   - Получите токен в @BotFather
   - Добавьте API ID и HASH

2. **Инициализируйте базу данных:**
   ```bash
   docker-compose exec app alembic upgrade head
   ```

3. **Загрузите модель Ollama:**
   ```bash
   docker-compose exec ollama ollama pull qwen2.5:7b
   ```

4. **Проверьте работу:**
   - Откройте http://localhost
   - Войдите в админку через /admin

---

## ✅ Чек-лист выполнения

- [x] Dockerfile для app
- [x] Dockerfile для web-admin
- [x] docker-compose.yml (development)
- [x] docker-compose.prod.yml (production)
- [x] .dockerignore
- [x] nginx.conf (development)
- [x] .env.example
- [x] Документация

---

**Исполнитель:** AI-агент Стефания  
**Дата завершения:** 2026-08-09  
**Статус:** ✅ **Готово к production**
