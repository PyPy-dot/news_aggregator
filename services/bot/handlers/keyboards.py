from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButtonRequestChat)

# Меню для обычного пользователя (базовая версия без кнопки админа и отписки)
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='💎 Подписка')],
        [KeyboardButton(text='📁 Категории'), KeyboardButton(text='🏷️ Тэги')],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


def get_user_kb_for_role(is_admin_user: bool, has_subscription: bool = False) -> ReplyKeyboardMarkup:
    """
    Получить пользовательскую клавиатуру с учётом роли и подписки.

    Args:
        is_admin_user: True если пользователь администратор
        has_subscription: True если у пользователя есть активная подписка

    Returns:
        ReplyKeyboardMarkup:
            - С кнопкой «🔙 Меню админа» для админов
            - С кнопкой «❌ Отписаться» только если есть подписка
    """
    # Базовые кнопки (есть у всех)
    base_rows = [
        [KeyboardButton(text='💎 Подписка')],
        [KeyboardButton(text='📁 Категории'), KeyboardButton(text='🏷️ Тэги')],
    ]

    # Добавляем кнопку отписки только если есть подписка
    if has_subscription:
        base_rows.append([KeyboardButton(text='❌ Отписаться')])

    # Для админов добавляем кнопку возврата в админ-меню
    if is_admin_user:
        base_rows.append([KeyboardButton(text='🔙 Меню админа')])

    return ReplyKeyboardMarkup(
        keyboard=base_rows,
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
        [KeyboardButton(text='Работа с сайтами')],
        [KeyboardButton(text='📝 Задачи')],
        [KeyboardButton(text='👤 Меню пользователя')],
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
        [InlineKeyboardButton(text='➕ Добавить', callback_data='add_channel')],
        [InlineKeyboardButton(text='🗑️ Удалить', callback_data='delete_channel')],
        [InlineKeyboardButton(text='✅ Доверенные источники', callback_data='trusted_channels_menu')],
        [InlineKeyboardButton(text='🔙 Вернуться в меню', callback_data='back_to_menu')]
    ]
)

# Клавиатура для возврата в меню работы с каналами (не в главное меню)
ikb_channels_back = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='🔙 Назад к каналам', callback_data='back_to_channels_menu')]
    ]
)

ikb_trusted = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='✅ Сделать доверенным', callback_data='make_trusted')],
        [InlineKeyboardButton(text='❌ Снять доверие', callback_data='remove_trusted')],
        [InlineKeyboardButton(text='🔙 Назад к каналам', callback_data='back_to_channels_menu')]
    ]
)

choose_chat_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(
        text="Выбрать канал",
        request_chat=KeyboardButtonRequestChat(
            request_id=1,
            chat_is_channel=True,
            bot_is_member=True,
            request_title=True,
            request_description=True  # Запрашиваем описание
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
     ],
    [KeyboardButton(text='🔙 Назад')]
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
    [KeyboardButton(text='🔙 Назад в меню каналов')]
], resize_keyboard=True, one_time_keyboard=True)

