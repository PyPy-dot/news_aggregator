"""
WebSocket endpoint для real-time авторизации ListenerBot.

Поддерживает двустороннюю связь:
- Backend → Frontend: пуш изменений состояния авторизации
- Frontend → Backend: отправка кода, пароля, отмена

Подключается на /ws/listener-auth.
Работает как дополнение к HTTP API (listener_auth.py), не заменяет его.
"""

import asyncio
import json
import logging
from typing import Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# Подключенные WebSocket-клиенты
_active_connections: Set[WebSocket] = set()


async def broadcast_state(state: dict) -> None:
    """
    Расслать обновление состояния всем подключенным WebSocket-клиентам.

    Вызывается из listener_auth.py через event-шину при изменении _auth_state.
    """
    if not _active_connections:
        return

    message = {"type": "state_change", "state": state}

    disconnected = set()
    for ws in _active_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)

    # Чистим отключенных
    _active_connections -= disconnected
    if disconnected:
        logger.debug(f"🧹 Удалено {len(disconnected)} отключенных WebSocket клиентов")


async def send_to_all(message: dict) -> None:
    """Расслать произвольное сообщение всем подключенным клиентам."""
    disconnected = set()
    for ws in _active_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)

    _active_connections -= disconnected


@router.websocket("/listener-auth")
async def listener_auth_websocket(websocket: WebSocket):
    """
    WebSocket endpoint для авторизации ListenerBot.

    Клиент подключается один раз, получает все обновления состояния real-time.

    Сообщения от клиента:
    - {"type": "submit_code", "code": "12345"}
    - {"type": "submit_password", "password": "..."}
    - {"type": "cancel"}

    Сообщения сервера:
    - {"type": "state_change", "state": {...}}
    - {"type": "completed"}
    - {"type": "error", "error": "..."}
    - {"type": "accepted", "message": "..."}  — подтверждение приёма ввода
    """
    from services.web_admin.routes.listener_auth import (
        get_auth_state,
        submit_code,
        submit_password,
        clear_auth_state,
    )

    await websocket.accept()
    _active_connections.add(websocket)

    logger.info(f"🔌 WebSocket подключён (клиентов: {len(_active_connections)})")

    # Отправить текущее состояние при подключении
    try:
        current_state = get_auth_state()
        await websocket.send_json({"type": "state_change", "state": current_state})
    except Exception:
        pass

    try:
        while True:
            # Читать сообщения от клиента
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "submit_code":
                code = data.get("code", "").strip()
                if code and submit_code(code):
                    await websocket.send_json({
                        "type": "accepted",
                        "message": "Код принят, обрабатываю...",
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Сейчас не ожидается ввод кода",
                    })

            elif msg_type == "submit_password":
                password = data.get("password", "")
                if password and submit_password(password):
                    await websocket.send_json({
                        "type": "accepted",
                        "message": "Пароль принят, обрабатываю...",
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Сейчас не ожидается ввод пароля",
                    })

            elif msg_type == "cancel":
                clear_auth_state()
                await websocket.send_json({
                    "type": "state_change",
                    "state": get_auth_state(),
                })
                logger.info("🚫 Авторизация отменена через WebSocket")

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                logger.warning(f"⚠️ Неизвестный тип WS сообщения: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket отключён (клиентов: {len(_active_connections) - 1})")
    except Exception as e:
        logger.error(f"❌ Ошибка WebSocket: {e}", exc_info=True)
    finally:
        _active_connections.discard(websocket)
