# Web Парсинг — базовая реализация v3.5.0

**Дата:** 2026-08-09  
**Задача:** PLAN_SUMMARY_v3.5.0.md #4  
**Статус:** 🔄 В работе (база создана)

---

## 📋 Описание

Парсинг новостей с сайтов, где нет RSS ленты.

**Возможности (базовая реализация):**
- requests + bs4 для статических сайтов
- Конфигурация через JSON
- Извлечение новостей по селекторам

---

## 📁 Созданные файлы

| Файл | Назначение |
|------|------------|
| `alembic/versions/..._add_web_parsing_tables.py` | Миграция БД |
| `database/models.py` | Модели WebSource, WebNews |
| `services/web/__init__.py` | Модуль web парсинга |
| `services/web/parser.py` | StaticWebParser, WebParserService |

---

## 🗄️ Схема БД

### Таблица web_sources
- id, name, url, category
- parser_config (JSON)
- is_active, last_checked
- check_interval_minutes

### Таблица web_news
- id, source_id, title, link
- description, content
- author, published_at
- category, processed, post_id

---

## 🔧 Использование

```python
from services.web.parser import StaticWebParser, ParserConfig

config = ParserConfig(
    name="Lenta.ru",
    url="https://lenta.ru/news",
    category="Новости",
    selectors={
        'article': 'article.news-item',
        'title': 'h3.title',
        'link': 'a[href]',
        'description': 'p.summary',
    }
)

parser = StaticWebParser(config)
news_items = parser.parse(config.url)
```

---

## 📊 Метрики

| Метрика | Значение |
|---------|----------|
| Создано файлов | 3 |
| Моделей | 2 |
| Статус | Базовая реализация |

---

## 🚀 Осталось реализовать

1. **Репозитории:**
   - WebSourceRepository
   - WebNewsRepository

2. **Интеграция со scheduler:**
   - Задача `_run_web_parser()` (каждые 60 мин)

3. **Конфигурация:**
   - YAML файлы для 5+ сайтов

4. **Dynamic Parser:**
   - Selenium для JavaScript сайтов

5. **Тесты:**
   - Тесты парсера
   - Интеграционные тесты

6. **Документация:**
   - Полная документация
   - Примеры конфигурации

---

**Исполнитель:** AI-агент Стефания  
**Статус:** 🔄 **Базовая реализация готова, требуется завершение**
