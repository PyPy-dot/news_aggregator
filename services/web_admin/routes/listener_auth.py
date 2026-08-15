"""
Listener Auth — единый процесс авторизации ListenerBot в Telegram.

Поддерживает два канала ввода параллельно:
- Веб-интерфейс (WebSocket + HTTP API polling)
- Консоль (stdin ввод)

Авторизация управляется через глобальное состояние (_auth_state)
и asyncio.Event для синхронизации между каналами.

API:
- GET  /api/listener/auth/status   — текущий статус
- POST /api/listener/auth/start    — начать процесс
- GET  /api/listener/auth/check    — авточек при загрузке страницы
- POST /api/listener/auth/code     — отправить код из веба
- POST /api/listener/auth/password — отправить пароль из веба
- POST /api/listener/auth/cancel   — отменить
- WS   /ws/listener-auth           — real-time авторизация
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Callable, Optional, Dict, Any, List

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from services.web_admin.api.app import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Глобальное состояние авторизации
# ---------------------------------------------------------------------------

_auth_state: Dict[str, Any] = {
    "step": None,           # None | "code" | "password" | "completed" | "error"
    "phone_number": None,
    "phone_code_hash": None,
    "message": None,
    "error": None,
    "timestamp": None,
}

# События для синхронизации между веб-API и процессом авторизации
_code_event = asyncio.Event()
_password_event = asyncio.Event()

# Флаг: процесс авторизации сейчас активен
_auth_running = False

# Event-шина для уведомлений о изменении состояния (WebSocket, и др.)
_state_change_listeners: List[Callable] = []


def on_state_change(callback: Callable) -> None:
    """
    Зарегистрировать callback на изменение состояния авторизации.

    Callback вызывается синхронно с dict-копией нового состояния.
    Используется WebSocket-менеджером для real-time push.
    """
    if callback not in _state_change_listeners:
        _state_change_listeners.append(callback)


# ---------------------------------------------------------------------------
# Публичный API для управления состоянием
# ---------------------------------------------------------------------------

def get_auth_state() -> Dict[str, Any]:
    """Вернуть копию текущего состояния."""
    return _auth_state.copy()


def set_auth_step(step: str, message: str = None, error: str = None):
    """Установить шаг авторизации и уведомить подписчиков."""
    _auth_state["step"] = step
    _auth_state["message"] = message
    _auth_state["error"] = error
    _auth_state["timestamp"] = datetime.now().isoformat()
    logger.info(f"🔐 Auth step -> {step} | msg={message} | err={error}")

    # Уведомить всех слушателей (WebSocket, и др.)
    state_copy = _auth_state.copy()
    for cb in _state_change_listeners:
        try:
            cb(state_copy)
        except Exception as e:
            logger.debug(f"⚠️ Ошибка callback состояния: {e}")


def clear_auth_state():
    """Сбросить состояние и события."""
    global _auth_state, _auth_running
    _auth_state = {
        "step": None,
        "phone_number": None,
        "phone_code_hash": None,
        "message": None,
        "error": None,
        "timestamp": None,
    }
    _code_event.clear()
    _password_event.clear()
    _auth_running = False


# ---------------------------------------------------------------------------
# Ожидание ввода (код / пароль) — параллельно из веба и консоли
# ---------------------------------------------------------------------------

async def wait_for_code(console_task_factory=None) -> Optional[str]:
    """
    Ждать код подтверждения.

    Параллельно слушает:
    - Веб-API (через submit_code() / WebSocket)
    - Консольный ввод (через asyncio gather)

    Returns код или None если таймаут.
    """
    set_auth_step("code", "Введите код из Telegram (консоль или веб-админка)")
    _code_event.clear()

    # Задача ожидания из веба
    async def wait_web():
        try:
            await asyncio.wait_for(_code_event.wait(), timeout=300)
            return _auth_state.get("code")
        except asyncio.TimeoutError:
            return None

    # Задача ожидания из консоли (только если stdin доступен)
    async def wait_console():
        try:
            logger.info("⌨️  Ожидание кода из консоли (таймаут 5 мин)...")
            loop = asyncio.get_event_loop()

            def read_input():
                print('\n🔐 Код из Telegram: ', end='', flush=True)
                try:
                    return sys.stdin.readline().strip()
                except Exception:
                    return None

            code = await asyncio.wait_for(
                loop.run_in_executor(None, read_input),
                timeout=300
            )
            if code:
                logger.info("✅ Код получен из консоли")
                return code
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"Ошибка ожидания кода из консоли: {e}")
        return None

    # Задаём список задач
    web_task = asyncio.create_task(wait_web())

    # Добавляем консоль только если stdin доступен
    if _is_stdin_available():
        console_task = asyncio.create_task(wait_console())
        tasks = [web_task, console_task]
    else:
        logger.info("⌨️ Консольный ввод недоступен (stdin), ожидаем через веб")
        tasks = [web_task]

    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Отменяем проигравшую задачу
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    # Извлекаем результат победителя
    for t in done:
        try:
            code = await t
            if code:
                return code
        except Exception:
            pass

    set_auth_step("error", error="Таймаут ввода кода (5 минут)")
    return None


async def wait_for_password() -> Optional[str]:
    """
    Ждать облачный пароль. Параллельно из веба и консоли.
    """
    set_auth_step("password", "Введите облачный пароль Telegram")
    _password_event.clear()

    async def wait_web():
        try:
            await asyncio.wait_for(_password_event.wait(), timeout=300)
            return _auth_state.get("password")
        except asyncio.TimeoutError:
            return None

    async def wait_console():
        try:
            logger.info("⌨️  Ожидание облачного пароля из консоли (таймаут 5 мин)...")
            loop = asyncio.get_event_loop()

            def read_input():
                print('\n🔒 Облачный пароль Telegram: ', end='', flush=True)
                try:
                    return sys.stdin.readline().strip()
                except Exception:
                    return None

            pw = await asyncio.wait_for(
                loop.run_in_executor(None, read_input),
                timeout=300
            )
            if pw:
                logger.info("✅ Облачный пароль получен из консоли")
                return pw
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"Ошибка ожидания пароля из консоли: {e}")
        return None

    web_task = asyncio.create_task(wait_web())

    if _is_stdin_available():
        console_task = asyncio.create_task(wait_console())
        tasks = [web_task, console_task]
    else:
        logger.info("⌨️ Консольный ввод недоступен (stdin), ожидаем пароль через веб")
        tasks = [web_task]

    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED,
    )

    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    for t in done:
        try:
            pw = await t
            if pw:
                return pw
        except Exception:
            pass

    set_auth_step("error", error="Таймаут ввода пароля (5 минут)")
    return None


# ---------------------------------------------------------------------------
# Submission из веб-API
# ---------------------------------------------------------------------------

def submit_code(code: str) -> bool:
    """Принять код из веб-интерфейса."""
    if _auth_state.get("step") != "code":
        return False
    _auth_state["code"] = code
    _code_event.set()
    logger.info("✅ Код получен из веб-интерфейса")
    return True


def submit_password(password: str) -> bool:
    """Принять пароль из веб-интерфейса."""
    if _auth_state.get("step") != "password":
        return False
    _auth_state["password"] = password
    _password_event.set()
    logger.info("✅ Облачный пароль получен из веб-интерфейса")
    return True


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def _is_stdin_available() -> bool:
    """Проверить, доступен ли stdin для интерактивного ввода."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Пересоздание сессии
