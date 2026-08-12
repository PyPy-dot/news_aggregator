"""
Auth module — аутентификация и авторизация.

Модуль содержит компоненты для:
- 2FA аутентификации (TOTP)
- Управления сессиями
- Проверки прав доступа
"""

from services.auth.two_factor_auth import (
    TwoFactorAuthService,
    get_2fa_service,
)

__all__ = [
    "TwoFactorAuthService",
    "get_2fa_service",
]
