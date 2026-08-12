# 📝 Structured JSON Logging — Настройка для ELK/Loki

**Версия:** 1.0  
**Дата:** 2026-08-10

---

## 📋 Обзор

Структурированное JSON логирование для интеграции с системами централизованного сбора логов:

- **Elasticsearch + Logstash + Kibana (ELK)**
- **Grafana Loki**
- **Splunk**
- **Datadog**

### Формат лога

```json
{
  "timestamp": "2026-08-10T12:00:00.123Z",
  "level": "INFO",
  "message": "User logged in",
  "logger": "services.bot.handlers.commands",
  "module": "commands",
  "function": "start_handler",
  "line": 42,
  "thread": "MainThread",
  "thread_id": 12345,
  "extra": {
    "user_id": 123456,
    "action": "login"
  }
}
```

---

## 🏗️ Архитектура

### Компоненты

```
┌─────────────────────────────────────────────────────────────┐
│                    Application                               │
│  logger.info("User action", extra={"user_id": 123})         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    JSONFormatter                             │
│  - timestamp (ISO 8601, UTC)                                │
│  - level, message, logger                                   │
│  - module, function, line                                   │
│  - extra context                                            │
│  - exception/traceback                                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐
│ Console      │ │ File     │ │ External │
│ (colored)    │ │ (JSON)   │ │ (ELK)    │
└──────────────┘ └──────────┘ └──────────┘
```

### Поля лога

| Поле | Тип | Описание |
|------|-----|----------|
| `timestamp` | string | ISO 8601, UTC (Z suffix) |
| `level` | string | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `message` | string | Основное сообщение |
| `logger` | string | Имя логгера (модуль) |
| `module` | string | Имя модуля |
| `function` | string | Имя функции |
| `line` | int | Номер строки |
| `thread` | string | Имя потока |
| `thread_id` | int | ID потока |
| `extra` | object | Дополнительный контекст |
| `exception` | object | Информация об исключении |

---

## ⚙️ Настройка

### Базовая настройка

```python
from services.logging_json import setup_json_logging

# В main.py
setup_json_logging(
    level="INFO",
    log_to_file=True,
    log_file="logs/app.json.log",
    include_extra_context=True,
)
```

### Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `level` | `"INFO"` | Уровень логирования |
| `log_to_console` | `True` | Логировать в консоль |
| `log_to_file` | `False` | Логировать в файл |
| `log_file` | `"logs/app.json.log"` | Путь к файлу логов |
| `log_file_max_bytes` | `10485760` (10MB) | Макс. размер файла |
| `log_file_backup_count` | `7` | Количество backup файлов |
| `include_extra_context` | `True` | Включать extra контекст |
| `colored_console` | `True` | Цветной вывод в консоль |

---

## 🛠️ Использование

### Получение логгера

```python
from services.logging_json import get_logger

logger = get_logger(__name__)

# Логирование
logger.info("Processing started")
logger.debug(f"User data: {user_data}")
logger.warning("Deprecated API call")
logger.error(f"Failed to process: {error}")
```

### Extra контекст

```python
# Добавление контекста
logger.info(
    "User action completed",
    extra={
        "user_id": 123456,
        "action": "purchase",
        "amount": 99.99,
        "currency": "RUB",
    }
)
```

**Вывод:**
```json
{
  "timestamp": "2026-08-10T12:00:00.123Z",
  "level": "INFO",
  "message": "User action completed",
  "logger": "services.bot.handlers.payment",
  "extra": {
    "user_id": 123456,
    "action": "purchase",
    "amount": 99.99,
    "currency": "RUB"
  }
}
```

### Логирование исключений

```python
try:
    result = await process_payment(user_id, amount)
except Exception as e:
    logger.exception(
        "Payment processing failed",
        extra={
            "user_id": user_id,
            "amount": amount,
            "error_type": type(e).__name__,
        }
    )
```

**Вывод:**
```json
{
  "timestamp": "2026-08-10T12:00:00.123Z",
  "level": "ERROR",
  "message": "Payment processing failed",
  "logger": "services.bot.handlers.payment",
  "exception": {
    "type": "PaymentError",
    "message": "Insufficient funds",
    "traceback": "Traceback (most recent call last):\n  ...",
    "traceback_lines": [...]
  }
}
```

### Декоратор для async функций

```python
from services.logging_json import log_async_context

@log_async_context
async def handle_callback(callback_data: str):
    # Автоматическое логирование начала/конца/ошибок
    await process_callback(callback_data)
```

**Вывод:**
```json
{"timestamp": "...", "level": "DEBUG", "message": "▶️ Starting handle_callback", ...}
{"timestamp": "...", "level": "DEBUG", "message": "✅ Completed handle_callback (125.50ms)", ...}
```

---

## 📊 Интеграция с ELK

### Logstash конфигурация

```ruby
# logstash.conf
input {
  file {
    path => "/var/log/news_aggregator/*.json.log"
    start_position => "beginning"
    codec => "json"
  }
}

filter {
  date {
    match => ["timestamp", "ISO8601"]
    target => "@timestamp"
  }

  mutate {
    rename => {
      "level" => "log_level"
      "logger" => "component"
    }
  }

  if [extra] {
    mutate {
      add_field => {
        "user_id" => "%{[extra][user_id]}"
        "action" => "%{[extra][action]}"
      }
    }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "news-aggregator-%{+YYYY.MM.dd}"
  }
}
```

### Kibana dashboard

**Примеры запросов:**

```kibana
# Ошибки за последний час
level: ERROR AND @timestamp > now-1h

# Действия конкретного пользователя
extra.user_id: 123456

# Логирование по модулю
logger: services.bot.handlers.*

# Медленные операции (elapsed_ms > 1000)
extra.elapsed_ms: >1000
```

