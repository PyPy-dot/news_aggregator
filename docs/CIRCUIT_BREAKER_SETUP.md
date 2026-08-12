# 🔌 Circuit Breaker — Защита от каскадных сбоев

**Версия:** 1.0  
**Дата:** 2026-08-10

---

## 📋 Обзор

Circuit Breaker (автоматический выключатель) — паттерн для защиты системы от каскадных сбоев при недоступности внешних сервисов.

### Проблемы, которые решает

| Проблема | Решение |
|----------|---------|
| **Многократные вызовы недоступного сервиса** | Блокировка вызовов на время восстановления |
| **Каскадные сбои** | Изоляция проблемного сервиса |
| **Отсутствие информации о состоянии** | Статистика и мониторинг состояний |
| **Долгое восстановление** | Автоматическая проверка восстановления (HALF_OPEN) |

---

## 🏗️ Архитектура

### Состояния Circuit Breaker

```
┌──────────────┐
│   CLOSED     │ ← Нормальная работа, вызовы проходят
│   (Закрыт)   │
└──────┬───────┘
       │ Порог ошибок достигнут
       ▼
┌──────────────┐
│    OPEN      │ ← Вызовы блокируются, recovery timeout идёт
│   (Открыт)   │
└──────┬───────┘
       │ Recovery timeout истёк
       ▼
┌──────────────┐
│  HALF_OPEN   │ ← Один тестовый вызов для проверки
│ (Полуоткрыт) │
└──────┬───────┘
       │
       ├─────────────┐
       │             │
       ▼             ▼
┌──────────┐   ┌──────────┐
│ SUCCESS  │   │ FAILURE  │
│    →     │   │    →     │
│  CLOSED  │   │   OPEN   │
└──────────┘   └──────────┘
```

### Компоненты

| Компонент | Описание |
|-----------|----------|
| **CircuitBreaker** | Основной класс с логикой переключения состояний |
| **CircuitBreakerManager** | Менеджер для управления несколькими breaker'ами |
| **CircuitStats** | Статистика вызовов (успехи, ошибки, latency) |
| **CircuitState** | Enum состояний (CLOSED, OPEN, HALF_OPEN) |

---

## ⚙️ Настройка

### Базовое использование

```python
from services.core.circuit_breaker import CircuitBreaker

# Создание breaker
breaker = CircuitBreaker(
    name="ollama",           # Имя для логирования
    failure_threshold=5,     # Порог ошибок для открытия
    recovery_timeout=30.0,   # Время до проверки (сек)
    timeout=60.0,            # Таймаут вызова (сек)
)

# Использование как декоратор
@breaker
async def call_external_service():
    ...

# Или вручную
async with breaker.call():
    result = await some_operation()
```

### Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `name` | — | Имя breaker (для логов и метрик) |
| `failure_threshold` | `5` | Количество ошибок для открытия |
| `recovery_timeout` | `30.0` | Время до попытки восстановления (сек) |
| `half_open_max_calls` | `1` | Макс. тестовых вызовов в HALF_OPEN |
| `timeout` | `None` | Таймаут вызова (сек) |
| `expected_exceptions` | `(Exception,)` | Типы исключений, считающиеся ошибками |

---

## 📦 Интеграция с LLM провайдерами

### Автоматическая защита

Все LLM провайдеры имеют встроенный circuit breaker:

```python
from services.core.llm_provider import OllamaProvider, OpenAIProvider

# Ollama с circuit breaker
ollama = OllamaProvider(
    base_url='http://localhost:11434',
    failure_threshold=5,      # 5 ошибок → OPEN
    recovery_timeout=30.0,    # 30 сек до проверки
    timeout=60.0,             # 60 сек на вызов
)

# OpenAI с circuit breaker
openai = OpenAIProvider(
    api_key='sk-...',
    failure_threshold=5,
    recovery_timeout=30.0,
    timeout=30.0,
)
```

### Проверка состояния

```python
# Получить состояние circuit breaker
state = ollama.get_circuit_breaker_state()

# Пример вывода:
{
    'name': 'ollama:http://localhost:11434',
    'state': 'closed',
    'is_closed': True,
    'is_open': False,
    'stats': {
        'total_calls': 100,
        'successful_calls': 95,
        'failed_calls': 5,
        'rejected_calls': 0,
        'consecutive_failures': 0,
        'avg_response_time_ms': 1250.5,
    },
    'config': {
        'failure_threshold': 5,
        'recovery_timeout': 30.0,
        'timeout': 60.0,
    }
}
```

