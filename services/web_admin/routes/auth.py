"""Auth routes для Web Admin — классическая аутентификация по логину/паролю."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

from services.web_admin.session_manager import get_session_manager, SessionManager
from services.web_admin.config import get_version

router = APIRouter()

# Шаблоны
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Cookie настройки
COOKIE_NAME = "web_admin_session"
COOKIE_MAX_AGE = 60 * 60 * 3  # 3 часа в секундах


def get_session_manager_dep() -> SessionManager:
    """Dependency для получения менеджера сессий."""
    return get_session_manager()


async def get_current_user_from_cookie(request: Request) -> Optional[dict]:
    """
    Получить текущего пользователя из cookie.

    Returns:
        dict с username или None если не авторизован
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


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    current_user: Annotated[Optional[dict], Depends(get_current_user_from_cookie)]
):
    """
    Страница входа.

    Если пользователь уже авторизован — редирект на главную.
    """
    if current_user:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
            "next": request.query_params.get("next", "/"),
            "version": get_version()
        }
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next_url: Annotated[str, Form()] = "/"
):
    """
    Обработка формы входа.

    Args:
        username: Логин пользователя
        password: Пароль
        next_url: Куда перенаправить после входа
    """
    manager = get_session_manager()

    # Проверяем учётные данные
    if not manager.credentials_exist():
        raise HTTPException(
            status_code=503,
            detail="Учётные данные не созданы. Перезапустите сервер для настройки."
        )

    if not manager.verify_password(password):
        # Неверный пароль — показываем страницу входа с ошибкой
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Неверный логин или пароль",
                "next": next_url,
                "username": username,
                "version": get_version()
            }
        )

    # Проверяем логин
    db_username = manager.get_username()
    if db_username != username:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Неверный логин или пароль",
                "next": next_url,
                "username": username,
                "version": get_version()
            }
        )

    # Создаём токен сессии
    token = manager.create_token(username)

    # Перенаправляем на главную или next_url
    redirect_url = next_url if next_url and next_url != "/login" else "/"
    response = RedirectResponse(url=redirect_url, status_code=303)

    # Устанавливаем cookie с токеном
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=False,  # В production установить True
        samesite="lax"
    )

    return response


@router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Выйти из системы.

    Удаляет cookie сессии.
    """
    response.delete_cookie(COOKIE_NAME)

    # Перенаправляем на страницу входа
    return RedirectResponse(url="/auth/login", status_code=303)


@router.get("/logout", response_class=HTMLResponse)
async def logout_get(request: Request):
    """GET версия logout (для ссылок в меню)."""
    # Создаём ответ с удалением cookie
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