# Inline KB для прямой генерации новости (этап ввода описания)
def create_direct_news_description_inline_kb() -> InlineKeyboardMarkup:
    """Создать inline-клавиатуру с кнопкой 'Назад в меню' для этапа ввода описания."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🔙 Назад в меню', callback_data='direct_news_back_to_menu')]
        ]
    )


def create_categories_select_kb(categories: list[str]) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с категориями для выбора при добавлении канала.

    Args:
        categories: Список названий категорий

    Returns:
        InlineKeyboardMarkup с кнопками категорий
    """
    buttons = []
    row = []
    for cat in categories:
        row.append(
            InlineKeyboardButton(
                text=f'📁 {cat}',
                callback_data=f'publisher_category_{cat}'
            )
        )
        if len(row) == 2:  # 2 кнопки в ряду
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_add_publisher')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
def create_direct_news_channel_kb(publishers: list) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с выбором канала для прямой генерации.

    Args:
        publishers: Список publisher'ов

    Returns:
        InlineKeyboardMarkup с кнопками каналов
    """
    buttons = []
    for p in publishers:
        buttons.append([InlineKeyboardButton(text=f"📢 {p.title}", callback_data=f'direct_channel_{p.id}')])
    buttons.append([InlineKeyboardButton(text='🔙 Отмена', callback_data='direct_cancel')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# KB для подтверждения очистки БД
cleanup_confirm_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Да, очистить', callback_data='cleanup_confirm'),
            InlineKeyboardButton(text='❌ Отмена', callback_data='cleanup_cancel')
        ]
    ]
)


def create_categories_kb(categories: list, user_categories: list[str]) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с категориями для выбора.

    Args:
        categories: Список категорий (dict с id, name)
        user_categories: Список выбранных пользователем категорий (названия)

    Returns:
        InlineKeyboardMarkup с кнопками категорий
    """
    buttons = []
    row = []
    for cat in categories:
        name = cat['name']
        is_selected = name in user_categories
        emoji = '✅' if is_selected else '⬜'
        row.append(
            InlineKeyboardButton(
                text=f'{emoji} {name}',
                callback_data=f'category_toggle_{name}'
            )
        )
        if len(row) == 2:  # 2 кнопки в ряду
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_to_user_menu')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_tags_kb(tags: list[str], user_tags: list[str]) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с тэгами для выбора (старая версия для совместимости).

    Args:
        tags: Список тэгов
        user_tags: Список выбранных пользователем тэгов

    Returns:
        InlineKeyboardMarkup с кнопками тэгов
    """
    buttons = []
    row = []
    for tag in tags:
        is_selected = tag in user_tags
        emoji = '✅' if is_selected else '⬜'
        row.append(
            InlineKeyboardButton(
                text=f'{emoji} {tag}',
                callback_data=f'tag_toggle_{tag}'
            )
        )
        if len(row) == 2:  # 2 кнопки в ряду
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_to_user_menu')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_user_tags_kb(user_tags: list[str]) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с тэгами пользователя для удаления.

    Args:
        user_tags: Список выбранных пользователем тэгов

    Returns:
        InlineKeyboardMarkup с кнопками тэгов
    """
    buttons = []
    row = []

    # Создаём кнопки для каждого тэга пользователя
    for tag in sorted(user_tags):
        row.append(
            InlineKeyboardButton(
                text=f'❌ {tag}',
                callback_data=f'tag_remove_{tag}'
            )
        )
        if len(row) == 2:  # 2 кнопки в ряду
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Добавляем кнопку "Назад"
    buttons.append([InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_to_user_menu')])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Предопределённые тэги для выбора
PREDEFINED_TAGS = [
    'Украина', 'Россия', 'США', 'Европа', 'Китай',
    'Зеленский', 'Путин', 'Байден',
    'Киев', 'Москва', 'Лондон', 'Брюссель',
    'НАТО', 'ЕС', 'ООН',
    'БПЛА', 'ПВО', 'армия', 'фронт',
    'экономика', 'инфляция', 'валюты',
    'технологии', 'IT', 'интернет',
    'энергетика', 'газ', 'нефть',
]


def create_subscription_kb(has_active_subscription: bool) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру для меню подписки.

    Args:
        has_active_subscription: Есть ли активная подписка

    Returns:
        InlineKeyboardMarkup с кнопками
    """
    buttons = []
    if not has_active_subscription:
        buttons.append([
            InlineKeyboardButton(text='💳 Оформить подписку', callback_data='subscribe_buy')
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text='🔄 Продлить подписку', callback_data='subscribe_extend')
        ])
    buttons.append([InlineKeyboardButton(text='ℹ️ Узнать подробнее', callback_data='subscribe_info')])
    buttons.append([InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_to_user_menu')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
