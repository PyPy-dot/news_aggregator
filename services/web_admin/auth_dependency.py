"""
Web Admin — Проверка авторизации (cookie/JWT).

Вынесено в отдельный модуль чтобы разорвать циклический импорт
между app.py и роутами (которые импортируют get_optional_user).
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.web_admin.session_manager import get_session_manager

# Cookie название
COOKIE_NAME = "web_admin_session"


async def get_optional_user(request: Request) -> Optional[dict]:
    """
    Получить пользователя если авторизован, иначе None.

    Для страниц, которые должны работать без обязательной авторизации.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    manager = get_session_manager()
    payload = manager.verify_token(token)

    if not payload:
        return None

    return {
        "username": payload.get("sub"),
        "logged_in": True
    }


async def get_required_user(request: Request) -> dict:
    """
    Получить текущего пользователя.

    Для защищённых страниц, требующих авторизации.
    """
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"}
        )
    return user
