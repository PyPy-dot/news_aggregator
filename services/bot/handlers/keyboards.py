from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButtonRequestChat)

# Меню для обычного пользователя
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📬 Последние посты'), KeyboardButton(text='📝 Сгенерированные новости')],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Меню для администратора
admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📬 Последние посты'), KeyboardButton(text='📝 Сгенерированные новости')],
        [KeyboardButton(text='📢 Каналы публикации')],
        [KeyboardButton(text='✍️ Прямая генерация новости')],
        [KeyboardButton(text='Получить ID фото')],
        [KeyboardButton(text='Работа с каналами')],
        [KeyboardButton(text='Доверенные источники')],
        [KeyboardButton(text='Работа с сайтами')]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Алиас для обратной совместимости
kb1 = admin_kb

kb2 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='Вернуться в меню', callback_data='back_to_menu')]
    ]
)

ikb1 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='Добавить', callback_data='add_channel')],
        [InlineKeyboardButton(text='Удалить', callback_data='delete_channel')]
    ]
)

ikb_trusted = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='✅ Сделать доверенным', callback_data='make_trusted')],
        [InlineKeyboardButton(text='❌ Снять доверие', callback_data='remove_trusted')]
    ]
)

choose_chat_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(
        text="Выбрать канал",
        request_chat=KeyboardButtonRequestChat(
            request_id=1,
            chat_is_channel=True,
            bot_is_member=True,
            request_title=True
        )
    ),
        KeyboardButton(
            text='Выбрать группу',
            request_chat=KeyboardButtonRequestChat(
                request_id=2,
                chat_is_channel=False,
                bot_is_member=True,
            )
        )
     ]
], resize_keyboard=True, one_time_keyboard=True)

# Клавиатуры для работы с publisher'ами
# Reply KB для главного меню publisher'ов
publishers_menu_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='📋 Список каналов')],
    [KeyboardButton(text='➕ Добавить канал')],
    [KeyboardButton(text='🔙 Назад в главное меню')]
], resize_keyboard=True, one_time_keyboard=True)

# Reply KB для просмотра списка каналов (с кнопкой возврата)
publishers_list_view_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='➕ Добавить канал')],
    [KeyboardButton(text='🔙 Назад')]
], resize_keyboard=True, one_time_keyboard=True)

# Reply KB для добавления publisher (как choose_chat_kb)
add_publisher_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(
        text="➕ Выбрать канал для публикации",
        request_chat=KeyboardButtonRequestChat(
            request_id=10,
            chat_is_channel=True,
            bot_is_member=True,
            request_title=True,
            request_description=True,  # Запрашиваем описание
            user_admin_rights=None,  # Не требуется админство
            bot_admin_rights=None,
        )
    )],
    [KeyboardButton(text='🔙 Назад')]
], resize_keyboard=True, one_time_keyboard=True)

def create_publisher_action_kb(publisher_id: int) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру действий для конкретного publisher.

    Args:
        publisher_id: ID publisher

    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Активировать', callback_data=f'activate_publisher_{publisher_id}'),
             InlineKeyboardButton(text='❌ Деактивировать', callback_data=f'deactivate_publisher_{publisher_id}')],
            [InlineKeyboardButton(text='🗑️ Удалить', callback_data=f'delete_publisher_{publisher_id}')],
            [InlineKeyboardButton(text='🔙 Назад', callback_data='publishers_menu')]
        ]
    )

# Клавиатура для выбора канала публикации (при одобрении новости)
def create_publishers_choice_kb(publishers: list) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с выбором канала для публикации.

    Args:
        publishers: Список dict с publisher'ами [{'id': 1, 'title': 'Channel'}, ...]

    Returns:
        InlineKeyboardMarkup с кнопками выбора
    """
    buttons = []
    for pub in publishers:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {pub['title']}",
                callback_data=f"publish_to_{pub['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_publish')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# KB для выбора канала при прямой генерации (reply keyboard)
def create_direct_news_channel_kb(publishers: list) -> ReplyKeyboardMarkup:
    """
    Создать клавиатуру с выбором канала для прямой генерации.

    Args:
        publishers: Список publisher'ов

    Returns:
        ReplyKeyboardMarkup с кнопками каналов
    """
    buttons = []
    for p in publishers:
        buttons.append([KeyboardButton(text=f"📢 {p.title}")])
    buttons.append([KeyboardButton(text='🔙 Назад')])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
