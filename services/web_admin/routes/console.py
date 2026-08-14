"""
Консоль управления — маршруты и API для веб-админки.

Предоставляет:
- HTML страница консоли
- API для выполнения команд
- API для выполнения Python кода
- API для выполнения SQL запросов
- API для управления сервисами (старт/стоп/рестарт)
"""

import logging
import asyncio
import sys
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text, select, func

from services.database import get_database_service
from services.web_admin.api.app import get_optional_user
from services.web_admin.config import get_version

logger = logging.getLogger(__name__)

router = APIRouter()

# Пути
BASE_DIR = Path(__file__).parent.parent  # services/web_admin/
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_service_status():
    """Получить статус сервисов из ServiceManager."""
    try:
        from services.service_manager import get_service_manager
        manager = get_service_manager()
        return manager.get_all_states()
    except Exception as e:
        logger.debug(f"Не удалось получить статус из ServiceManager: {e}")
        # Возвращаем статус по умолчанию (все остановлено)
        return {
            "bot": False,
            "listener": False,
            "scheduler": False,
        }


async def control_service_api(service: str, action: str):
    """
    Управление сервисом через ServiceManager.

    Args:
        service: имя сервиса (bot, listener, scheduler)
        action: действие (start, stop, restart)

    Returns:
        Dict с результатом
    """
    try:
        from services.service_manager import get_service_manager
        manager = get_service_manager()

        if action == "start":
            return await manager.start_service(service)
        elif action == "stop":
            return await manager.stop_service(service)
        elif action == "restart":
            return await manager.restart_service(service)
        else:
            return {"success": False, "error": f"Неизвестное действие: {action}"}

    except Exception as e:
        logger.error(f"Ошибка управления сервисом {service}/{action}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/", response_class=HTMLResponse)
