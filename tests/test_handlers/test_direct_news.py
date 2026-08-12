"""
Тесты для прямой генерации новостей (direct news handler).

Проверка:
- Обычный пользователь не может генерировать новости
- Администратор может генерировать новости
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import Message, User
from aiogram.fsm.context import FSMContext

# Устанавливаем тестовый ключ шифрования ДО импорта модулей
os.environ['ENCRYPTION_KEY'] = 'test_encryption_key_for_testing_purposes_only_32chars'

from services.bot.handlers.states import DirectNewsStates


@pytest.fixture
def mock_admin_message() -> Message:
    """Создать мок сообщения от администратора."""
    message = MagicMock(spec=Message)
    message.from_user = User(
        id=999888777,
        is_bot=False,
        first_name='Test',
        username='admin'
    )
    message.answer = AsyncMock()
    message.text = ''
    message.photo = None
    message.video = None
    message.caption = None
    return message


@pytest.fixture
def mock_user_message() -> Message:
    """Создать мок сообщения от обычного пользователя."""
    message = MagicMock(spec=Message)
    message.from_user = User(
        id=111222333,
        is_bot=False,
        first_name='Test',
        username='user'
    )
    message.answer = AsyncMock()
    message.text = ''
    message.photo = None
    message.video = None
    message.caption = None
    return message


@pytest.fixture
def mock_state() -> FSMContext:
    """Создать мок состояния FSM."""
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_state = AsyncMock()
    state.get_data = AsyncMock()
    return state


class TestDirectNewsAccess:
    """Тесты доступа к прямой генерации новостей (с моками БД)."""

    @pytest.mark.asyncio
    async def test_admin_can_start_direct_news(
        self,
        mock_admin_message: Message,
        mock_state: FSMContext,
    ):
        """Администратор может начать прямую генерацию новости."""
        # Мокаем проверку прав — админ
        with patch('services.bot.handlers.direct_news.check_admin_access', return_value=True):
            from services.bot.handlers.direct_news import start_direct_news
            await start_direct_news(mock_admin_message, mock_state)

        # Проверяем, что состояние установлено
        mock_state.set_state.assert_called_once_with(DirectNewsStates.waiting_for_description)

        # Проверяем, что админу показано сообщение с инструкцией
        mock_admin_message.answer.assert_called_once()
        call_args = mock_admin_message.answer.call_args
        assert '✍️ **Прямая генерация новости — Этап 1**' in call_args[0][0]
        assert 'Введите описание новости' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_user_cannot_start_direct_news(
        self,
        mock_user_message: Message,
        mock_state: FSMContext,
    ):
        """Обычный пользователь не может начать прямую генерацию новости."""
        # Мокаем проверку прав — не админ
        # check_admin_access сам вызывает answer(), поэтому патчим его полностью
        async def mock_check(msg):
            await msg.answer('❌ У вас нет прав для генерации новостей', show_alert=True)
            return False

        with patch('services.bot.handlers.direct_news.check_admin_access', side_effect=mock_check):
            from services.bot.handlers.direct_news import start_direct_news
            await start_direct_news(mock_user_message, mock_state)

        # Проверяем, что состояние НЕ установлено
        mock_state.set_state.assert_not_called()

        # Проверяем, что пользователю показано сообщение об ошибке
        mock_user_message.answer.assert_called_once()
        call_args = mock_user_message.answer.call_args
        assert '❌ У вас нет прав' in call_args[0][0]
