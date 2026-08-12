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
    waiting_for_category = State()
    waiting_for_confirm = State()


class DirectNewsStates(StatesGroup):
    """Состояния для прямой генерации новостей админом."""
    waiting_for_description = State()  # Ожидание описания новости
    waiting_for_media = State()  # Ожидание фото/видео (опционально)
    waiting_for_channel = State()  # Выбор канала публикации
    confirm_generation = State()  # Подтверждение генерации


class EditNewsStates(StatesGroup):
    """Состояния для редактирования новости админом."""
    waiting_for_text = State()  # Ожидание нового текста новости


class UserPreferencesStates(StatesGroup):
    """Состояния для управления предпочтениями пользователя."""
    viewing_categories = State()  # Просмотр категорий
    viewing_tags = State()  # Просмотр тэгов
    waiting_for_tags_input = State()  # Ожидание ввода тэгов пользователем


class TaskStates(StatesGroup):
    """Состояния для управления задачами."""
    # Прямая генерация
    waiting_for_description = State()  # Ожидание описания для прямой генерации
    waiting_for_channel = State()  # Выбор канала публикации
    waiting_for_direct_scheduled_time = State()  # Выбор времени для разовой генерации
    waiting_for_direct_recurrence = State()  # Выбор периодичности
    waiting_for_direct_time = State()  # Выбор времени для прямой генерации

    # Плановая обработка
    waiting_for_scheduled_recurrence = State()  # Выбор периодичности для плановой
    waiting_for_scheduled_time = State()  # Выбор времени для плановой

    # Редактирование
    editing_description = State()  # Редактирование описания
    editing_scheduled_at = State()  # Редактирование времени
    editing_recurrence = State()  # Редактирование периодичности
    editing_publisher = State()  # Редактирование канала публикации