---

## 🔧 Менеджер circuit breaker'ов

### Управление несколькими breaker'ами

```python
from services.core.circuit_breaker import (
    CircuitBreakerManager,
    create_circuit_breaker,
    get_circuit_breaker_manager,
)

# Создание менеджера
manager = CircuitBreakerManager()

# Добавление breaker'ов
manager.add(CircuitBreaker(name="telegram", failure_threshold=3))
manager.add(CircuitBreaker(name="rss_parser", failure_threshold=5))

# Или через helper-функцию
breaker = create_circuit_breaker(
    name="anthropic_api",
    failure_threshold=5,
    recovery_timeout=30.0,
)

# Получение breaker по имени
breaker = manager.get("telegram")
breaker = get_circuit_breaker("telegram")

# Проверка всех состояний
states = manager.get_all_states()

# Сброс всех breaker'ов
await manager.reset_all()

# Проверка здоровья
if manager.all_closed:
    print("Все сервисы здоровы")
else:
    open_breakers = manager.get_open_breakers()
    print(f"Проблемы: {open_breakers}")
```

---

## 📊 Мониторинг и алерты

### Prometheus метрики (пример)

```python
from prometheus_client import Counter, Gauge, Histogram

# Метрики
cb_state = Gauge('circuit_breaker_state', 'Состояние breaker', ['name'])
cb_failures = Counter('circuit_breaker_failures_total', 'Ошибки breaker', ['name'])
cb_rejected = Counter('circuit_breaker_rejected_total', 'Отклонённые вызовы', ['name'])
cb_latency = Histogram('circuit_breaker_latency_ms', 'Latency вызовов', ['name'])

# Обновление метрик
def update_cb_metrics(name: str, state: dict):
    cb_state.labels(name).set({
        'closed': 1, 'open': 0, 'half_open': 0
    }[state['state']])
    cb_failures.labels(name).inc(state['stats']['failed_calls'])
    cb_rejected.labels(name).inc(state['stats']['rejected_calls'])
    cb_latency.labels(name).observe(state['stats']['avg_response_time_ms'])
```

### Grafana дашборд (пример запросов)

```promql
# Количество открытых breaker'ов
count(circuit_breaker_state == 0)

# Ошибки по сервисам за 5 мин
sum(rate(circuit_breaker_failures_total[5m])) by (name)

# Средний latency по сервисам
histogram_quantile(0.95, rate(circuit_breaker_latency_ms_bucket[5m]))
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты circuit breaker
pytest tests/test_core/test_circuit_breaker.py -v

# С покрытием
pytest tests/test_core/test_circuit_breaker.py -v --cov=services/core/circuit_breaker
```

### Тестовые сценарии

| Тест | Описание |
|------|----------|
| `test_initial_state_closed` | Начальное состояние CLOSED |
| `test_success_keeps_closed` | Успешные вызовы сохраняют CLOSED |
| `test_failures_open_circuit` | Ошибки открывают circuit |
| `test_open_rejects_calls` | OPEN отклоняет вызовы |
| `test_recovery_timeout_to_half_open` | Recovery → HALF_OPEN |
| `test_half_open_success_to_closed` | Успех в HALF_OPEN → CLOSED |
| `test_half_open_failure_to_open` | Ошибка в HALF_OPEN → OPEN |
| `test_timeout_exception` | Таймаут вызова |
| `test_stats_tracking` | Отслеживание статистики |
| `test_decorator_usage` | Использование как декоратор |

---

## 🛠️ Примеры использования

### Пример 1: Защита вызова Telegram API

```python
from services.core.circuit_breaker import CircuitBreaker

telegram_cb = CircuitBreaker(
    name="telegram_api",
    failure_threshold=3,       # Telegram часто блокирует
    recovery_timeout=60.0,     # 1 минута до проверки
    timeout=10.0,              # 10 сек таймаут
)

@telegram_cb
async def send_telegram_message(chat_id: int, text: str):
    from aiogram import Bot
    bot = Bot(token='...')
    await bot.send_message(chat_id, text)

# Использование
try:
    await send_telegram_message(123456, "Hello")
except CircuitBreakerError:
    logger.warning("Telegram API недоступен, сообщение отложено")
```

### Пример 2: Защита RSS парсера