# ---------------------------------------------------------------------------

async def remove_session_file(session_name: str = "userbot") -> bool:
    """
    Удалить файлы сессии Telegram.

    Returns True если хотя бы один файл был удалён.
    """
    removed = False
    for suffix in [".session", ".session-journal"]:
        f = f"{session_name}{suffix}"
        if os.path.exists(f):
            try:
                os.remove(f)
                logger.info(f"🗑️ Удалён: {f}")
                removed = True
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить {f}: {e}")
    return removed


async def recreate_client(listener, session_name: str = "userbot") -> bool:
    """
    Пересоздать Telethon клиент с чистой сессией.

    1. Отключить старый клиент
    2. Удалить файлы сессии
    3. Создать новый клиент и подключиться

    Returns True если успешно.
    """
    from config.settings import settings
    from telethon import TelegramClient

    # Используем сохранённый путь сессии из listener.bot (может быть перенаправлен в локальную папку)
    session_file = getattr(listener, '_session_file', None) or session_name

    try:
        if listener.client:
            await listener.client.disconnect()
    except Exception:
        pass

    # Удаляем старые файлы
    await remove_session_file(session_file)

    # Пересоздаём
    try:
        listener.client = TelegramClient(
            session_file,
            api_id=settings.api_id,
            api_hash=settings.api_hash,
            connection_retries=3,
            retry_delay=1,
            timeout=30,
            use_ipv6=True,
            flood_sleep_threshold=60,
            auto_reconnect=True,
        )
        try:
            await listener.client.connect()
        except Exception:
            # IPv6 не работает — без него
            try:
                await listener.client.disconnect()
            except Exception:
                pass
            listener.client = TelegramClient(
                session_file,
                api_id=settings.api_id,
                api_hash=settings.api_hash,
                connection_retries=3,
                retry_delay=1,
                timeout=30,
                use_ipv6=False,
                flood_sleep_threshold=60,
                auto_reconnect=True,
            )
            await listener.client.connect()
        listener._client_initialized = True
        logger.info("✅ Клиент пересоздан с чистой сессией")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось пересоздать клиент: {e}")
        return False


