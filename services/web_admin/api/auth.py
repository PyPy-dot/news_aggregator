"""
Web Admin Authentication — JWT авторизация + 2FA.

Использует:
- python-jose для JWT
- TOTP для 2FA
- Cookies для сессий
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from database.repositories.users import UserRepository
from services.database import get_database_service
from services.auth.two_factor_auth import get_2fa_service

logger = logging.getLogger(__name__)

# =============================================================================
# Конфигурация
# =============================================================================

# Секретный ключ для JWT (в production использовать из env!)
JWT_SECRET = "your-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 24 часа

# Cookie настройки
COOKIE_NAME = "admin_session"
COOKIE_SECURE = False  # В production установить True


# =============================================================================
# Модели
# =============================================================================

class TokenData(BaseModel):
    """Данные токена."""
    user_id: int
    telegram_id: int
    username: str
    is_admin: bool


class LoginRequest(BaseModel):
    """Запрос на вход."""
    telegram_id: int
    totp_code: Optional[str] = None
    backup_code: Optional[str] = None
    remember_me: bool = False


# =============================================================================
# JWT утилиты
# =============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Создать JWT токен.

    Args:
        data: Данные для токена
        expires_delta: Время жизни токена

    Returns:
        JWT токен
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Расшифровать JWT токен.

    Args:
        token: JWT токен

    Returns:
        TokenData или None
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: int = payload.get("user_id")
        telegram_id: int = payload.get("telegram_id")
        username: str = payload.get("username")
        is_admin: bool = payload.get("is_admin", False)

        if user_id is None or telegram_id is None:
            return None

        return TokenData(
            user_id=user_id,
            telegram_id=telegram_id,
            username=username,
            is_admin=is_admin
        )

    except JWTError:
        return None


# =============================================================================
# Авторизация
# =============================================================================

security = HTTPBearer(auto_error=False)


async def get_current_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Получить текущего авторизованного администратора.

    Проверяет:
    1. JWT токен из Authorization header
    2. JWT токен из cookies
    3. Пользователь должен быть админом

    Args:
        request: FastAPI request
        credentials: JWT токен из header

    Returns:
        dict: Информация о пользователе

    Raises:
        HTTPException: Если не авторизован или не админ
    """
    token = None

    # Пробуем получить токен из header
    if credentials:
        token = credentials.credentials

    # Если нет, пробуем из cookies
    if not token:
        token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходимо авторизоваться",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Расшифровываем токен
    user_data = decode_access_token(token)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Проверяем, админ ли
    if not user_data.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуется права администратора"
        )

    # Проверяем, существует ли пользователь в БД
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_data.telegram_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден"
            )

        return {
            "id": user.id,
            "telegram_id": user_data.telegram_id,
            "username": user_data.username,
            "is_admin": True,
            "has_2fa": user.totp_enabled,
        }


async def authenticate_user(
    telegram_id: int,
    totp_code: Optional[str] = None,
    backup_code: Optional[str] = None
) -> Optional[dict]:
    """
    Аутентифицировать пользователя.

    Args:
        telegram_id: Telegram ID пользователя
        totp_code: TOTP код из аутентификатора
        backup_code: Резервный код (если 2FA)

    Returns:
        dict: Информация о пользователе или None
    """
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)

        # Получаем пользователя
        user = await user_repo.get_by_telegram_id(telegram_id)

        if not user:
            logger.warning(f"Пользователь не найден: {telegram_id}")
            return None

        # Проверяем, админ ли
        if user.role != 'admin':
            logger.warning(f"Пользователь не админ: {telegram_id}")
            return None

        # Проверяем 2FA
        if user.totp_enabled:
            if not totp_code and not backup_code:
                logger.warning(f"Требуется 2FA для пользователя: {telegram_id}")
                return None

            totp_service = get_2fa_service()

            # Проверяем TOTP код
            if totp_code:
                if not user.totp_secret:
                    logger.error(f"2FA включена, но секрет не установлен: {telegram_id}")
                    return None

                if not totp_service.verify_code(user.totp_secret, totp_code):
                    logger.warning(f"Неверный TOTP код для пользователя: {telegram_id}")
                    return None

            # Проверяем резервный код
            elif backup_code:
                if not user.totp_backup_codes:
                    logger.error(f"Резервные коды не установлены: {telegram_id}")
                    return None

                is_valid, new_codes_json = totp_service.verify_backup_code(
                    user.totp_backup_codes,
                    backup_code
                )

                if not is_valid:
                    logger.warning(f"Неверный резервный код: {telegram_id}")
                    return None

                # Сохраняем обновлённые коды
                await user_repo.set_backup_codes(telegram_id, new_codes_json)

        # Успешная аутентификация
        return {
            "id": user.id,
            "telegram_id": telegram_id,
            "username": f"admin_{telegram_id}",
            "is_admin": True,
            "has_2fa": user.totp_enabled,
        }
