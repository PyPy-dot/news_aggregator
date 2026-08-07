"""
Tests for NotificationService.
"""

import pytest
import logging
from unittest.mock import AsyncMock, patch, MagicMock

from services.telegram.notification import NotificationService, set_global_bot, get_global_bot

# Настраиваем логирование для тестов
logging.basicConfig(level=logging.INFO)


class TestNotificationService:
    """Тесты для NotificationService."""

    def test_init(self):
        """Тест инициализации сервиса."""
        service = NotificationService()
        # Сервис не хранит admin_chat_id — получает админов из БД
        assert service.bot is None

    @pytest.mark.asyncio
    async def test_notify_urgent_news_no_admins(self, caplog):
        """Тест уведомления о срочной новости без админов."""
        caplog.set_level(logging.WARNING)
        service = NotificationService()

        # Мок для _get_admin_ids — возвращаем пустой список
        with patch.object(service, '_get_admin_ids', return_value=[]):
            await service.notify_urgent_news(
                post_id=42,
                text="Breaking News",
                category="Политика",
                urgency=5,
                channel_title="Test Channel"
            )

        # Проверяем логирование
        assert "Нет админов" in caplog.text

    @pytest.mark.asyncio
    async def test_notify_urgent_news_with_admins(self, caplog):
        """Тест уведомления о срочной новости с админами."""
        caplog.set_level(logging.INFO)
        service = NotificationService()

        # Мок для бота
        mock_bot = AsyncMock()
        set_global_bot(mock_bot)

        # Мок для _get_admin_ids
        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_urgent_news(
                post_id=42,
                text="Breaking News",
                category="Политика",
                urgency=5,
                channel_title="Test Channel"
            )

        # Проверяем вызов бота
        mock_bot.send_message.assert_called_once()
        assert "СРОЧНАЯ" in mock_bot.send_message.call_args[0][1]

        # Очищаем глобальный бот
        set_global_bot(None)

    @pytest.mark.asyncio
    async def test_notify_pending_news_no_admins(self, caplog):
        """Тест уведомления о плановой новости без админов."""
        caplog.set_level(logging.WARNING)
        service = NotificationService()

        with patch.object(service, '_get_admin_ids', return_value=[]):
            await service.notify_pending_news(
                post_id=100,
                text="Regular News",
                category="Экономика",
                channel_title="Test Channel"
            )

        assert "Нет админов" in caplog.text

    @pytest.mark.asyncio
    async def test_notify_pending_news_with_admins(self, caplog):
        """Тест уведомления о плановой новости с админами."""
        caplog.set_level(logging.INFO)
        service = NotificationService()

        mock_bot = AsyncMock()
        set_global_bot(mock_bot)

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_pending_news(
                post_id=100,
                text="Regular News",
                category="Экономика",
                channel_title="Test Channel"
            )

        mock_bot.send_message.assert_called_once()
        assert "модерации" in mock_bot.send_message.call_args[0][1]

        set_global_bot(None)

    @pytest.mark.asyncio
    async def test_notify_direct_publish(self, caplog):
        """Тест уведомления о прямой публикации."""
        caplog.set_level(logging.INFO)
        service = NotificationService()

        mock_bot = AsyncMock()
        set_global_bot(mock_bot)

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_direct_publish(
                post_id=55,
                channel_title="Trusted Channel",
                category="Важное",
                text="Direct publish text"
            )

        mock_bot.send_message.assert_called_once()
        assert "ОПУБЛИКОВАНО НАПРЯМУЮ" in mock_bot.send_message.call_args[0][1]

        set_global_bot(None)

    @pytest.mark.asyncio
    async def test_notify_no_bot(self, caplog):
        """Тест уведомления без инициализированного бота."""
        caplog.set_level(logging.WARNING)
        service = NotificationService()

        # Бот не установлен
        assert get_global_bot() is None

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_urgent_news(
                post_id=42,
                text="Test",
                category="Тест",
                urgency=5,
                channel_title="Test"
            )

        assert "Бот не инициализирован" in caplog.text


class TestGlobalBotFunctions:
    """Тесты для функций установки/получения глобального бота."""

    def test_set_and_get_bot(self):
        """Тест установки и получения бота."""
        mock_bot = MagicMock()

        set_global_bot(mock_bot)
        assert get_global_bot() is mock_bot

        set_global_bot(None)
        assert get_global_bot() is None