# ---------------------------------------------------------------------------
# Основной процесс авторизации (вызывается из bot.py или через API)
# ---------------------------------------------------------------------------

async def run_auth_process(listener) -> bool:
    """
    Выполнить процесс авторизации ListenerBot.

    Это — единственная точка запуска авторизации.
    Вызывается из bot.py::initialize() когда is_user_authorized() == False,
    или через POST /api/listener/auth/start.

    Args:
        listener: экземпляр ListenerBot

    Returns:
        True если авторизация прошла успешно
    """
    global _auth_running

    if _auth_running:
        logger.warning("⚠️ Процесс авторизации уже запущен")
        return False

    from config.settings import settings

    try:
        from telethon.errors import SessionPasswordNeededError, AuthKeyUnregisteredError, FloodWaitError
    except ImportError:
        logger.error("❌ Telethon не установлен")
        set_auth_step("error", error="Telethon не установлен")
        return False

    _auth_running = True
    clear_auth_state()
    # clear_auth_state сбрасывает _auth_running, восстановим
    _auth_running = True

    phone_number = settings.phone_number
    _auth_state["phone_number"] = phone_number

    logger.info(f"🔐 Начало авторизации для {phone_number}")

    # Проверяем клиента
    if not listener.client or not listener._client_initialized:
        set_auth_step("error", error="Telegram клиент не инициализирован")
        _auth_running = False
        return False

    # Проверяем, не авторизован ли уже
    try:
        is_authorized = await listener.client.is_user_authorized()
    except AuthKeyUnregisteredError:
        logger.warning("⚠️ AuthKeyUnregisteredError — ключ сессии удалён на сервере Telegram")
        logger.info("🔄 Пересоздание клиента с чистой сессией...")
        ok = await recreate_client(listener)
        if not ok:
            set_auth_step("error", error="Не удалось пересоздать Telegram клиент")
            _auth_running = False
            return False
        is_authorized = False
    except Exception as auth_err:
        error_str = str(auth_err)
        if 'no such table' in error_str or 'database disk image is malformed' in error_str:
            logger.warning("⚠️ Сессия SQLite повреждена — пересоздание")
            ok = await recreate_client(listener)
            if not ok:
                set_auth_step("error", error="Не удалось пересоздать Telegram клиент")
                _auth_running = False
                return False
            is_authorized = False
        else:
            logger.warning(f"⚠️ Ошибка проверки авторизации: {auth_err}")
            is_authorized = False

    if is_authorized:
        logger.info("✅ ListenerBot уже авторизован")
        set_auth_step("completed", "Уже авторизован")
        _auth_running = False
        return True

    # --- Шаг 1: отправляем код ---
    try:
        sent = await listener.client.send_code_request(phone_number)
        _auth_state["phone_code_hash"] = sent.phone_code_hash
        logger.info(f"📱 Код отправлен в Telegram (hash: {sent.phone_code_hash[:12]}...)")

        # Проверяем тип доставки кода
        if hasattr(sent, 'type') and sent.type:
            from telethon.tl.types import auth as auth_types
            code_type = sent.type
            if isinstance(code_type, auth_types.SentCodeTypeApp):
                logger.info("📱 Код будет отправлен В ПРИЛОЖЕНИЕ Telegram")
            elif isinstance(code_type, auth_types.SentCodeTypeSms):
                logger.info("📱 Код будет отправлен через SMS")
            else:
                logger.info(f"📱 Тип доставки: {type(code_type).__name__}")

        if hasattr(sent, 'next_type') and sent.next_type:
            logger.info(f"   Следующий тип при повторном запросе: {type(sent.next_type).__name__}")
    except FloodWaitError as e:
        seconds = e.seconds
        minutes = seconds / 60
        hours = minutes / 60
        if hours >= 1:
            wait_msg = f"{hours:.1f} ч. ({int(minutes)} мин.)"
        elif minutes >= 1:
            wait_msg = f"{minutes:.1f} мин. ({seconds} сек.)"
        else:
            wait_msg = f"{seconds} сек."
        logger.warning(
            f"⏳ FloodWait от Telegram: {wait_msg}\n"
            f"   Причина: слишком много запросов кода.\n"
            f"   Решение: подождите {wait_msg} и попробуйте снова"
        )
        set_auth_step("error", error=f"FloodWait: подождите {wait_msg}")
        _auth_running = False
        return False
    except AuthKeyUnregisteredError:
        logger.error("❌ Сессия недействительна (AuthKeyUnregisteredError)")
        logger.info("🔄 Попытка пересоздания сессии...")
        ok = await recreate_client(listener)
        if ok:
            try:
                sent = await listener.client.send_code_request(phone_number)
                _auth_state["phone_code_hash"] = sent.phone_code_hash
                logger.info("📱 Код отправлен в Telegram (после пересоздания сессии)")
            except Exception as retry_err:
                logger.error(f"❌ Не удалось отправить код после пересоздания: {retry_err}")
                set_auth_step("error", error=str(retry_err))
                _auth_running = False
                return False
        else:
            set_auth_step("error", error="Сессия недействительна. Не удалось пересоздать клиент.")
            _auth_running = False
            return False
    except Exception as send_err:
        error_str = str(send_err)
        if 'no such table' in error_str or 'database disk image is malformed' in error_str:
            logger.error("❌ База данных сессии повреждена!")
            set_auth_step("error", error="Сессия повреждена. Попытка восстановления...")
            ok = await recreate_client(listener)
            if ok:
                try:
                    sent = await listener.client.send_code_request(phone_number)
                    _auth_state["phone_code_hash"] = sent.phone_code_hash
                    logger.info("📱 Код отправлен (после восстановления сессии)")
                except Exception as retry_err:
                    logger.error(f"❌ Ошибка повторной отправки: {retry_err}")
                    set_auth_step("error", error=str(retry_err))
                    _auth_running = False
                    return False
            else:
                set_auth_step("error", error="Сессия повреждена. Не удалось восстановить.")
                _auth_running = False
                return False

    # Ждём код (параллельно консоль + веб)
    code = await wait_for_code()
    if not code:
        _auth_running = False
        return False

    # --- Шаг 2: sign_in с кодом ---
    try:
        await listener.client.sign_in(
            phone_number,
            code,
            phone_code_hash=_auth_state["phone_code_hash"]
        )
        logger.info("✅ Авторизация успешна!")
        set_auth_step("completed", "Авторизация успешна")
        _auth_running = False
        clear_auth_state()
        return True

    except SessionPasswordNeededError:
        logger.info("🔒 Требуется облачный пароль")

        # Ждём пароль (параллельно консоль + веб)
        password = await wait_for_password()
        if not password:
            _auth_running = False
            return False

        try:
            await listener.client.sign_in(password=password)
            logger.info("✅ Авторизация с паролем успешна!")
            set_auth_step("completed", "Авторизация успешна")
            _auth_running = False
            clear_auth_state()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка ввода пароля: {e}")
            set_auth_step("error", error=str(e))
            _auth_running = False
            return False

    except Exception as e:
        logger.error(f"❌ Ошибка авторизации: {e}", exc_info=True)
        set_auth_step("error", error=str(e))
        _auth_running = False
        return False

    finally:
        _auth_running = False


