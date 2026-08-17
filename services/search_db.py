"""
Database-agnostic search helpers.

Предоставляет функции для построения поисковых запросов,
адаптированных к конкретной СУБД (SQLite, PostgreSQL, MySQL).

Использует абстрактный слой services/database для определения
типа СУБД и выбора соответствующей стратегии поиска.
"""

import logging
import re
from typing import Optional

from sqlalchemy import Column, or_, and_
from sqlalchemy.sql import Select

from services.database.enums import DatabaseType

logger = logging.getLogger(__name__)


def _get_db_type() -> Optional[DatabaseType]:
    """Определить тип СУБД из глобального сервиса."""
    try:
        from services.database import get_database_service
        svc = get_database_service()
        return svc.db_type
    except Exception:
        return None


# =============================================================================
# Case-insensitive LIKE
# =============================================================================

def ilike(
    col: Column,
    query: str,
    _db_type: Optional[DatabaseType] = None,
) -> any:
    """
    Case-insensitive LIKE, адаптированный к СУБД.

    Принимает query (строка без wildcard), сам добавляет %.

    - PostgreSQL: ILIKE (нативный case-insensitive)
    - MySQL: LIKE (MySQL LIKE — case-insensitive по умолчанию для utf8)
    - SQLite: OR из нескольких LIKE (LOWER/UPPER), т.к. NOCASE индекс
      не работает для Unicode
    """
    if _db_type is None:
        _db_type = _get_db_type()

    pattern = f"%{query}%"

    if _db_type == DatabaseType.POSTGRESQL:
        return col.ilike(pattern)

    elif _db_type == DatabaseType.MYSQL:
        return col.like(pattern)

    else:
        # SQLite и fallback: OR из нескольких вариантов регистра
        patterns = [pattern, f"%{query.lower()}%", f"%{query.upper()}%"]
        return or_(col.like(p) for p in patterns)


def ilike_any(
    col: Column,
    queries: list[str],
    _db_type: Optional[DatabaseType] = None,
) -> any:
    """OR-составной case-insensitive LIKE для нескольких запросов."""
    if not queries:
        return True  # type: ignore[return-value]
    return or_(ilike(col, q, _db_type=_db_type) for q in queries)


# =============================================================================
# Multi-column text search
# =============================================================================

def text_search_condition(
    query: str,
    text_col: Column,
    category_col: Optional[Column] = None,
    tags_col: Optional[Column] = None,
    _db_type: Optional[DatabaseType] = None,
) -> any:
    """
    Поиск по нескольким текстовым столбцам с учётом СУБД.

    Для PostgreSQL используется ILIKE, для MySQL — LIKE,
    для SQLite — множественные LIKE с разными регистрами.
    """
    if _db_type is None:
        _db_type = _get_db_type()

    conditions: list[any] = []

    # Текстовый столбец (обязательный)
    conditions.append(ilike(text_col, query, _db_type=_db_type))

    # Категория
    if category_col is not None:
        conditions.append(ilike(category_col, query, _db_type=_db_type))

    # Теги
    if tags_col is not None:
        conditions.append(ilike(tags_col, query, _db_type=_db_type))

    return or_(*conditions)


# =============================================================================
# Apply filter (LIKE / ==)
# =============================================================================

def apply_filter(
    stmt: Select,
    model: type,
    field: str,
    value: str,
    _db_type: Optional[DatabaseType] = None,
) -> Select:
    """
    Применить нестрогий фильтр.

    Для текстовых полей используется ILIKE / LIKE с учётом СУБД,
    для числовых — точное сравнение.
    """
    if _db_type is None:
        _db_type = _get_db_type()

    if not field or not value:
        return stmt

    try:
        col = getattr(model, field, None)
        if col is None:
            logger.warning(f"Column {field!r} not found on {model.__name__}")
            return stmt

        if field in ("tags", "category", "event_category", "urgency", "moderation_status"):
            if _db_type == DatabaseType.POSTGRESQL:
                stmt = stmt.where(col.ilike(f"%{value}%"))
            elif _db_type == DatabaseType.MYSQL:
                stmt = stmt.where(col.like(f"%{value}%"))
            else:
                patterns = [
                    f"%{value}%",
                    f"%{value.lower()}%",
                    f"%{value.upper()}%",
                ]
                stmt = stmt.where(or_(col.like(p) for p in patterns))
        else:
            stmt = stmt.where(col == value)

    except Exception as e:
        logger.warning(f"Error applying filter [{field}={value}]: {e}")

    return stmt


# =============================================================================
# Morphological search (Python-level, DB-agnostic)
# =============================================================================

def search_morph(haystack: str, needle: str, min_common_len: int = 4) -> bool:
    """
    Морфологический поиск через n-gram совпадение.

    Каждое слово запроса должно совпасть с каким-то словом текста
    по общей подстроке длины >= min_common_len. Независим от СУБД.
    """
    # Защита от None / нестроковых значений
    haystack = str(haystack or "")
    needle = str(needle or "")

    def clean_tokens(t: str) -> list[str]:
        t = re.sub(r'<[^>]+>', ' ', t).lower()
        t = re.sub(r'[^\w\s]', ' ', t)
        return [w for w in t.split() if len(w) >= 3]

    needle_tokens = clean_tokens(needle)
    haystack_tokens = clean_tokens(haystack)

    # Пустой needle не матчит ничего (раньше возвращал True)
    if not needle_tokens:
        return False

    # Пустой haystack не может матчить
    if not haystack_tokens:
        return False

    haystack_set = set(haystack_tokens)

    # Индекс: первый символ → список слов
    h_index: dict[str, list[str]] = {}
    for w in haystack_tokens:
        h_index.setdefault(w[0], []).append(w)

    for nw in needle_tokens:
        if nw in haystack_set:
            continue

        candidates = h_index.get(nw[0], [])
        matched = False
        for hw in candidates:
            for n in range(len(nw), min_common_len - 1, -1):
                for i in range(len(nw) - n + 1):
                    if nw[i:i + n] in hw:
                        matched = True
                        break
                if matched:
                    break
        if not matched:
            return False
    return True
