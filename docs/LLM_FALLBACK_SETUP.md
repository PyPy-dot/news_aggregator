# 🔁 Fallback LLM Provider — Настройка и использование

**Версия:** 1.0  
**Дата:** 2026-08-10

---

## 📋 Обзор

Система fallback-провайдеров обеспечивает бесперебойную работу AI-агентов при недоступности основного LLM-провайдера.

### Возможности

- ✅ **Автоматическое переключение** между провайдерами при ошибках
- ✅ **Retry логика** с экспоненциальной задержкой
- ✅ **Поддержка 3 провайдеров**: Ollama, OpenAI, Anthropic
- ✅ **Статистика** по каждому провайдеру (запросы, ошибки, latency)
- ✅ **Прозрачная работа** для AI-агентов (без изменений в коде)

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Agent                                  │
│              (Categorizer, Analyst, Editor)                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              FallbackLLMProvider                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Retry Logic (экспоненциальная задержка)            │   │
│  │  - retry_attempts: 3                                │   │
│  │  - retry_delay: 2s (2^attempt)                      │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Provider Chain (приоритет):                        │   │
│  │  1. OllamaProvider (основной)                       │   │
│  │  2. OpenAIProvider (fallback)                       │   │
│  │  3. AnthropicProvider (fallback)                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌─────────┐  ┌──────────┐  ┌──────────┐
   │ Ollama  │  │  OpenAI  │  │ Anthropic│
   │ Local   │  │   API    │  │   API    │
   └─────────┘  └──────────┘  └──────────┘
```

---

## ⚙️ Настройка

### 1. Переменные окружения

Скопируйте `.env.example` в `.env` и настройте провайдеры:

```bash
# =============================================================================
# LLM Providers (Fallback цепочка)
# =============================================================================

# Основной провайдер: ollama, openai, anthropic
LLM_PRIMARY_PROVIDER=ollama

# Ollama (локальный LLM)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# OpenAI API (fallback)
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=https://api.openai.com/v1

# Anthropic API (fallback)
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Fallback настройки
LLM_RETRY_ATTEMPTS=3
LLM_RETRY_DELAY_SECONDS=2
LLM_FALLBACK_ENABLED=true
```

### 2. Конфигурация fallback

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `LLM_PRIMARY_PROVIDER` | `ollama` | Основной провайдер (`ollama`, `openai`, `anthropic`) |
| `LLM_RETRY_ATTEMPTS` | `3` | Количество попыток перед fallback |
| `LLM_RETRY_DELAY_SECONDS` | `2` | Задержка между попытками (экспоненциальная) |
| `LLM_FALLBACK_ENABLED` | `true` | Включить автоматический fallback |

---

## 🔧 Примеры использования

### Пример 1: Настройка цепочки Ollama → OpenAI → Anthropic

```bash
# .env файл
LLM_PRIMARY_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

**Поведение:**
1. Запросы идут в Ollama
2. При ошибке Ollama → 3 retry с задержкой 2s, 4s, 8s
3. После retry → переключение на OpenAI
4. При ошибке OpenAI → переключение на Anthropic

### Пример 2: Только OpenAI (без локального Ollama)

```bash
LLM_PRIMARY_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

**Поведение:**
- Все запросы идут напрямую в OpenAI
- Fallback не настроен (можно добавить Ollama как fallback)

### Пример 3: OpenAI с Ollama как fallback

```bash
LLM_PRIMARY_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Ollama как fallback (автоматически добавляется)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

**Поведение:**
1. Запросы идут в OpenAI
2. При ошибке → переключение на Ollama (локальная модель)

---

## 📊 Статистика и мониторинг

### Получение статистики провайдеров

```python
from services.ai_agent.agents import CategorizerAgent

agent = CategorizerAgent()

# Получить статистику всех провайдеров
stats = agent.get_provider_stats()

# Пример вывода:
{
    'ollama': {
        'total': 100,
        'success': 95,
        'failed': 5,
        'fallbacks': 0,
        'avg_latency_ms': 1250.5,
        'healthy': True,
        'last_error': None,
    },
    'openai': {
        'total': 5,
        'success': 5,
        'failed': 0,
        'fallbacks': 5,  # Сработало 5 fallback'ов
        'avg_latency_ms': 450.2,
        'healthy': True,
        'last_error': None,
    }
}
```

### Логирование fallback-событий

