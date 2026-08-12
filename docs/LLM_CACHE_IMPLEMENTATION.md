# Реализация кэширования LLM ответов

**Дата:** 2026-08-09  
**Версия:** 3.2.0  
**Статус:** ✅ Завершено

---

## Обзор

Добавлено кэширование ответов AI агентов (LLM) для снижения нагрузки на Ollama и ускорения обработки повторяющихся запросов.

**Преимущества:**
- ⚡ Ускорение обработки повторяющихся запросов (экономия 2-5 секунд на запрос)
- 📉 Снижение нагрузки на Ollama API
- 💾 LRU-кэш с настраиваемым размером
- ⏰ TTL 24 часа (настраиваемый)
- 🔒 Async-safe операции

---

## Архитектура

### Компоненты

```
services/ai_agent/
├── cache.py              # LLMResponseCache (LRU-кэш)
│   ├── CacheEntry        # Запись в кэше с TTL
│   └── LLMResponseCache  # Основной класс кэша
│
└── agents/
    └── base.py           # BaseAgent (интеграция кэша)
        └── send_question()  # Метод с кэшированием
```

### Принцип работы

```
┌─────────────────────────────────────────────────────────────┐
│                   BaseAgent.send_question()                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │   Проверка кэша         │
              │   (хэш промпта + модель)│
              └─────────────────────────┘
                    │               │
                    │ Hit           │ Miss
                    ▼               ▼
        ┌───────────────────┐  ┌──────────────────┐
        │  Вернуть из кэша  │  │  Запрос к Ollama │
        │  (экономия 2-5с)  │  │  + сохранить     │
        └───────────────────┘  └──────────────────┘
```

---

## Изменения

### 1. Кэш (`services/ai_agent/cache.py`)

**Классы:**
- `CacheEntry` — запись в кэше с TTL
- `LLMResponseCache` — LRU-кэш с async поддержкой

**Методы:**
- `get(prompt, model)` — получить значение
- `set(prompt, value, model, ttl)` — сохранить значение
- `delete(prompt, model)` — удалить запись
- `clear()` — очистить весь кэш
- `stats()` — статистика (hits, misses, hit_rate)
- `cleanup()` — удалить истёкшие записи

**Параметры:**
- `max_size=1000` — максимальное количество записей
- `default_ttl=86400` (24 часа) — время жизни записи

**Кэширование:**
```python
from services.ai_agent.cache import get_llm_cache

cache = get_llm_cache()
await cache.set("prompt", "response", model="qwen2.5:7b")
result = await cache.get("prompt", model="qwen2.5:7b")
```

---

### 2. BaseAgent (`services/ai_agent/agents/base.py`)

**Изменения:**
- Метод `send_question()` обновлён для использования кэша
- Новый параметр `use_cache=True` (по умолчанию True)
- Метод `_get_cache_prompt()` — создание ключа кэша

**Ключ кэша:**
```python
# Включает системный промпт для точного匹配
key = f"{system_prompt}|||{user_message}"
hashed = sha256(key)
```

---

### 3. Экспорт (`services/ai_agent/__init__.py`)

**Добавлено:**
```python
from services.ai_agent.cache import (
    LLMResponseCache,
    get_llm_cache,
    reset_llm_cache,
)
```

---

## Использование

### Базовое

```python
from services.ai_agent.agents import AnalystAgent

agent = AnalystAgent()

# Первый запрос (кэш miss, запрос к Ollama)
response1 = await agent.send_question("Какая категория у этой новости?")

# Повторный запрос (кэш hit, без запроса к Ollama)
response2 = await agent.send_question("Какая категория у этой новости?")
# response2 === response1 (из кэша)
```

### Отключение кэша

```python
# Для одноразовых запросов
response = await agent.send_question("Уникальный вопрос", use_cache=False)
```

### Статистика кэша

