"""
Settings — Настройки веб-админки.

Предоставляет:
- Просмотр и редактирование .env файла
- Управление переменными окружения
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from services.web_admin.api.app import get_optional_user
from services.web_admin.config import get_version

logger = logging.getLogger(__name__)

router = APIRouter()

# Пути
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
PROJECT_ROOT = BASE_DIR.parent.parent  # news_aggregator/
ENV_FILE = PROJECT_ROOT / ".env"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Категории переменных для группировки
ENV_CATEGORIES = {
    "Application": ["APP_VERSION"],
    "Database": ["DB_USER", "DB_PASSWORD", "DB_NAME", "DB_HOST", "DB_PORT"],
    "Telegram Bot": ["BOT_TOKEN", "API_ID", "API_HASH", "PHONE_NUMBER"],
    "Telegram Proxy": ["TELEGRAM_PROXY", "TELEGRAM_MTPROTO_PROXY"],
    "Listener Bot": ["DISABLE_LISTENER_BOT", "LISTENER_2FA_ENABLED", "LISTENER_2FA_PROVIDER", "LISTENER_2FA_SECRET"],
    "Admin": ["ADMIN_ID", "JWT_SECRET"],
    "AI/LLM": ["OLLAMA_HOST", "OLLAMA_MODEL"],
    "Vector DB": ["CHROMA_HOST"],
    "Redis": ["REDIS_URL"],
    "Logging": ["LOG_LEVEL", "ENCRYPTION_KEY"],
    "Web Admin": ["WEB_ADMIN_HOST", "WEB_ADMIN_PORT", "WEB_ADMIN_JWT_SECRET", "WEB_ADMIN_SESSION_EXPIRE_HOURS"],
}

# Переменные которые можно редактировать (безопасные)
EDITABLE_VARS = {
    "APP_VERSION": {"type": "text", "description": "Версия приложения"},
    "DB_USER": {"type": "text", "description": "Пользователь БД"},
    "DB_PASSWORD": {"type": "password", "description": "Пароль БД"},
    "DB_NAME": {"type": "text", "description": "Имя БД"},
    "DB_HOST": {"type": "text", "description": "Хост БД"},
    "DB_PORT": {"type": "number", "description": "Порт БД"},
    "BOT_TOKEN": {"type": "password", "description": "Токен Telegram бота"},
    "API_ID": {"type": "text", "description": "API ID Telegram"},
    "API_HASH": {"type": "password", "description": "API Hash Telegram"},
    "PHONE_NUMBER": {"type": "text", "description": "Номер телефона Telegram"},
    "TELEGRAM_PROXY": {"type": "text", "description": "Proxy для Telegram"},
    "TELEGRAM_MTPROTO_PROXY": {"type": "text", "description": "MTProto Proxy"},
    "DISABLE_LISTENER_BOT": {"type": "boolean", "description": "Отключить ListenerBot"},
    "LISTENER_2FA_ENABLED": {"type": "boolean", "description": "Включить 2FA для ListenerBot"},
    "LISTENER_2FA_PROVIDER": {"type": "text", "description": "2FA провайдер (google/yandex)"},
    "LISTENER_2FA_SECRET": {"type": "password", "description": "2FA секрет"},
    "ADMIN_ID": {"type": "text", "description": "Telegram ID администратора"},
    "JWT_SECRET": {"type": "password", "description": "JWT секрет"},
    "OLLAMA_HOST": {"type": "text", "description": "Ollama хост"},
    "OLLAMA_MODEL": {"type": "text", "description": "Ollama модель"},
    "CHROMA_HOST": {"type": "text", "description": "ChromaDB хост"},
    "REDIS_URL": {"type": "text", "description": "Redis URL"},
    "LOG_LEVEL": {"type": "select", "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], "description": "Уровень логирования"},
    "ENCRYPTION_KEY": {"type": "password", "description": "Ключ шифрования"},
    "WEB_ADMIN_HOST": {"type": "text", "description": "Web Admin хост"},
    "WEB_ADMIN_PORT": {"type": "number", "description": "Web Admin порт"},
    "WEB_ADMIN_JWT_SECRET": {"type": "password", "description": "Web Admin JWT секрет"},
    "WEB_ADMIN_SESSION_EXPIRE_HOURS": {"type": "number", "description": "Время жизни сессии (часы)"},
}


def parse_env_file(file_path: Path) -> dict:
    """
    Распарсить .env файл.

    Returns:
        Dict с переменными
    """
    env_vars = {}

    if not file_path.exists():
        return env_vars

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Пропускаем пустые строки и комментарии
            if not line or line.startswith('#'):
                continue

            # Парсим KEY=VALUE
            match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
            if match:
                key = match.group(1)
                value = match.group(2)

                # Убираем кавычки если есть
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                env_vars[key] = {
                    "value": value,
                    "line": line_num,
                    "raw": line
                }

    return env_vars


def write_env_file(file_path: Path, env_vars: dict) -> bool:
    """
    Записать .env файл.

    Args:
        file_path: Путь к файлу
        env_vars: Dict с переменными {key: value}

    Returns:
        True если успешно
    """
    try:
        # Читаем существующий файл
        lines = []
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        # Обновляем значения
        updated_keys = set()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', stripped)
                if match:
                    key = match.group(1)
                    if key in env_vars:
                        # Форматируем новую строку
                        value = env_vars[key]
                        if ' ' in value or '"' in value or "'" in value:
                            lines[i] = f'{key}="{value}"\n'
                        else:
                            lines[i] = f'{key}={value}\n'
                        updated_keys.add(key)

        # Добавляем новые переменные в конец
        for key, value in env_vars.items():
            if key not in updated_keys:
                if ' ' in value or '"' in value or "'" in value:
                    lines.append(f'{key}="{value}"\n')
                else:
                    lines.append(f'{key}={value}\n')

        # Пишем файл
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return True

    except Exception as e:
        logger.error(f"Ошибка записи .env: {e}", exc_info=True)
        return False


@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """Страница настроек."""
    env_vars = parse_env_file(ENV_FILE)

    # Группируем переменные
    grouped_vars = {}
    for category, keys in ENV_CATEGORIES.items():
        category_vars = []
        for key in keys:
            if key in env_vars:
                var_info = EDITABLE_VARS.get(key, {"type": "text", "description": ""})
                category_vars.append({
                    "key": key,
                    "value": env_vars[key]["value"],
                    **var_info
                })
        if category_vars:
            grouped_vars[category] = category_vars

    # Добавляем некатегоризированные
    categorized_keys = set(k for keys in ENV_CATEGORIES.values() for k in keys)
    uncategorized = []
    for key, info in env_vars.items():
        if key not in categorized_keys:
            var_info = EDITABLE_VARS.get(key, {"type": "text", "description": ""})
            uncategorized.append({
                "key": key,
                "value": info["value"],
                **var_info
            })

    if uncategorized:
        grouped_vars["Other"] = uncategorized

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "user": user,
            "version": get_version(),
            "grouped_vars": grouped_vars,
            "env_file_exists": ENV_FILE.exists()
        }
    )


@router.get("/api/env")
async def get_env_vars(user: Optional[dict] = Depends(get_optional_user)):
    """Получить все переменные окружения."""
    env_vars = parse_env_file(ENV_FILE)

    result = {}
    for key, info in env_vars.items():
        var_info = EDITABLE_VARS.get(key, {"type": "text", "description": ""})
        result[key] = {
            "value": info["value"],
            "editable": key in EDITABLE_VARS,
            **var_info
        }

    return JSONResponse(content={
        "success": True,
        "variables": result
    })


@router.post("/api/env")
async def update_env_vars(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Обновить переменные окружения.

    Body: {"variables": {"KEY": "value", ...}}
    """
    try:
        data = await request.json()
        variables = data.get("variables", {})

        # Валидация
        if not isinstance(variables, dict):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Неверный формат данных"}
            )

        # Проверяем что все ключи редактируемые
        for key in variables.keys():
            if key not in EDITABLE_VARS:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": f"Переменная {key} не может быть изменена"}
                )

        # Записываем файл
        success = write_env_file(ENV_FILE, variables)

        if success:
            logger.info(f"✅ .env обновлен: {list(variables.keys())}")
            return JSONResponse(content={
                "success": True,
                "message": "Настройки сохранены. Перезапустите приложение для применения."
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Ошибка записи файла"}
            )

    except Exception as e:
        logger.error(f"Ошибка обновления .env: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.post("/api/env/restart")
async def restart_services(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Перезапустить сервисы после изменения настроек.

    Внимание: Это требует внешней оркестрации (docker-compose restart или аналог)
    """
    # В реальной реализации здесь был бы вызов docker-compose или systemd
    # Для现在 просто возвращаем инструкцию
    return JSONResponse(content={
        "success": True,
        "message": "Для применения настроек перезапустите приложение",
        "instructions": [
            "Остановите сервисы: docker-compose down",
            "Запустите заново: docker-compose up -d",
            "Или: systemctl restart news-aggregator"
        ]
    })
