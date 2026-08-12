"""Auth routes для Web Admin."""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import RedirectResponse

from services.web_admin.api.auth import (
    authenticate_user,
    create_access_token,
    COOKIE_NAME,
    LoginRequest,
)

router = APIRouter()


@router.post("/login")
async def login(login_data: LoginRequest):
    """
    Войти в систему.

    Args:
        login_data: Данные для входа (telegram_id, totp_code/backup_code)

    Returns:
        dict: {access_token, token_type}
    """
    user = await authenticate_user(
        telegram_id=login_data.telegram_id,
        totp_code=login_data.totp_code,
        backup_code=login_data.backup_code,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учётные данные или 2FA код"
        )

    # Создаём JWT токен
    access_token = create_access_token(
        data={
            "user_id": user["id"],
            "telegram_id": user["telegram_id"],
            "username": user["username"],
            "is_admin": user["is_admin"],
        }
    )

    response = RedirectResponse(url="/dashboard")
    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        max_age=60 * 60 * 24,  # 24 часа
        httponly=True,
        secure=False,  # В production установить True
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout():
    """Выйти из системы."""
    response = RedirectResponse(url="/auth/login")
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Вышли из системы"}


@router.get("/login", response_class=RedirectResponse)
async def login_page():
    """Страница входа (redirect)."""
    return RedirectResponse(url="/")
