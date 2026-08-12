"""
Callback-хендлеры для Telegram бота.

Этот файл служит точкой входа для всех callback-запросов.
Фактические обработчики разнесены по модулям:
- callbacks_channels.py — управление каналами (добавление, удаление, доверенные источники)
- callbacks_moderation.py — модерация постов и новостей
- callbacks_preferences.py — предпочтения пользователя и подписка
- callbacks_admin.py — административные функции (очистка БД)
"""

# Импортируем все обработчики из модулей для регистрации в роутере
from services.bot.handlers.callbacks_channels import (
    add_channel,
    delete_channel,
    confirm_delete_channel,
    trusted_channels_menu,
    toggle_trusted_channel,
    make_trusted,
    remove_trusted,
    confirm_make_trusted,
    confirm_remove_trusted,
)

from services.bot.handlers.callbacks_moderation import (
    approve_post_callback,
    reject_post_callback,
    approve_news_callback,
    reject_news_callback,
    edit_news_callback,
)

from services.bot.handlers.callbacks_preferences import (
    back_to_menu,
    back_to_user_menu_callback,
    category_toggle_callback,
    tag_toggle_callback,
    tag_remove_callback,
    subscription_menu_callback,
    subscribe_buy_callback,
    subscribe_extend_callback,
    subscribe_info_callback,
)

from services.bot.handlers.callbacks_admin import (
    cleanup_confirm_callback,
    cleanup_cancel_callback,
)

# Ре-экспорт для совместимости (если кто-то импортирует отсюда)
__all__ = [
    # Channels
    'add_channel',
    'delete_channel',
    'confirm_delete_channel',
    'trusted_channels_menu',
    'toggle_trusted_channel',
    'make_trusted',
    'remove_trusted',
    'confirm_make_trusted',
    'confirm_remove_trusted',
    # Moderation
    'approve_post_callback',
    'reject_post_callback',
    'approve_news_callback',
    'reject_news_callback',
    'edit_news_callback',
    # Preferences
    'back_to_menu',
    'back_to_user_menu_callback',
    'category_toggle_callback',
    'tag_toggle_callback',
    'tag_remove_callback',
    'subscription_menu_callback',
    'subscribe_buy_callback',
    'subscribe_extend_callback',
    'subscribe_info_callback',
    # Admin
    'cleanup_confirm_callback',
    'cleanup_cancel_callback',
]
