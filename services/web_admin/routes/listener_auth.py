"""
Listener Auth — API для авторизации ListenerBot в Telegram.

Предоставляет:
- API для запроса кода подтверждения
- API для ввода кода подтверждения
- API для ввода облачного пароля
- WebSocket для уведомления об изменениях статуса авторизации
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from services.web_admin.api.app import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Глобальное состояние авторизации
_auth_state: Dict[str, Any] = {
    "step": None,  # None, "code", "password", "completed", "error"
    "phone_number": None,
    "phone_code_hash": None,
    "message": None,
    "error": None,
    "timestamp": None,
}

# События для синхронизации
_code_event = asyncio.Event()
_password_event = asyncio.Event()


def get_auth_state() -> Dict[str, Any]:
    """Получить текущее состояние авторизации."""
    return _auth_state.copy()


def set_auth_step(step: str, message: str = None, error: str = None):
    """Установить шаг авторизации."""
    _auth_state["step"] = step
    _auth_state["message"] = message
    _auth_state["error"] = error
    _auth_state["timestamp"] = datetime.now().isoformat()
    logger.info(f"🔐 Авторизация: шаг={step}, message={message}, error={error}")


def clear_auth_state():
    """Очистить состояние авторизации."""
    global _auth_state
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


async def wait_for_code() -> Optional[str]:
    """
    Ждать ввода кода подтверждения.

    Returns:
        Код подтверждения или None если таймаут
    """
    set_auth_step("code", "Введите код из Telegram")
    _code_event.clear()

    try:
        # Ждем код 5 минут
        await asyncio.wait_for(_code_event.wait(), timeout=300)
        code = _auth_state.get("code")
        return code
    except asyncio.TimeoutError:
        set_auth_step("error", error="Таймаут ввода кода")
        return None


async def wait_for_password() -> Optional[str]:
    """
    Ждать ввода облачного пароля.

    Returns:
        Пароль или None если таймаут
    """
    set_auth_step("password", "Введите облачный пароль Telegram")
    _password_event.clear()

    try:
        # Ждем пароль 5 минут
        await asyncio.wait_for(_password_event.wait(), timeout=300)
        password = _auth_state.get("password")
        return password
    except asyncio.TimeoutError:
        set_auth_step("error", error="Таймаут ввода пароля")
        return None


def submit_code(code: str) -> bool:
    """
    Отправить код подтверждения.

    Args:
        code: Код из Telegram

    Returns:
        True если код принят
    """
    if _auth_state.get("step") != "code":
        return False

    _auth_state["code"] = code
    _code_event.set()
    logger.info("✅ Код подтверждения получен из браузера")
    return True


def submit_password(password: str) -> bool:
    """
    Отправить облачный пароль.

    Args:
        password: Облачный пароль Telegram

    Returns:
        True если пароль принят
    """
    if _auth_state.get("step") != "password":
        return False

    _auth_state["password"] = password
    _password_event.set()
    logger.info("✅ Облачный пароль получен из браузера")
    return True


@router.get("/api/listener/auth/status")
async def get_auth_status(user: Optional[dict] = Depends(get_optional_user)):
    """
    Получить текущий статус авторизации ListenerBot.

    Returns:
        Состояние авторизации
    """
    return JSONResponse(content={
        "success": True,
        "state": get_auth_state()
    })


@router.post("/api/listener/auth/start")
async def start_auth(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Начать процесс авторизации ListenerBot.

    Запускает процесс авторизации в ListenerBot.
    """
    try:
        from services.service_manager import get_service_manager

        manager = get_service_manager()

        # Проверяем, запущен ли listener
        if not manager.is_running("listener"):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "ListenerBot не запущен. Запустите сервис перед авторизацией."
                }
            )

        # Очищаем предыдущее состояние
        clear_auth_state()

        # Получаем listener и запускаем авторизацию
        listener = manager._listener
        if not listener:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "ListenerBot не инициализирован"
                }
            )

        # Проверяем, не авторизован ли уже
        if await listener.client.is_user_authorized():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "ListenerBot уже авторизован"
                }
            )

        # Запускаем авторизацию в фоне
        asyncio.create_task(_run_auth_process(listener))

        return JSONResponse(content={
            "success": True,
            "message": "Процесс авторизации запущен"
        })

    except Exception as e:
        logger.error(f"Ошибка запуска авторизации: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.get("/api/listener/auth/check")
async def check_and_start_auth(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Проверить необходимость авторизации и запустить если требуется.

    Вызывается автоматически при загрузке страницы для проверки состояния.
    """
    try:
        from services.service_manager import get_service_manager

        manager = get_service_manager()

        # Проверяем, запущен ли listener
        if not manager.is_running("listener"):
            return JSONResponse(content={
                "success": True,
                "auth_needed": False,
                "reason": "listener_not_running"
            })

        listener = manager._listener
        if not listener:
            return JSONResponse(content={
                "success": True,
                "auth_needed": False,
                "reason": "listener_not_initialized"
            })

        # Проверяем, подключен ли клиент
        if not listener.client or not listener._client_initialized:
            return JSONResponse(content={
                "success": True,
                "auth_needed": False,
                "reason": "client_not_connected"
            })

        # Проверяем, подключен ли клиент к Telegram
        try:
            if not listener.client.is_connected():
                return JSONResponse(content={
                    "success": True,
                    "auth_needed": False,
                    "reason": "client_disconnected"
                })
        except Exception:
            # Если проверка подключения не удалась, считаем что не подключен
            return JSONResponse(content={
                "success": True,
                "auth_needed": False,
                "reason": "client_connection_error"
            })

        # Проверяем авторизацию
        try:
            if await listener.client.is_user_authorized():
                return JSONResponse(content={
                    "success": True,
                    "auth_needed": False,
                    "reason": "already_authorized"
                })
        except Exception as e:
            # Если проверка авторизации не удалась (например, разрыв соединения)
            logger.warning(f"⚠️ Не удалось проверить авторизацию: {e}")
            return JSONResponse(content={
                "success": True,
                "auth_needed": False,
                "reason": "auth_check_error"
            })

        # Если уже идет процесс авторизации
        current_state = get_auth_state()
        if current_state.get("step") in ("code", "password"):
            return JSONResponse(content={
                "success": True,
                "auth_needed": True,
                "state": current_state,
                "reason": "auth_in_progress"
            })

        # Требуется авторизация - запускаем процесс
        clear_auth_state()
        asyncio.create_task(_run_auth_process(listener))

        return JSONResponse(content={
            "success": True,
            "auth_needed": True,
            "reason": "auth_started"
        })

    except Exception as e:
        logger.error(f"Ошибка проверки авторизации: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


async def _run_auth_process(listener):
    """
    Запустить процесс авторизации в ListenerBot.

    Args:
        listener: Экземпляр ListenerBot
    """
    try:
        from config.settings import settings
        from telethon.errors import SessionPasswordNeededError, AuthKeyUnregisteredError

        clear_auth_state()

        # Получаем телефон из настроек
        phone_number = settings.phone_number
        _auth_state["phone_number"] = phone_number

        logger.info(f"🔐 Начало авторизации для {phone_number}")

        # Проверяем, подключен ли клиент
        if not listener.client or not listener._client_initialized:
            set_auth_step("error", error="Telegram клиент не инициализирован")
            return

        # Проверяем, не авторизован ли уже (с обработкой ошибок)
        try:
            is_authorized = await listener.client.is_user_authorized()
        except AuthKeyUnregisteredError:
            logger.warning("⚠️ Сессия недействительна (AuthKeyUnregisteredError) - требуется новая авторизация")
            is_authorized = False
        except Exception as auth_err:
            error_str = str(auth_err)
            # Проверяем на ошибку SQLite
            if 'no such table' in error_str or 'database disk image is malformed' in error_str:
                logger.warning(f"⚠️ Сессия SQLite повреждена - требуется пересоздание")
                # Удаляем повреждённую сессию
                import os
                session_file = "userbot.session"
                session_journal = "userbot.session-journal"
                for f in [session_file, session_journal]:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                            logger.info(f"🗑️ Удалён файл: {f}")
                        except Exception as remove_err:
                            logger.warning(f"⚠️ Не удалось удалить {f}: {remove_err}")
                # Переподключаем клиента с чистой сессией
                try:
                    await listener.client.disconnect()
                except Exception:
                    pass
                # Создаём новый клиент
                from telethon import TelegramClient
                listener.client = TelegramClient(
                    "userbot",
                    api_id=settings.api_id,
                    api_hash=settings.api_hash,
                )
                await listener.client.connect()
                listener._client_initialized = True
                is_authorized = False
            else:
                logger.warning(f"⚠️ Ошибка проверки авторизации: {auth_err}")
                is_authorized = False

        if is_authorized:
            logger.info("✅ ListenerBot уже авторизован")
            set_auth_step("completed", "Уже авторизован")
            return

        # Запрашиваем код
        logger.info("📱 Отправка запроса кода в Telegram...")
        try:
            sent = await listener.client.send_code_request(phone_number)
            _auth_state["phone_code_hash"] = sent.phone_code_hash
            logger.info("📱 Код отправлен в Telegram")
            set_auth_step("code", f"Код отправлен на {phone_number}")
        except AuthKeyUnregisteredError:
            logger.error("❌ Сессия недействительна! Требуется полная перерегистрация.")
            set_auth_step("error", error="Сессия недействительна. Перезапустите ListenerBot.")
            # Удаляем файл сессии
            import os
            session_file = "userbot.session"
            if os.path.exists(session_file):
                try:
                    os.remove(session_file)
                    logger.info(f"🗑️ Файл сессии {session_file} удалён")
                except Exception as remove_err:
                    logger.error(f"❌ Не удалось удалить сессию: {remove_err}")
            return
        except Exception as send_err:
            error_str = str(send_err)
            if 'no such table' in error_str or 'database disk image is malformed' in error_str:
                logger.error("❌ База данных сессии повреждена!")
                set_auth_step("error", error="Сессия повреждена. Перезапустите ListenerBot.")
                # Удаляем файлы сессии
                import os
                session_file = "userbot.session"
                session_journal = "userbot.session-journal"
                for f in [session_file, session_journal]:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                            logger.info(f"🗑️ Удалён файл: {f}")
                        except Exception as remove_err:
                            logger.warning(f"⚠️ Не удалось удалить {f}: {remove_err}")
            else:
                logger.error(f"❌ Ошибка отправки кода: {send_err}")
                set_auth_step("error", error=str(send_err))
            return

        # Ждем код из браузера или консоли
        code = await wait_for_code()
        if not code:
            return

        try:
            # Пробуем войти с кодом
            await listener.client.sign_in(phone_number, code, phone_code_hash=_auth_state["phone_code_hash"])
            logger.info("✅ Авторизация успешна")
            set_auth_step("completed", "Авторизация успешна")
            clear_auth_state()
            return

        except SessionPasswordNeededError:
            logger.info("🔒 Требуется облачный пароль")
            set_auth_step("password", "Требуется облачный пароль Telegram")

            # Ждем пароль из браузера или консоли
            password = await wait_for_password()
            if not password:
                return

            # Входим с паролем
            await listener.client.sign_in(password=password)
            logger.info("✅ Авторизация с паролем успешна")
            set_auth_step("completed", "Авторизация успешна")
            clear_auth_state()

        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}", exc_info=True)
            set_auth_step("error", error=str(e))

    except Exception as e:
        logger.error(f"Ошибка процесса авторизации: {e}", exc_info=True)
        set_auth_step("error", error=str(e))


@router.post("/api/listener/auth/code")
async def submit_code_endpoint(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Отправить код подтверждения из браузера.
    """
    try:
        data = await request.json()
        code = data.get("code", "").strip()

        if not code:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Код не может быть пустым"}
            )

        if _auth_state.get("step") != "code":
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Сейчас не ожидается ввод кода"}
            )

        if submit_code(code):
            return JSONResponse(content={
                "success": True,
                "message": "Код принят"
            })
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Не удалось отправить код"}
            )

    except Exception as e:
        logger.error(f"Ошибка отправки кода: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.post("/api/listener/auth/password")
async def submit_password_endpoint(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user)
):
    """
    Отправить облачный пароль из браузера.
    """
    try:
        data = await request.json()
        password = data.get("password", "")

        if not password:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Пароль не может быть пустым"}
            )

        if _auth_state.get("step") != "password":
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Сейчас не ожидается ввод пароля"}
            )

        if submit_password(password):
            return JSONResponse(content={
                "success": True,
                "message": "Пароль принят"
            })
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Не удалось отправить пароль"}
            )

    except Exception as e:
        logger.error(f"Ошибка отправки пароля: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.post("/api/listener/auth/cancel")
async def cancel_auth(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    """
    Отменить процесс авторизации.
    """
    clear_auth_state()
    logger.info("🚫 Авторизация отменена пользователем")
    return JSONResponse(content={
        "success": True,
        "message": "Авторизация отменена"
    })