```python
from services.ai_agent.cache import get_llm_cache

cache = get_llm_cache()
stats = await cache.stats()

print(f"Hits: {stats['hits']}")
print(f"Misses: {stats['misses']}")
print(f"Hit Rate: {stats['hit_rate']}%")
print(f"Size: {stats['size']}/{stats['max_size']}")
```

### Очистка кэша

```python
from services.ai_agent.cache import reset_llm_cache

# Полный сброс кэша
await reset_llm_cache()
```

---

## Производительность

### Benchmark (ожидаемый)

| Сценарий | Без кэша | С кэшем | Улучшение |
|----------|----------|---------|-----------|
| Повторяющийся запрос | 2-5с | <10ms | 200-500x |
| Hit Rate (после 100 запросов) | - | ~40-60% | - |
| Нагрузка на Ollama | 100% | 40-60% | 40-60% снижение |

### Метрики

```
Hits: 150
Misses: 100
Hit Rate: 60.0%
Size: 250/1000
Evictions: 0
```

---

## Тестирование

### Запуск тестов

```bash
# Все тесты кэширования
pytest tests/test_agents/test_llm_cache.py -v

# С покрытием
pytest tests/test_agents/test_llm_cache.py --cov=services/ai_agent/cache -v
```

### Результат

```
======================== 21 passed, 1 warning in 2.38s =========================
```

**Покрытие:**
- ✅ CacheEntry (создание, TTL, expiration)
- ✅ LRU eviction
- ✅ TTL expiration
- ✅ Concurrent access
- ✅ Singleton pattern
- ✅ Stats & cleanup

---

## Архитектурные решения

### 1. LRU (Least Recently Used)

При переполнении кэша удаляется самая старая запись:

```python
def _evict_if_needed(self):
    while len(self._cache) >= self.max_size:
        self._cache.popitem(last=False)  # Удаляем первую (старейшую)
```

### 2. Хэширование промптов

SHA-256 для создания уникального ключа:

```python
def _compute_key(self, prompt: str, model: str = "") -> str:
    key_data = f"{model}:{prompt}"
    return hashlib.sha256(key_data.encode('utf-8')).hexdigest()
```

### 3. Async Lock

Защита от race conditions:

```python
async with self._lock:
    # Операции с кэшем
```

### 4. TTL с гранулярностью

Каждая запись имеет свой TTL:

```python
entry = CacheEntry(value, ttl_seconds)
```

---

## Рекомендации

### Настройка размера кэша

**Для development:**
```python
cache = get_llm_cache(max_size=100, default_ttl=3600)  # 1 час
```

**Для production:**
```python
cache = get_llm_cache(max_size=5000, default_ttl=86400)  # 24 часа
```

### Мониторинг

Добавьте метрики Prometheus:

```python
# services/monitoring/metrics.py
from prometheus_client import Counter, Gauge

llm_cache_hits = Counter('llm_cache_hits_total', 'Total cache hits')
llm_cache_misses = Counter('llm_cache_misses_total', 'Total cache misses')
llm_cache_size = Gauge('llm_cache_size', 'Current cache size')
```

### Инвалидация кэша

При обновлении промптов:

```python
# Сбросить кэш при изменении промптов
await reset_llm_cache()
```

---

## Метрики выполнения

| Задача | Статус |
|--------|--------|
| Создание `services/ai_agent/cache.py` | ✅ |
| Интеграция в `BaseAgent.send_question()` | ✅ |
| Обновление `__init__.py` | ✅ |
| Тесты (21 тест) | ✅ 21/21 |
| Документация | ✅ |
| **Итого** | **✅ Завершено** |

---

## Следующие шаги

### Рекомендации

1. **Добавить метрики Prometheus** — мониторинг hit/miss rate
2. **Персистентный кэш** — Redis для сохранения между перезапусками
3. **Префетчинг** — предзагрузка популярных запросов в кэш
4. **Адаптивный TTL** — динамическая настройка TTL на основе частоты запросов

---

**Исполнитель:** AI-агент Стефания  
**Дата завершения:** 2026-08-09  
**Статус:** ✅ Готово к production