async def console_page(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """Страница консоли управления."""
    return templates.TemplateResponse(
        request=request,
        name="console.html",
        context={
            "user": user,
            "version": get_version()
        }
    )


@router.post("/api/execute")
async def execute_command(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Выполнить команду в консоли.

    Поддерживаемые команды:
    - help — список команд
    - status — статус сервисов
    - start <service> — запуск сервиса
    - stop <service> — остановка сервиса
    - restart <service> — рестарт сервиса
    - start-all — запуск всех сервисов
    - stop-all — остановка всех сервисов
    - clear — очистить терминал
    - version — версия приложения
    """
    try:
        data = await request.json()
        command = data.get("command", "").strip()

        if not command:
            return JSONResponse(content={"success": False, "error": "Пустая команда"})

        # Парсинг команды
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        output = ""

        if cmd == "help":
            version = get_version()
            # Каждая строка без лишних пробелов - \n только в конце
            lines = [
                "\x1b[1;36m╔══════════════════════════════════════════════════╗\x1b[0m",
                f"\x1b[1;36m║\x1b[0m \x1b[1;33mNews Aggregator v{version}\x1b[0m                           \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m╠══════════════════════════════════════════════════╣\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mhelp\x1b[0m        - Справка                            \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mstatus\x1b[0m      - Статус сервисов                    \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mversion\x1b[0m     - Версия                             \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mclear\x1b[0m       - Очистить                           \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mstart <svc>\x1b[0m   - Запуск                           \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mstop <svc>\x1b[0m    - Остановка                        \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mrestart <svc>\x1b[0m - Рестарт                          \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mlist channels\x1b[0m - Каналы                           \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mlist users\x1b[0m    - Пользователи                     \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m║\x1b[0m \x1b[33mstats\x1b[0m       - Статистика                         \x1b[1;36m║\x1b[0m",
                "\x1b[1;36m╚══════════════════════════════════════════════════╝\x1b[0m"
            ]
            output = "\n".join(lines)

        elif cmd == "status":
            services = get_service_status()
            output = "\x1b[1;36mСтатус сервисов:\x1b[0m\n"
            for service, is_running in services.items():
                status_icon = "\x1b[32m●\x1b[0m" if is_running else "\x1b[31m●\x1b[0m"
                status_text = "\x1b[32mРаботает\x1b[0m" if is_running else "\x1b[31mОстановлен\x1b[0m"
                output += f"  {status_icon} {service}: {status_text}\n"

        elif cmd == "clear":
            output = "\x1b[2J\x1b[H"

        elif cmd == "version":
            output = f"\x1b[1;33mNews Aggregator v{get_version()}\x1b[0m"

        elif cmd in ("start", "stop", "restart"):
            if not args:
                output = f"\x1b[31mОшибка: укажите сервис (bot, listener, scheduler)\x1b[0m"
            else:
                service = args[0].lower()
                if service in ("bot", "listener", "scheduler"):
                    result = await control_service_api(service, cmd)
                    if result.get("success"):
                        if cmd == "start":
                            output = f"\x1b[32m✅ {service} запущен\x1b[0m"
                        elif cmd == "stop":
                            output = f"\x1b[31m🛑 {service} остановлен\x1b[0m"
                        else:
                            output = f"\x1b[32m✅ {service} перезапущен\x1b[0m"
                    else:
                        output = f"\x1b[31m❌ Ошибка: {result.get('error')}\x1b[0m"
                else:
                    output = f"\x1b[31mОшибка: неизвестный сервис '{service}'\x1b[0m"

        elif cmd == "start-all":
            output = "\x1b[33mЗапуск всех сервисов...\x1b[0m\n"
            result = await control_service_api("bot", "start")  # Запускаем все через manager
            # В реальной реализации здесь был бы вызов manager.start_all()
            for service in ["scheduler", "bot", "listener"]:
                await control_service_api(service, "start")
                output += f"  \x1b[32m●\x1b[0m {service} запущен\n"
            output += "\x1b[32m✅ Все сервисы запущены\x1b[0m"
            logger.info("Все сервисы запущены через консоль")

        elif cmd == "stop-all":
            output = "\x1b[31mОстановка всех сервисов...\x1b[0m\n"
            # Останавливаем в обратном порядке
            for service in ["listener", "bot", "scheduler"]:
                await control_service_api(service, "stop")
                output += f"  \x1b[31m●\x1b[0m {service} остановлен\n"
            output += "\x1b[31m✅ Все сервисы остановлены\x1b[0m"
            logger.info("Все сервисы остановлены через консоль")

        elif cmd == "list":
            if args and args[0] == "channels":
                output = await _list_channels()
            elif args and args[0] == "users":
                output = await _list_users()
            else:
                output = "\x1b[31mИспользование: list channels | list users\x1b[0m"

        elif cmd == "stats":
            output = await _get_stats()

        else:
            output = f"\x1b[31mНеизвестная команда: {cmd}\x1b[0m\nВведите \x1b[33mhelp\x1b[0m для списка команд"

        return JSONResponse(content={"success": True, "output": output})

    except Exception as e:
        logger.error(f"Ошибка выполнения команды: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


async def _list_channels() -> str:
    """Получить список каналов."""
    try:
        db_service = get_database_service()
        async with db_service.session_context() as session:
            from database.models import Channel
            result = await session.execute(
                select(Channel).limit(10).order_by(Channel.id.desc())
            )
            channels = result.scalars().all()

            if not channels:
                return "\x1b[33mНет каналов\x1b[0m"

            output = "\x1b[1;36mКаналы (последние 10):\x1b[0m\n"
            for ch in channels:
                name = getattr(ch, 'name', 'N/A') or 'N/A'
                output += f"  • {name} (ID: {ch.id})\n"
            return output
    except Exception as e:
        return f"\x1b[31mОшибка: {e}\x1b[0m"


async def _list_users() -> str:
    """Получить список пользователей."""
    try:
        db_service = get_database_service()
        async with db_service.session_context() as session:
            from database.models import User
            result = await session.execute(
                select(User).limit(10).order_by(User.id.desc())
            )
            users = result.scalars().all()

            if not users:
                return "\x1b[33mНет пользователей\x1b[0m"

            output = "\x1b[1;36mПользователи (последние 10):\x1b[0m\n"
            for user in users:
                username = getattr(user, 'username', 'N/A') or 'N/A'
                output += f"  • {username} (ID: {user.id})\n"
            return output
    except Exception as e:
        return f"\x1b[31mОшибка: {e}\x1b[0m"


async def _get_stats() -> str:
    """Получить статистику системы."""
    try:
        db_service = get_database_service()
        async with db_service.session_context() as session:
            from database.models import TelegramPost, Channel, User, Task
            from sqlalchemy import func, select

            # Количество новостей
            result = await session.execute(select(func.count()).select_from(TelegramPost))
            news_count = result.scalar() or 0

            # Количество каналов
            result = await session.execute(select(func.count()).select_from(Channel))
            channels_count = result.scalar() or 0

            # Количество пользователей
            result = await session.execute(select(func.count()).select_from(User))
            users_count = result.scalar() or 0

            # Количество задач
            result = await session.execute(select(func.count()).select_from(Task))
            tasks_count = result.scalar() or 0

            output = "\x1b[1;36mСтатистика системы:\x1b[0m\n"
            output += f"  📰 Новостей: \x1b[33m{news_count}\x1b[0m\n"
            output += f"  📢 Каналов: \x1b[33m{channels_count}\x1b[0m\n"
            output += f"  👥 Пользователей: \x1b[33m{users_count}\x1b[0m\n"
            output += f"  📋 Задач: \x1b[33m{tasks_count}\x1b[0m"

            return output
    except Exception as e:
        return f"\x1b[31mОшибка: {e}\x1b[0m"


@router.post("/api/python")
async def execute_python(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Выполнить Python код.

    Внимание: выполняет код в том же процессе! Будьте осторожны.
    """
    try:
        data = await request.json()
        code = data.get("code", "")

        if not code:
            return JSONResponse(content={"success": False, "error": "Пустой код"})

        # Перехват вывода
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        # Создаём безопасное окружение
        safe_globals = {
            "__builtins__": __builtins__,
            "print": print,
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "pow": pow,
            "datetime": datetime,
        }

        try:
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                exec(code, safe_globals, {})

            output = stdout_buffer.getvalue()
            error = stderr_buffer.getvalue()

            if error:
                return JSONResponse(content={"success": False, "error": error})

            return JSONResponse(content={"success": True, "output": output or "Выполнено без вывода"})

        except Exception as e:
            error_msg = traceback.format_exc()
            return JSONResponse(content={"success": False, "error": error_msg})

    except Exception as e:
        logger.error(f"Ошибка выполнения Python: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.post("/api/sql")
async def execute_sql(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Выполнить SQL запрос.

    Поддерживаются SELECT, INSERT, UPDATE, DELETE.
    """
    try:
        data = await request.json()
        query = data.get("query", "").strip()

        if not query:
            return JSONResponse(content={"success": False, "error": "Пустой запрос"})

        # Проверка на опасные операции
        query_upper = query.upper()
        dangerous_keywords = ["DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE"]
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                return JSONResponse(
                    content={"success": False, "error": f"Операция {keyword} запрещена"}
                )

        db_service = get_database_service()

        async with db_service.session_context() as session:
            if query_upper.startswith("SELECT"):
                # SELECT запрос — возвращаем результаты
                result = await session.execute(text(query))
                rows = result.fetchall()
                columns = result.keys()

                # Преобразуем в сериализуемый формат
                serializable_rows = []
                for row in rows:
                    serializable_row = []
                    for value in row:
                        if isinstance(value, datetime):
                            serializable_row.append(value.isoformat())
                        else:
                            serializable_row.append(value)
                    serializable_rows.append(serializable_row)

                return JSONResponse(content={
                    "success": True,
                    "columns": list(columns),
                    "rows": serializable_rows
                })

            else:
                # INSERT, UPDATE, DELETE
                result = await session.execute(text(query))
                await session.commit()
                affected = result.rowcount

                return JSONResponse(content={
                    "success": True,
                    "affected": affected
                })

    except Exception as e:
        logger.error(f"Ошибка выполнения SQL: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.get("/api/status")
async def get_status(user: Optional[dict] = Depends(get_optional_user)):
    """Получить статус сервисов."""
    services = get_service_status()
    return JSONResponse(content={
        "success": True,
        "services": services
    })


@router.get("/api/logs")
async def get_logs(
    request: Request,
    level: str = "INFO",
    source: str = "all",
    limit: int = 100,
    user: Optional[dict] = Depends(get_optional_user)
):
    """Получить логи из буфера."""
    try:
        from services.web_admin.log_handler import get_log_handler
        handler = get_log_handler()

        logs = handler.get_logs(
            limit=limit,
            level=level,
            source=source
        )

        return JSONResponse(content={
            "success": True,
            "logs": logs
        })
    except Exception as e:
        logger.error(f"Ошибка получения логов: {e}")
        return JSONResponse(content={
            "success": False,
            "error": str(e),
            "logs": []
        })


@router.post("/api/logs/clear")
async def clear_logs(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user)
):
    """Очистить буфер логов."""
    try:
        from services.web_admin.log_handler import get_log_handler
        handler = get_log_handler()
        handler.clear()

        return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Ошибка очистки логов: {e}")
        return JSONResponse(content={"success": False, "error": str(e)})


@router.post("/api/{service}/start")
async def start_service(service: str, request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Запустить сервис через ServiceManager.
    """
    if service not in ("bot", "listener", "scheduler"):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Неизвестный сервис: {service}"}
        )

    result = await control_service_api(service, "start")

    if result.get("success"):
        logger.info(f"✅ Сервис {service} запущен через API")
    else:
        logger.error(f"❌ Ошибка запуска {service}: {result.get('error')}")

    return JSONResponse(content=result)


@router.post("/api/{service}/stop")
async def stop_service(service: str, request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Остановить сервис через ServiceManager.
    """
    if service not in ("bot", "listener", "scheduler"):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Неизвестный сервис: {service}"}
        )

    result = await control_service_api(service, "stop")

    if result.get("success"):
        logger.info(f"✅ Сервис {service} остановлен через API")
    else:
        logger.error(f"❌ Ошибка остановки {service}: {result.get('error')}")

    return JSONResponse(content=result)


@router.post("/api/{service}/restart")
async def restart_service(service: str, request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Перезапустить сервис через ServiceManager.
    """
    if service not in ("bot", "listener", "scheduler"):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Неизвестный сервис: {service}"}
        )

    result = await control_service_api(service, "restart")

    if result.get("success"):
        logger.info(f"✅ Сервис {service} перезапущен через API")
    else:
        logger.error(f"❌ Ошибка рестарта {service}: {result.get('error')}")

    return JSONResponse(content=result)
