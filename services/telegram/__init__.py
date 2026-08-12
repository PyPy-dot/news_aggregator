"""
Telegram services package.

Модули для работы с Telegram:
- connection: Подключение к Telegram
- listener: Мониторинг каналов
- notification: Уведомления

Примечание: CategorizationService удалён — используйте services/categorization/ напрямую.
"""

from services.telegram.notification import NotificationService

__all__ = [
    'NotificationService',
]
