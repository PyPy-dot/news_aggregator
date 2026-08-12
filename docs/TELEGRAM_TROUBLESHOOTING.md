# 🔧 Диагностика проблем с подключением к Telegram

**Версия:** 1.0  
**Дата:** 2026-08-12

---

## 🚨 Симптомы

```
TelegramNetworkError: HTTP Client says - Request timeout error
```

Или:

```
❌ Ошибка подключения к Telegram: Не удалось инициализировать бота
```

---

## ✅ Чеклист диагностики

### 1. Проверьте токен бота

```bash
# В .env файле:
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# Проверка:
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

**Ожидаемый ответ:**
```json
{"ok":true,"result":{"id":123456,"is_bot":true,"first_name":"News Bot","username":"news_bot"}}
```

**Если ошибка:**
- Токен неверный → получите новый в [@BotFather](https://t.me/BotFather)
- Бот заблокирован → разблокируйте через @BotFather

---

### 2. Проверьте соединение с Telegram

```bash
# Проверка доступности API Telegram
curl -v https://api.telegram.org/

# Проверка DNS
nslookup api.telegram.org

# Проверка маршрута
traceroute api.telegram.org
```

**Если не доступно:**
- Нет интернета → проверьте соединение
- Telegram заблокирован → используйте прокси (см. ниже)

---

### 3. Настройте прокси (если Telegram заблокирован)

#### Вариант A: SOCKS5 прокси

```bash
# В .env файле:
TELEGRAM_PROXY=socks5://proxy.example.com:1080

# Пример с авторизацией:
TELEGRAM_PROXY=socks5://user:pass@proxy.example.com:1080
```

#### Вариант B: HTTP прокси

```bash
# В .env файле:
TELEGRAM_PROXY=http://proxy.example.com:8080
```

#### Вариант C: MTProto прокси (официальные прокси Telegram)

```bash
# В .env файле:
TELEGRAM_MTPROTO_PROXY=server.example.com:443:secret

# Или в формате URL:
TELEGRAM_MTPROTO_PROXY=https://t.me/proxy?server=server.example.com&port=443&secret=secret
```

**Где взять прокси:**
- [@ProxyMT](https://t.me/ProxyMT) — бесплатные MTProto прокси
- [@MTProxy](https://t.me/MTProxy) — официальные прокси Telegram

---

### 4. Проверьте переменные окружения

```bash
# Убедитесь, что все обязательные переменные установлены:
cat .env | grep -E "BOT_TOKEN|API_ID|API_HASH|PHONE_NUMBER"

# Должно быть:
TELEGRAM_BOT_TOKEN=123456:...
API_ID=12345678
API_HASH=abcdef1234567890
PHONE_NUMBER=+79991234567
```

---

### 5. Проверьте логи

```bash
# Запустите приложение и смотрите логи:
python main.py 2>&1 | grep -E "ERROR|WARNING|Telegram"

# Или в Docker:
docker-compose logs -f app | grep -E "ERROR|Telegram"
```

**Типичные ошибки:**

| Ошибка | Решение |
|--------|---------|
| `Unauthorized` | Неверный токен бота |
| `TimeoutError` | Нет соединения или заблокирован |
| `FloodWaitError` | Слишком много запросов, подождите |
| `ConnectionResetError` | Проблемы с сетью или прокси |

---

### 6. Тестовый скрипт

Создайте файл `test_telegram.py`:

```python
"""Тест подключения к Telegram."""
import asyncio
import aiohttp

async def test_telegram():
    """Проверить доступность Telegram API."""
    url = "https://api.telegram.org/"
    
    print(f"🔍 Проверка {url}...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                print(f"✅ Telegram доступен: {resp.status}")
                return True
        except asyncio.TimeoutError:
            print("❌ Timeout: Telegram не отвечает")
            return False
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False

async def test_bot_token(token):
    """Проверить токен бота."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    
    print(f"🔍 Проверка токена бота...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                if data.get('ok'):
                    bot = data['result']
                    print(f"✅ Бот: @{bot.get('username', 'N/A')} ({bot['first_name']})")
                    return True
                else:
                    print(f"❌ Ошибка: {data}")
                    return False
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Проверка API
    api_ok = asyncio.run(test_telegram())
    
    # Проверка токена
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if token:
        token_ok = asyncio.run(test_bot_token(token))
    else:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        token_ok = False
    
    # Итог
    print("\n" + "="*50)
    if api_ok and token_ok:
        print("✅ Все проверки пройдены!")
    else:
        print("❌ Есть проблемы с подключением")
        if not api_ok:
            print("   - Telegram API недоступен")
        if not token_ok:
            print("   - Токен бота неверный")
```

Запуск:
```bash
source .venv/bin/activate
python test_telegram.py
```

---

## 🔧 Решения

### Проблема: Telegram заблокирован в регионе

**Решение 1: Использовать прокси**

```bash
# Найдите бесплатный прокси:
curl https://t.me/ProxyMT

# Добавьте в .env:
TELEGRAM_PROXY=socks5://proxy.example.com:1080
```

**Решение 2: Использовать MTProto прокси**

```bash
# Добавьте в .env:
TELEGRAM_MTPROTO_PROXY=server.example.com:443:secret
```

---

### Проблема: Таймаут при подключении

**Решение: Увеличить таймауты**

В `services/bot/bot.py` уже установлены увеличенные таймауты:
```python
timeout = aiohttp.ClientTimeout(
    total=300,      # 5 минут
    connect=120,    # 2 минуты
    sock_connect=120,
    sock_read=120
)
```

Если всё равно таймаут — проблема с сетью или прокси.

---

### Проблема: FloodWaitError (слишком много запросов)

**Решение: Подождать указанное время**

```
FloodWaitError: A wait of X seconds is required
```

Подождите X секунд перед повторной попыткой. Telegram ограничивает частоту запросов.

---

### Проблема: Unauthorized (неверный токен)

**Решение: Получить новый токен**

1. Откройте [@BotFather](https://t.me/BotFather)
2. `/mybots` → выберите вашего бота
3. `API Token` → скопируйте новый токен
4. Обновите в `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=новый_токен
   ```

---

## 📞 Поддержка

Если ничего не помогло:

1. Проверьте [@TelegramAPI](https://t.me/TelegramAPI) — нет ли проблем на стороне Telegram
2. Проверьте логи приложения на наличие других ошибок
3. Убедитесь, что используете последнюю версию кода

---

**Автор:** AI-агент Стефания  
**Дата:** 2026-08-12
