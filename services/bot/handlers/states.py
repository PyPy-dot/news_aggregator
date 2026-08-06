from aiogram.fsm.state import StatesGroup, State


class AddChannel(StatesGroup):
    edit_channels = State()
    add_channel = State()


class DeleteChannel(StatesGroup):
    edit_channels = State()
    delete_channel = State()


class TrustedChannel(StatesGroup):
    select_channel = State()


class PublisherStates(StatesGroup):
    """Состояния для управления каналами публикации."""
    waiting_for_channel = State()
    waiting_for_confirm = State()


class DirectNewsStates(StatesGroup):
    """Состояния для прямой генерации новостей админом."""
    waiting_for_description = State()  # Ожидание описания новости
    waiting_for_media = State()  # Ожидание фото/видео (опционально)
    waiting_for_channel = State()  # Выбор канала публикации
    confirm_generation = State()  # Подтверждение генерации