```
⚠️ Ollama ошибка (попытка 1/3): ConnectionError: Cannot connect to Ollama
⏳ Пауза 2с перед следующей попыткой...
⚠️ Ollama ошибка (попытка 2/3): ConnectionError: Cannot connect to Ollama
⏳ Пауза 4с перед следующей попыткой...
⚠️ Ollama ошибка (попытка 3/3): ConnectionError: Cannot connect to Ollama
🔄 Переключение с ollama на openai
✅ Fallback сработал: openai после 1 неудачных провайдеров
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты fallback-провайдера
pytest tests/test_core/test_llm_fallback.py -v

# С покрытием
pytest tests/test_core/test_llm_fallback.py -v --cov=services/core/llm_provider
```

### Тестовые сценарии

| Тест | Описание |
|------|----------|
| `test_single_provider_success` | Единственный провайдер успешен |
| `test_fallback_on_first_failure` | Fallback при неудаче первого |
| `test_retry_before_fallback` | Retry попытки перед fallback |
| `test_all_providers_fail` | Все провайдеры недоступны |
| `test_fallback_stats` | Статистика fallback |
| `test_three_provider_chain` | Цепочка из 3 провайдеров |

---

## 🛠️ API

### Основные классы

#### `LLMProvider` (абстрактный класс)

```python
from services.core.llm_provider import LLMProvider, LLMMessage, LLMResponse

class MyProvider(LLMProvider):
    @property
    def name(self) -> str: ...
    
    @property
    def provider_type(self) -> ProviderType: ...
    
    async def chat(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse: ...
    
    async def is_available(self) -> bool: ...
```

#### `FallbackLLMProvider`

```python
from services.core.llm_provider import FallbackLLMProvider, OllamaProvider

fallback = FallbackLLMProvider(
    providers=[
        OllamaProvider(base_url='http://localhost:11434'),
        OpenAIProvider(api_key='sk-...'),
    ],
    retry_attempts=3,
    retry_delay_seconds=2.0,
)

response = await fallback.chat(
    messages=[LLMMessage(role='user', content='Hello')],
    model='qwen2.5:7b',
)
```

#### `get_llm_provider()`

```python
from services.core.llm_provider import get_llm_provider

# Получить провайдер из настроек (автоматически создаёт fallback)
provider = get_llm_provider()

# Использовать в агенте
from services.ai_agent.agents import CategorizerAgent

agent = CategorizerAgent(llm_provider=provider)
```

---

## 🚨 Troubleshooting

### Проблема: Ollama недоступен, fallback не срабатывает

**Решение:**
1. Проверьте, что OPENAI_API_KEY или ANTHROPIC_API_KEY указаны в `.env`
2. Убедитесь, что `LLM_FALLBACK_ENABLED=true`
3. Проверьте логи — должно быть сообщение о переключении

### Проблема: Constant fallback to OpenAI

**Решение:**
1. Проверьте доступность Ollama: `curl http://localhost:11434/api/tags`
2. Убедитесь, что модель загружена: `ollama pull qwen2.5:7b`
3. Проверьте логи Ollama на ошибки

### Проблема: Высокий latency при fallback

**Решение:**
1. Уменьшите `LLM_RETRY_ATTEMPTS` до 1-2
2. Уменьшите `LLM_RETRY_DELAY_SECONDS` до 1
3. Рассмотрите возможность использования только облачного провайдера

---

## 📈 Рекомендации

### Production конфигурация

```bash
# Основной: OpenAI (надёжность)
LLM_PRIMARY_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Fallback: Ollama (локально, экономия)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Retry настройки (оптимизировано для production)
LLM_RETRY_ATTEMPTS=2
LLM_RETRY_DELAY_SECONDS=1
```

### Экономия затрат

```bash
# Основной: Ollama (бесплатно)
LLM_PRIMARY_PROVIDER=ollama

# Fallback: OpenAI только для критичных запросов
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini  # Более дешёвая модель
```

---

## 📝 Changelog

### v1.0 (2026-08-10)
- ✅ Добавлены Ollama, OpenAI, Anthropic провайдеры
- ✅ Fallback-цепочка с автоматическим переключением
- ✅ Retry логика с экспоненциальной задержкой
- ✅ Статистика по провайдерам
- ✅ Интеграция с AI-агентами
- ✅ Тесты (15 сценариев)

---

**Автор:** AI-агент Стефания  
**Связанные документы:** 
- [ARCHITECTURE.md](ARCHITECTURE.md) — общая архитектура
- [AI_AGENTS.md](AI_AGENTS.md) — AI-агенты
- [CONFIGURATION.md](CONFIGURATION.md) — настройка приложения
