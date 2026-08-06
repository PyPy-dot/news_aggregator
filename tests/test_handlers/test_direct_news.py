"""
Тесты для прямой генерации новостей (direct news handler).

Проверка:
- Обычный пользователь не может генерировать новости
- Администратор может генерировать новости
- Используется заглушка вместо AI модели
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


class TestDirectNewsGeneration:
    """Тесты генерации новостей с заглушкой вместо AI."""

    @pytest.mark.asyncio
    async def test_handle_description_saves_data(
        self,
        mock_admin_message: Message,
        mock_state: FSMContext,
    ):
        """Обработчик описания сохраняет данные в состоянии."""
        mock_admin_message.text = 'Тестовое описание события'

        # Мокаем получение publishers
        with patch('services.bot.handlers.direct_news.RepositoryFactory') as MockFactory:
            mock_factory = MagicMock()
            mock_publishers_repo = AsyncMock()
            mock_publisher = MagicMock()
            mock_publisher.id = 1
            mock_publisher.title = 'Test Channel'
            mock_publisher.channel_id = -1001234567890
            mock_publishers_repo.get_all = AsyncMock(return_value=[mock_publisher])
            mock_factory.publishers.return_value = mock_publishers_repo
            MockFactory.return_value = mock_factory

            # Мокаем клавиатуру
            with patch('services.bot.handlers.direct_news.create_direct_news_channel_kb') as mock_kb:
                mock_kb.return_value = MagicMock()

                from services.bot.handlers.direct_news import handle_description
                await handle_description(mock_admin_message, mock_state)

                # Проверяем, что данные сохранены
                mock_state.update_data.assert_called()
                call_args = mock_state.update_data.call_args_list[0]
                assert call_args[1]['description'] == 'Тестовое описание события'

                # Проверяем, что состояние изменено
                mock_state.set_state.assert_called_once_with(DirectNewsStates.waiting_for_channel)

    @pytest.mark.asyncio
    async def test_admin_can_generate_news_with_stub(
        self,
        mock_admin_message: Message,
        mock_state: FSMContext,
    ):
        """Администратор может сгенерировать новость с заглушкой вместо AI."""
        import json

        # Устанавливаем данные состояния
        mock_state.get_data = AsyncMock(return_value={
            'description': 'Тестовое описание новости',
        })

        mock_admin_message.text = '📢 Test Channel'
        mock_admin_message.answer = AsyncMock()

        # Мокаем EditorAgent с заглушкой
        # send_question возвращает JSON строку, parse_json_response парсит её
        mock_json_response = json.dumps({
            'title': 'Тестовый заголовок',
            'text': 'Тестовый текст новости',
            'summary': 'Краткое содержание',
            'news_tags': ['тест', 'новость']
        })

        with patch('services.bot.handlers.direct_news.EditorAgent') as MockEditorAgent:
            mock_agent = MagicMock()
            # send_question — async метод, возвращает coroutine
            mock_agent.send_question = AsyncMock(return_value=mock_json_response)
            # parse_json_response — static method, но вызывается через instance
            mock_agent.parse_json_response = MagicMock(return_value={
                'title': 'Тестовый заголовок',
                'text': 'Тестовый текст новости',
                'summary': 'Краткое содержание',
                'news_tags': ['тест', 'новость']
            })
            MockEditorAgent.return_value = mock_agent

            # Мокаем фабрику репозиториев
            with patch('services.bot.handlers.direct_news.RepositoryFactory') as MockFactory:
                mock_factory = MagicMock()

                mock_news_repo = AsyncMock()
                mock_created_news = MagicMock()
                mock_created_news.id = 123
                mock_news_repo.create_news = AsyncMock(return_value=mock_created_news)
                mock_factory.news.return_value = mock_news_repo

                mock_publishers_repo = AsyncMock()
                mock_publisher = MagicMock()
                mock_publisher.id = 1
                mock_publisher.channel_id = -1001234567890
                mock_publisher.title = 'Test Channel'
                mock_publishers_repo.get_by_id = AsyncMock(return_value=mock_publisher)
                mock_publishers_repo.get_all = AsyncMock(return_value=[mock_publisher])
                mock_factory.publishers.return_value = mock_publishers_repo

                MockFactory.return_value = mock_factory

                # Мокаем отправку в Telegram (импортируется внутри функции)
                import services.bot.handlers.direct_news as direct_news_module
                original_send = direct_news_module.bot.send_photo if hasattr(direct_news_module, 'bot') else None
                mock_bot_send = AsyncMock()

                with patch.object(direct_news_module, 'bot', create=True) as mock_bot:
                    mock_bot.send_photo = mock_bot_send

                    # Вызываем хендлер выбора канала
                    from services.bot.handlers.direct_news import handle_channel_selection
                    await handle_channel_selection(mock_admin_message, mock_state)

                    # Проверяем, что новость сохранена
                    mock_news_repo.create_news.assert_called_once()


class TestCheckAdminAccess:
    """Тесты проверки прав администратора (с моками)."""

    @pytest.mark.asyncio
    async def test_admin_access_check_with_mock(self, mock_admin_message: Message):
        """Проверка прав администратора с моком БД."""
        # Мокаем UserRepository
        with patch('services.bot.handlers.direct_news.UserRepository') as MockUserRepo:
            mock_user = MagicMock()
            mock_user.role = 'admin'

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_telegram_id = AsyncMock(return_value=mock_user)
            MockUserRepo.return_value = mock_repo_instance

            from services.bot.handlers.direct_news import check_admin_access
            result = await check_admin_access(mock_admin_message)

            assert result is True
            mock_admin_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_access_check_with_mock(self, mock_user_message: Message):
        """Проверка прав обычного пользователя с моком БД."""
        # Мокаем UserRepository
        with patch('services.bot.handlers.direct_news.UserRepository') as MockUserRepo:
            mock_user = MagicMock()
            mock_user.role = 'user'

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_telegram_id = AsyncMock(return_value=mock_user)
            MockUserRepo.return_value = mock_repo_instance

            from services.bot.handlers.direct_news import check_admin_access
            result = await check_admin_access(mock_user_message)

            assert result is False
            mock_user_message.answer.assert_called_once()
            call_args = mock_user_message.answer.call_args
            assert '❌ У вас нет прав' in call_args[0][0]