```python
from services.core.circuit_breaker import CircuitBreaker

rss_cb = CircuitBreaker(
    name="rss_parser",
    failure_threshold=5,
    recovery_timeout=120.0,    # 2 минуты — RSS может долго восстанавливаться
    timeout=30.0,              # 30 сек на парсинг
)

async def parse_rss_feed(url: str):
    async with rss_cb.call():
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()

# Использование
try:
    content = await parse_rss_feed("https://example.com/rss")
except CircuitBreakerError:
    logger.error(f"RSS парсер недоступен: {url}")
except CircuitBreakerError as e:
    if e.state == CircuitState.OPEN:
        logger.warning(f"RSS парсер в состоянии OPEN, пропускаем {url}")
```

### Пример 3: Интеграция с FallbackLLMProvider

```python
from services.core.llm_provider import FallbackLLMProvider, OllamaProvider, OpenAIProvider

# Провайдеры уже имеют встроенные circuit breaker'ы
fallback = FallbackLLMProvider(
    providers=[
        OllamaProvider(
            base_url='http://localhost:11434',
            failure_threshold=5,
            recovery_timeout=30.0,
        ),
        OpenAIProvider(
            api_key='sk-...',
            failure_threshold=5,
            recovery_timeout=30.0,
        ),
    ],
    retry_attempts=3,
)

# Автоматическая защита:
# 1. Ollama недоступен → circuit breaker открывается
# 2. Fallback переключается на OpenAI
# 3. После восстановления Ollama → автоматическое возвращение
```

---

## 🚨 Troubleshooting

### Проблема: Circuit breaker постоянно открывается

**Возможные причины:**
1. Слишком низкий `failure_threshold`
2. Слишком короткий `recovery_timeout`
3. Реальные проблемы с сервисом

**Решение:**
```python
# Увеличить порог и время восстановления
breaker = CircuitBreaker(
    name="problematic_service",
    failure_threshold=10,      # Было 5
    recovery_timeout=120.0,    # Было 30
)
```

### Проблема: Breaker не восстанавливается

**Возможные причины:**
1. Сервис действительно недоступен
2. `recovery_timeout` слишком короткий для проверки

**Решение:**
```python
# Проверить состояние
state = breaker.get_state_dict()
print(f"State: {state['state']}")
print(f"Last failure: {state['stats']['last_failure_time']}")

# Принудительный сброс (если сервис точно здоров)
await breaker.reset()
```

### Проблема: Высокий rejected_calls

**Возможные причины:**
1. Частые сбои сервиса
2. Недостаточный `recovery_timeout`

**Решение:**
```python
# Увеличить recovery_timeout для стабильности
breaker = CircuitBreaker(
    name="unstable_service",
    recovery_timeout=300.0,  # 5 минут
)
```

---

## 📈 Рекомендации

### Настройки для разных сервисов

| Сервис | failure_threshold | recovery_timeout | timeout |
|--------|-------------------|------------------|---------|
| **Ollama (локальный)** | 5 | 30s | 60s |
| **OpenAI API** | 5 | 30s | 30s |
| **Anthropic API** | 5 | 30s | 30s |
| **Telegram API** | 3 | 60s | 10s |
| **RSS парсер** | 5 | 120s | 30s |
| **Web парсер** | 5 | 60s | 15s |

### Best practices

1. **Логгируйте все переключения состояний** — помогает при отладке
2. **Настройте алерты на OPEN состояние** — быстрое реагирование
3. **Мониторьте `rejected_calls`** — индикатор проблем
4. **Используйте разные пороги для разных сервисов** — не универсально
5. **Тестируйте fallback сценарии** — проверяйте восстановление

---

## 📝 Changelog

### v1.0 (2026-08-10)
- ✅ CircuitBreaker класс с полной логикой
- ✅ CircuitBreakerManager для управления
- ✅ Статистика вызовов (CircuitStats)
- ✅ Интеграция с LLM провайдерами
- ✅ Тесты (24 сценария, 100% покрытие)
- ✅ Документация

---

**Автор:** AI-агент Стефания  
**Связанные документы:**
- [LLM_FALLBACK_SETUP.md](LLM_FALLBACK_SETUP.md) — Fallback LLM провайдеры
- [ARCHITECTURE.md](ARCHITECTURE.md) — общая архитектура
- [MONITORING_SETUP.md](MONITORING_SETUP.md) — мониторинг (в разработке)