---

## 📊 Интеграция с Grafana Loki

### Promtail конфигурация

```yaml
# promtail.yml
scrape_configs:
  - job_name: news-aggregator
    static_configs:
      - targets:
          - localhost
        labels:
          job: news-aggregator
          __path__: /var/log/news_aggregator/*.json.log

    pipeline_stages:
      - json:
          expressions:
            level: level
            logger: logger
            user_id: extra.user_id
            action: extra.action

      - labels:
          level:
          logger:
          action:

      - output:
          source: message
```

### Grafana LogQL запросы

```logql
# Ошибки за последний час
{job="news-aggregator", level="ERROR"} | json | __timestamp__ > now() - 1h

# Действия по пользователю
{job="news-aggregator"} | json | user_id = "123456"

# Агрегация по уровням
sum by (level) (count_over_time({job="news-aggregator"}[1h]))

# Топ модулей по количеству логов
topk(5, sum by (logger) (count_over_time({job="news-aggregator"}[1h])))
```

---

## 🔧 Утилиты

### Чтение JSON логов (tail)

```python
from services.logging_json import tail_json_log

# Читать последние 100 строк
for entry in tail_json_log("logs/app.json.log", lines=100):
    print(f"{entry['timestamp']} [{entry['level']}] {entry['message']}")

# Следить за изменениями (tail -f)
for entry in tail_json_log("logs/app.json.log", follow=True):
    print(f"{entry['timestamp']} [{entry['level']}] {entry['message']}")
```

### Парсинг строки лога

```python
from services.logging_json import parse_json_log_line

line = '{"timestamp": "...", "level": "INFO", "message": "Test"}'
data = parse_json_log_line(line)

print(data["level"])  # INFO
print(data["message"])  # Test
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
pytest tests/test_services/test_json_logging.py -v

# С покрытием
pytest tests/test_services/test_json_logging.py -v --cov=services/logging_json
```

### Тестовые сценарии

| Тест | Описание |
|------|----------|
| `test_basic_format` | Базовое JSON форматирование |
| `test_extra_context` | Extra контекст |
| `test_exception_format` | Форматирование исключений |
| `test_timestamp_format` | Формат timestamp |
| `test_colored_output` | Цветной вывод |
| `test_multi_handler` | Множественные хендлеры |
| `test_context_filter` | Контекстный фильтр |
| `test_level_filter` | Фильтр по уровню |
| `test_full_logging_flow` | Полный цикл логирования |

---

## 🚨 Troubleshooting

### Проблема: Логи не пишутся в файл

**Возможные причины:**
1. Нет прав на запись в директорию
2. Не указана `log_to_file=True`

**Решение:**
```bash
# Проверить права
ls -la logs/

# Создать директорию
mkdir -p logs && chmod 755 logs
```

### Проблема: JSON не парсится

**Возможные причины:**
1. Несколько записей в одной строке
2. Невалидный JSON в extra

**Решение:**
```python
# Использовать JSON Lines формат (одна запись = одна строка)
# Каждая запись разделяется \n

# Для чтения использовать:
with open("app.json.log") as f:
    for line in f:
        data = json.loads(line)  # Парсить каждую строку отдельно
```

### Проблема: Extra контекст не попадает в лог

**Возможные причины:**
1. `include_extra_context=False`
2. Ключи extra конфликтуют со стандартными атрибутами

**Решение:**
```python
setup_json_logging(include_extra_context=True)

# Избегать стандартных имён:
# args, asctime, created, exc_info, filename, funcName,
# levelname, levelno, lineno, module, msecs, msg, name,
# pathname, process, processName, relativeCreated, stack_info,
# thread, threadName, message
```

---

## 📈 Best practices

### 1. Используйте структурированный контекст

```python
# ✅ Хорошо
logger.info("Payment processed", extra={
    "user_id": user_id,
    "amount": amount,
    "currency": currency,
})

# ❌ Плохо
logger.info(f"Payment processed for user {user_id} amount {amount}")
```

### 2. Избегайте PII в логах

```python
# ✅ Хорошо
logger.info("User authenticated", extra={"user_id": hashed_id})

# ❌ Плохо
logger.info(f"User {email} logged in with password {password}")
```

### 3. Логируйте timing операций

```python
start = time.time()
result = await expensive_operation()
elapsed_ms = (time.time() - start) * 1000

logger.info(
    "Operation completed",
    extra={"elapsed_ms": elapsed_ms, "result_size": len(result)}
)
```

### 4. Используйте уровни логирования правильно

| Уровень | Когда использовать |
|---------|-------------------|
| DEBUG | Отладочная информация (значения переменных, flow) |
| INFO | Нормальная работа (старт/стоп, действия пользователей) |
| WARNING | Предупреждения (некритичные ошибки, fallback) |
| ERROR | Ошибки (не удалось выполнить операцию) |
| CRITICAL | Критичные ошибки (система неработоспособна) |

---

## 📝 Changelog

### v1.0 (2026-08-10)
- ✅ JSONFormatter с полным набором полей
- ✅ ColoredConsoleHandler для разработки
- ✅ MultiHandler для логирования в несколько destinations
- ✅ ContextFilter, LevelFilter фильтры
- ✅ log_async_context декоратор
- ✅ Утилиты (parse_json_log_line, tail_json_log)
- ✅ Тесты (18 сценариев)
- ✅ Документация

---

**Автор:** AI-агент Стефания  
**Связанные документы:**
- [HEALTH_CHECK_SETUP.md](HEALTH_CHECK_SETUP.md) — Health check API
- [CIRCUIT_BREAKER_SETUP.md](CIRCUIT_BREAKER_SETUP.md) — Circuit breaker
- [MONITORING_SETUP.md](MONITORING_SETUP.md) — Общий мониторинг