async def _remove_session_file():
    """Legacy wrapper — перенаправляет на публичную функцию."""
    await remove_session_file()


async def _recreate_client(listener):
    """Legacy wrapper — перенаправляет на публичную функцию."""
    await recreate_client(listener)


# ---------------------------------------------------------------------------
# FastAPI эндпоинты
# ---------------------------------------------------------------------------

@router.get("/api/listener/auth/status")
async def get_auth_status(
    user: Optional[dict] = Depends(get_optional_user),
):
    """Текущий статус авторизации."""
    return JSONResponse(content={"success": True, "state": get_auth_state()})


@router.post("/api/listener/auth/start")
async def start_auth(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Начать процесс авторизации через веб-интерфейс."""
    try:
        from services.service_manager import get_service_manager

        manager = get_service_manager()

        if not manager.is_running("listener"):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "ListenerBot не запущен. Запустите сервис перед авторизацией.",
                },
            )

        listener = manager._listener
        if not listener:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "ListenerBot не инициализирован"},
            )

        # Проверяем, не авторизован ли уже
        try:
            if await listener.client.is_user_authorized():
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Уже авторизован"},
                )
        except Exception:
            pass

        # Запускаем процесс в фоне
        asyncio.create_task(run_auth_process(listener))

        return JSONResponse(
            content={"success": True, "message": "Процесс авторизации запущен"}
        )

    except Exception as e:
        logger.error(f"Ошибка запуска авторизации: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )


@router.get("/api/listener/auth/check")
async def check_and_start_auth(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Проверить необходимость авторизации и запустить при необходимости.

    Вызывается при загрузке страницы. Если listener запущен, подключён,
    но не авторизован — запускает процесс и сообщает фронтенду.
    """
    try:
        from services.service_manager import get_service_manager

        manager = get_service_manager()

        if not manager.is_running("listener"):
            return JSONResponse(content={
                "success": True, "auth_needed": False,
                "reason": "listener_not_running",
            })

        listener = manager._listener
        if not listener:
            return JSONResponse(content={
                "success": True, "auth_needed": False,
                "reason": "listener_not_initialized",
            })

        if not listener.client or not listener._client_initialized:
            return JSONResponse(content={
                "success": True, "auth_needed": False,
                "reason": "client_not_connected",
            })

        try:
            if not listener.client.is_connected():
                return JSONResponse(content={
                    "success": True, "auth_needed": False,
                    "reason": "client_disconnected",
                })
        except Exception:
            return JSONResponse(content={
                "success": True, "auth_needed": False,
                "reason": "client_connection_error",
            })

        # Проверка авторизации
        try:
            if await listener.client.is_user_authorized():
                return JSONResponse(content={
                    "success": True, "auth_needed": False,
                    "reason": "already_authorized",
                })
        except Exception as e:
            logger.warning(f"⚠️ Не удалось проверить авторизацию: {e}")
            return JSONResponse(content={
                "success": True, "auth_needed": False,
                "reason": "auth_check_error",
            })

        # Авторизация нужна — проверяем, не запущен ли уже процесс
        current_state = get_auth_state()
        if current_state.get("step") in ("code", "password"):
            return JSONResponse(content={
                "success": True,
                "auth_needed": True,
                "state": current_state,
                "reason": "auth_in_progress",
            })

        # Запускаем процесс
        asyncio.create_task(run_auth_process(listener))

        return JSONResponse(content={
            "success": True,
            "auth_needed": True,
            "reason": "auth_started",
        })

    except Exception as e:
        logger.error(f"Ошибка проверки авторизации: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )


@router.post("/api/listener/auth/code")
async def submit_code_endpoint(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Отправить код подтверждения из браузера."""
    try:
        data = await request.json()
        code = data.get("code", "").strip()

        if not code:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Код не может быть пустым"},
            )

        if submit_code(code):
            return JSONResponse(content={"success": True, "message": "Код принят"})
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Сейчас не ожидается ввод кода",
                },
            )

    except Exception as e:
        logger.error(f"Ошибка отправки кода: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )


@router.post("/api/listener/auth/password")
async def submit_password_endpoint(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Отправить облачный пароль из браузера."""
    try:
        data = await request.json()
        password = data.get("password", "")

        if not password:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Пароль не может быть пустым"},
            )

        if submit_password(password):
            return JSONResponse(content={"success": True, "message": "Пароль принят"})
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Сейчас не ожидается ввод пароля",
                },
            )

    except Exception as e:
        logger.error(f"Ошибка отправки пароля: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )


@router.post("/api/listener/auth/cancel")
async def cancel_auth(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Отменить процесс авторизации."""
    clear_auth_state()
    logger.info("🚫 Авторизация отменена")
    return JSONResponse(content={"success": True, "message": "Авторизация отменена"})
