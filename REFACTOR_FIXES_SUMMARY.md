# Refactoring Fixes Summary

## Дата: 2026-08-06

### Исправленные проблемы

---

## 1. Ошибка векторного поиска: `'_type'` KeyError

**Проблема:** Периодическая ошибка `[ERROR] ... Ошибка векторного поиска событий: '_type'`

**Причина:** В metadata коллекций ChromaDB добавлялся ключ `'type': 'event'`/`'type': 'news'`/`'type': 'post'`, но при поиске и обработке результатов код не учитывал, что этот ключ может отсутствовать или metadata может быть пустым.

**Исправления:**

### `services/vector_search/search_engine.py`
- Удалён ключ `'type'` из metadata во всех методах (`add_event`, `add_news`, `add_post`) — он не использовался в коде
- Импорт `json` перемещён в начало файла (был в конце после класса)

### `services/vector_search/chroma_client.py`
- Метод `search()` переписан с безопасной обработкой metadata:
  ```python
  metadata = results['metadatas'][0][i] if results['metadatas'] else {}
  distance = results['distances'][0][i] if results['distances'] else 0
  ```
- Используется `.get()` для безопасного доступа к ключам metadata

**Статус:** ✅ Исправлено

---

## 2. Проблемы с расшифровкой Telegram ID в UserRepository

**Проблема:** Метод `decrypt_user_id()` мог выбрасывать необработанные исключения при:
- Неверном ключе шифрования
- Повреждённых данных в БД
- Некорректном формате зашифрованной строки

**Исправления:**

### `services/util.py`
- Добавлена обработка исключений в `decrypt_user_id()`:
  - `InvalidTag` — неверный ключ или повреждённые данные
  - `ValueError`, `UnicodeDecodeError` — некорректный формат
  - Общее `Exception` — для любых неожиданных ошибок
- Добавлено логирование ошибок с деталями

### `database/repositories/users.py`
- Добавлен импорт `logging`
- Метод `get_user_telegram_id()` обёрнут в try/except с логированием
- Добавлен новый безопасный метод `get_user_telegram_id_safe()`:
  ```python
  def get_user_telegram_id_safe(self, user: User) -> int | None:
      """Возвращает None вместо выброса исключения."""
  ```

**Статус:** ✅ Исправлено

---

## Изменённые файлы

| Файл | Изменения |
|------|-----------|
| `services/vector_search/search_engine.py` | Удалён ключ 'type' из metadata, перемещён импорт json |
| `services/vector_search/chroma_client.py` | Безопасная обработка metadata в search() |
| `services/util.py` | Обработка исключений в decrypt_user_id() |
| `database/repositories/users.py` | Логирование ошибок, новый безопасный метод |

---

## Тестирование

### Ручная проверка
```bash
# Проверка синтаксиса
python3 -m py_compile services/vector_search/search_engine.py
python3 -m py_compile services/vector_search/chroma_client.py
python3 -m py_compile services/util.py
python3 -m py_compile database/repositories/users.py
```

### Рекомендуемые тесты
1. Протестировать векторный поиск с пустыми metadata
2. Протестировать расшифровку с неверным ключом
3. Протестировать метод `get_user_telegram_id_safe()`

---

## Обратная совместимость

Все изменения обратно совместимы:
- Удаление ключа `'type'` из metadata не влияет на существующий код (он не использовался)
- `decrypt_user_id()` сохраняет сигнатуру и поведение (исключения пробрасываются)
- Новый метод `get_user_telegram_id_safe()` — дополнение, не замена

---

## Следующие шаги

1. Добавить юнит-тесты на исправленный функционал
2. Протестировать на реальных данных
3. Рассмотреть возможность миграции существующих записей векторного поиска (удаление 'type' из старых metadata)
