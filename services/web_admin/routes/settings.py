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
    "Application": ["APP_VERSION", "TELEGRAM_USE_IPV6"],
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
# reload: immediate = сразу, service:X = рестарт сервиса, full = рестарт всего
EDITABLE_VARS = {
    "APP_VERSION": {"type": "text", "reload": "immediate", "description": "Версия приложения"},
    "DB_USER": {"type": "text", "reload": "full", "description": "Пользователь БД"},
    "DB_PASSWORD": {"type": "password", "reload": "full", "description": "Пароль БД"},
    "DB_NAME": {"type": "text", "reload": "full", "description": "Имя БД"},
    "DB_HOST": {"type": "text", "reload": "full", "description": "Хост БД"},
    "DB_PORT": {"type": "number", "reload": "full", "description": "Порт БД"},
    "BOT_TOKEN": {"type": "password", "reload": "service:bot", "description": "Токен Telegram бота"},
    "API_ID": {"type": "text", "reload": "service:listener", "description": "API ID Telegram"},
    "API_HASH": {"type": "password", "reload": "service:listener", "description": "API Hash Telegram"},
    "PHONE_NUMBER": {"type": "text", "reload": "service:listener", "description": "Номер телефона Telegram"},
    "TELEGRAM_PROXY": {"type": "text", "reload": "service:listener", "description": "Proxy для Telegram"},
    "TELEGRAM_MTPROTO_PROXY": {"type": "text", "reload": "service:listener", "description": "MTProto Proxy"},
    "TELEGRAM_USE_IPV6": {"type": "boolean", "reload": "service:listener", "description": "Использовать IPv6 для Telegram"},
    "DISABLE_LISTENER_BOT": {"type": "boolean", "reload": "service:listener", "description": "Отключить ListenerBot"},
    "LISTENER_2FA_ENABLED": {"type": "boolean", "reload": "service:listener", "description": "Включить 2FA для ListenerBot"},
    "LISTENER_2FA_PROVIDER": {"type": "text", "reload": "service:listener", "description": "2FA провайдер (google/yandex)"},
    "LISTENER_2FA_SECRET": {"type": "password", "reload": "service:listener", "description": "2FA секрет"},
    "ADMIN_ID": {"type": "text", "reload": "immediate", "description": "Telegram ID администратора"},
    "JWT_SECRET": {"type": "password", "reload": "full", "description": "JWT секрет"},
    "OLLAMA_HOST": {"type": "text", "reload": "immediate", "description": "Ollama хост"},
    "OLLAMA_MODEL": {"type": "text", "reload": "immediate", "description": "Ollama модель"},
    "CHROMA_HOST": {"type": "text", "reload": "immediate", "description": "ChromaDB хост"},
    "REDIS_URL": {"type": "text", "reload": "immediate", "description": "Redis URL"},
    "LOG_LEVEL": {"type": "select", "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], "reload": "immediate", "description": "Уровень логирования"},
    "ENCRYPTION_KEY": {"type": "password", "reload": "full", "description": "Ключ шифрования"},
    "WEB_ADMIN_HOST": {"type": "text", "reload": "full", "description": "Web Admin хост"},
    "WEB_ADMIN_PORT": {"type": "number", "reload": "full", "description": "Web Admin порт"},
    "WEB_ADMIN_JWT_SECRET": {"type": "password", "reload": "full", "description": "Web Admin JWT секрет"},
    "WEB_ADMIN_SESSION_EXPIRE_HOURS": {"type": "number", "reload": "immediate", "description": "Время жизни сессии (часы)"},
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

    Returns structured response with what was applied immediately
    and what requires restart.
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

        # Читаем старые значения чтобы определить что изменилось
        old_env = parse_env_file(ENV_FILE)

        # Записываем файл
        success = write_env_file(ENV_FILE, variables)

        if not success:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Ошибка записи файла"}
            )

        # Определяем какие переменные реально изменились
        changed_keys = []
        for key, new_value in variables.items():
            old_info = old_env.get(key)
            if old_info is None or old_info["value"] != new_value:
                changed_keys.append(key)

        # Перезагружаем settings в памяти
        from config.settings import reload_settings
        reload_settings()

        # Применяем immediate настройки
        applied_immediately = []
        for key in changed_keys:
            var_info = EDITABLE_VARS.get(key, {})
            reload_type = var_info.get("reload", "full")

            if reload_type == "immediate":
                # LOG_LEVEL — применить сразу
                if key == "LOG_LEVEL":
                    import logging as log_mod
                    log_mod.getLogger().setLevel(variables[key])
                    logger.info(f"🔧 LOG_LEVEL применён: {variables[key]}")

                applied_immediately.append(key)

        # Определяем что требует рестарта
        requires_restart = {}  # service_name -> [keys]
        needs_full_restart = []
        for key in changed_keys:
            var_info = EDITABLE_VARS.get(key, {})
            reload_type = var_info.get("reload", "full")

            if reload_type == "immediate":
                continue
            elif reload_type == "full":
                if key not in needs_full_restart:
                    needs_full_restart.append(key)
            elif reload_type.startswith("service:"):
                service = reload_type.split(":", 1)[1]
                if service not in requires_restart:
                    requires_restart[service] = []
                requires_restart[service].append(key)

        # Проверяем состояние сервисов через service_manager
        running_services = {}
        try:
            from services.service_manager import get_service_manager
            manager = get_service_manager()
            for svc in requires_restart:
                running_services[svc] = manager.is_running(svc)
        except Exception:
            pass

        # Формируем ответ
        result = {
            "success": True,
            "message": "Настройки сохранены",
            "changed": changed_keys,
            "applied_immediately": applied_immediately,
            "requires_restart": requires_restart,
            "needs_full_restart": needs_full_restart,
            "running_services": running_services,
        }

        # Определяем итоговое сообщение
        messages = []
        if applied_immediately:
            messages.append(f"Применено сразу: {', '.join(applied_immediately)}")
        if requires_restart:
            for svc, keys in requires_restart.items():
                svc_name = {"bot": "Бот", "listener": "Лисенер", "scheduler": "Шедулер"}.get(svc, svc)
                if running_services.get(svc):
                    messages.append(f"Требует рестарта {svc_name}: {', '.join(keys)}")
                else:
                    messages.append(f"Применится при запуске {svc_name}: {', '.join(keys)}")
        if needs_full_restart:
            messages.append(f"Требует перезапуска приложения: {', '.join(needs_full_restart)}")

        if messages:
            result["message"] = ". ".join(messages) + "."

        logger.info(f"✅ .env обновлен: {changed_keys}")
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Ошибка обновления .env: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.post("/api/env/restart")
async def restart_services(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Перезапустить указанные сервисы после изменения настроек.

    Body: {"services": ["bot", "listener", "scheduler"]}
    """
    try:
        data = await request.json()
        services = data.get("services", [])

        results = {}
        try:
            from services.service_manager import get_service_manager
            manager = get_service_manager()

            for svc in services:
                try:
                    if manager.is_running(svc):
                        # Рестарт: стоп → старт
                        await manager.stop_service(svc)
                        await manager.start_service(svc)
                        results[svc] = "restarted"
                    else:
                        results[svc] = "not_running"
                except Exception as e:
                    results[svc] = f"error: {e}"
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"ServiceManager недоступен: {e}"}
            )

        return JSONResponse(content={
            "success": True,
            "message": "Сервисы перезапущены",
            "results": results,
        })

    except Exception as e:
        logger.error(f"Ошибка рестарта сервисов: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )
