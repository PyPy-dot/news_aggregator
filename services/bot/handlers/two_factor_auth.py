"""
2FA хендлеры для Telegram бота.

Команды:
- /2fa — Управление 2FA
- /2fa setup — Настройка 2FA
- /2fa disable — Отключение 2FA
- /2fa status — Проверка статуса
- /2fa provider — Смена провайдера (google/yandex)

Поддерживаемые провайдеры:
- google — Google Authenticator (стандартный)
- yandex — Яндекс.Ключ
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.repositories.users import UserRepository
from services.auth.two_factor_auth import get_2fa_service, ProviderType
from services.bot.utils import get_repository_factory
from services.telegram.notification import send_message_with_retry

logger = logging.getLogger(__name__)

# Роутер для 2FA хендлеров
router = Router()


# =============================================================================
# FSM состояния
# =============================================================================

class TwoFactorSetup(StatesGroup):
    """Состояния для настройки 2FA."""
    waiting_for_code = State()  # Ожидание кода из аутентификатора
    waiting_for_confirm = State()  # Ожидание подтверждения


# =============================================================================
# Команды
# =============================================================================

@router.message(Command("2fa"))
async def cmd_2fa(message: Message):
    """Команда /2fa — главное меню 2FA."""
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        status = await user_repo.get_2fa_status(message.from_user.id)

    if status['enabled']:
        text = (
            "🔐 **2FA включена**\n\n"
            "Ваш аккаунт защищён двухфакторной аутентификацией.\n\n"
            "Доступные команды:\n"
            "/2fa disable — Отключить 2FA\n"
            "/2fa status — Проверить статус"
        )
    else:
        text = (
            "🔐 **Двухфакторная аутентификация (2FA)**\n\n"
            "2FA добавляет дополнительный уровень защиты вашего аккаунта.\n\n"
            "Для настройки:\n"
            "1. Нажмите /2fa setup\n"
            "2. Отсканируйте QR-код в Google Authenticator / Authy\n"
            "3. Введите код из приложения\n\n"
            "Доступные команды:\n"
            "/2fa setup — Настроить 2FA\n"
            "/2fa status — Проверить статус"
        )

    await send_message_with_retry(
        message,
        text,
        parse_mode='Markdown'
    )


@router.message(Command("2fa", "setup"))
async def cmd_2fa_setup(message: Message, state: FSMContext):
    """Команда /2fa setup — начало настройки 2FA."""
    # Проверяем, админ ли пользователь
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        user = await user_repo.get_by_telegram_id(message.from_user.id)

        if not user or user.role != 'admin':
            await send_message_with_retry(
                message,
                "❌ Эта команда доступна только администраторам."
            )
            return

        # Проверяем, не включена ли уже 2FA
        status = await user_repo.get_2fa_status(message.from_user.id)
        if status['enabled']:
            await send_message_with_retry(
                message,
                "⚠️ 2FA уже включена. Используйте /2fa disable для отключения."
            )
            return

    # Получаем текущий провайдер
    try:
        from config.settings import settings
        provider = getattr(settings, 'listener_2fa_provider', 'google')
        if provider not in ('google', 'yandex'):
            provider = 'google'
    except Exception:
        provider = 'google'

    # Генерируем новый секрет
    totp_service = get_2fa_service(provider)
    secret = totp_service.generate_secret()

    # Создаём provisioning URI
    username = message.from_user.username or f"user_{message.from_user.id}"
    uri = totp_service.get_provisioning_uri(secret, username)

    # Генерируем QR-код
    qr_bytes = totp_service.generate_qr_code(uri)

    # Сохраняем секрет в состоянии (пока не включаем)
    await state.update_data(totp_secret=secret)
    await state.set_state(TwoFactorSetup.waiting_for_code)

    # Отправляем QR-код
    from io import BytesIO
    photo = FSInputFile(BytesIO(qr_bytes), filename="qr_code.png")

    # Отправляем инструкцию для текущего провайдера
    await send_message_with_retry(
        message,
        totp_service.get_setup_instructions(),
        parse_mode='Markdown'
    )

    # Отправляем QR-код
    await send_message_with_retry(
        message,
        f"_Секретный ключ (для ручного ввода):_\n`{secret}`",
        photo=photo,
        parse_mode='Markdown'
    )

    await send_message_with_retry(
        message,
        "👇 Введите 6-значный код из приложения:"
    )


@router.message(TwoFactorSetup.waiting_for_code)
async def handle_verification_code(message: Message, state: FSMContext):
    """Проверка кода из аутентификатора."""
    code = message.text.strip()

    # Проверяем формат кода (6 цифр)
    if not code.isdigit() or len(code) != 6:
        await send_message_with_retry(
            message,
            "❌ Неверный формат. Введите 6-значный код:"
        )
        return

    # Получаем секрет из состояния
    data = await state.get_data()
    secret = data.get('totp_secret')

    if not secret:
        await send_message_with_retry(
            message,
            "❌ Ошибка: сессия истекла. Начните настройку заново: /2fa setup"
        )
        await state.clear()
        return

    # Проверяем код
    totp_service = get_2fa_service()

    if totp_service.verify_code(secret, code):
        # Код верный — включаем 2FA
        async with get_repository_factory() as factory:
            user_repo = factory.users()

            # Сохраняем секрет и включаем 2FA
            await user_repo.set_totp_secret(message.from_user.id, secret)
            await user_repo.enable_2fa(message.from_user.id)

            # Генерируем резервные коды
            backup_codes = totp_service.generate_backup_codes(count=10)
            backup_codes_json = totp_service.serialize_backup_codes(backup_codes)
            await user_repo.set_backup_codes(message.from_user.id, backup_codes_json)

        # Отправляем резервные коды
        codes_text = "\n".join(f"{i+1}. {code}" for i, code in enumerate(backup_codes))

        await send_message_with_retry(
            message,
            "✅ **2FA успешно настроена!**\n\n"
            "🔑 **Резервные коды для восстановления:**\n\n"
            f"{codes_text}\n\n"
            "**Важно:**\n"
            "- Сохраните эти коды в надёжном месте\n"
            "- Каждый код можно использовать только один раз\n"
            "- Если потеряете доступ к приложению, используйте резервные коды\n\n"
            "2FA теперь включена для вашего аккаунта."
        )

        await state.clear()
    else:
        await send_message_with_retry(
            message,
            "❌ Неверный код. Попробуйте ещё раз:\n\n"
            "Убедитесь, что:\n"
            "- Время на устройстве синхронизировано\n"
            "- Вы вводите актуальный код (обновляется каждые 30 сек)"
        )


@router.message(Command("2fa", "disable"))
async def cmd_2fa_disable(message: Message):
    """Команда /2fa disable — отключение 2FA."""
    # Проверяем, админ ли пользователь
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        user = await user_repo.get_by_telegram_id(message.from_user.id)

        if not user or user.role != 'admin':
            await send_message_with_retry(
                message,
                "❌ Эта команда доступна только администраторам."
            )
            return

        # Проверяем, включена ли 2FA
        status = await user_repo.get_2fa_status(message.from_user.id)
        if not status['enabled']:
            await send_message_with_retry(
                message,
                "⚠️ 2FA ещё не включена."
            )
            return

    # Отключаем 2FA
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        await user_repo.disable_2fa(message.from_user.id)

    await send_message_with_retry(
        message,
        "🚫 **2FA отключена**\n\n"
        "Ваш аккаунт больше не защищён двухфакторной аутентификацией.\n\n"
        "Для повторной настройки используйте: /2fa setup"
    )


@router.message(Command("2fa", "status"))
async def cmd_2fa_status(message: Message):
    """Команда /2fa status — проверка статуса 2FA."""
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        status = await user_repo.get_2fa_status(message.from_user.id)

    # Получаем текущий провайдер
    try:
        from config.settings import settings
        provider = getattr(settings, 'listener_2fa_provider', 'google')
        provider_name = "Яндекс.Ключ" if provider == 'yandex' else "Google Authenticator"
    except Exception:
        provider = 'google'
        provider_name = "Google Authenticator"

    if not status['has_secret']:
        text = (
            "📊 **Статус 2FA:**\n\n"
            "❌ 2FA не настроена\n\n"
            f"🔹 Текущий провайдер: {provider_name}\n"
            f"🔹 Для настройки: /2fa setup\n"
            f"🔹 Сменить провайдер: /2fa provider"
        )
    elif not status['enabled']:
        text = (
            "📊 **Статус 2FA:**\n\n"
            "⚠️ 2FA настроена, но не включена\n\n"
            f"🔹 Текущий провайдер: {provider_name}\n"
            f"🔹 Завершите настройку: /2fa setup\n"
            f"🔹 Сменить провайдер: /2fa provider"
        )
    else:
        backup_status = "✅" if status['has_backup_codes'] else "❌"
        text = (
            "📊 **Статус 2FA:**\n\n"
            "✅ 2FA включена\n"
            f"🔹 Провайдер: {provider_name}\n"
            f"{backup_status} Резервные коды: {'есть' if status['has_backup_codes'] else 'нет'}\n\n"
            "🔹 Для отключения: /2fa disable\n"
            "🔹 Сменить провайдер: /2fa provider"
        )

    await send_message_with_retry(message, text)


@router.message(Command("2fa", "provider"))
async def cmd_2fa_provider(message: Message):
    """Команда /2fa provider — смена провайдера 2FA."""
    # Проверяем, админ ли пользователь
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        user = await user_repo.get_by_telegram_id(message.from_user.id)

        if not user or user.role != 'admin':
            await send_message_with_retry(
                message,
                "❌ Эта команда доступна только администраторам."
            )
            return

    # Создаём клавиатуру с выбором провайдера
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔵 Google Authenticator", callback_data="2fa_provider_google")],
        [InlineKeyboardButton(text="🔴 Яндекс.Ключ", callback_data="2fa_provider_yandex")],
    ])

    # Получаем текущий провайдер
    try:
        from config.settings import settings
        provider = getattr(settings, 'listener_2fa_provider', 'google')
        current = "Яндекс.Ключ" if provider == 'yandex' else "Google Authenticator"
    except Exception:
        current = "Google Authenticator"

    text = (
        f"🔐 **Смена провайдера 2FA**\n\n"
        f"Текущий провайдер: **{current}**\n\n"
        "Выберите новый провайдер:\n\n"
        "🔵 **Google Authenticator** — стандартный выбор, поддерживается всеми приложениями\n"
        "🔴 **Яндекс.Ключ** — российское приложение, работает без VPN\n\n"
        "_После смены провайдера потребуется перенастроить 2FA в приложении_"
    )

    await send_message_with_retry(
        message,
        text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


# =============================================================================
# Callback хендлеры для кнопок
# =============================================================================

@router.callback_query(F.data == "2fa_setup")
async def callback_2fa_setup(callback: CallbackQuery, state: FSMContext):
    """Callback для кнопки настройки 2FA."""
    await cmd_2fa_setup(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "2fa_disable")
async def callback_2fa_disable(callback: CallbackQuery):
    """Callback для кнопки отключения 2FA."""
    # Проверяем, админ ли пользователь
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

        if not user or user.role != 'admin':
            await callback.answer("❌ Только для администраторов", show_alert=True)
            return

        status = await user_repo.get_2fa_status(callback.from_user.id)
        if not status['enabled']:
            await callback.answer("⚠️ 2FA ещё не включена", show_alert=True)
            return

        # Отключаем 2FA
        await user_repo.disable_2fa(callback.from_user.id)

    await callback.message.edit_text(
        "🚫 **2FA отключена**\n\n"
        "Ваш аккаунт больше не защищён двухфакторной аутентификацией."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("2fa_provider_"))
async def callback_2fa_provider_set(callback: CallbackQuery):
    """Callback для кнопки выбора провайдера 2FA."""
    provider = callback.data.split("_")[-1]

    if provider not in ('google', 'yandex'):
        await callback.answer("❌ Неверный провайдер", show_alert=True)
        return

    # Проверяем, админ ли пользователь
    async with get_repository_factory() as factory:
        user_repo = factory.users()
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

        if not user or user.role != 'admin':
            await callback.answer("❌ Только для администраторов", show_alert=True)
            return

    # Получаем текущий провайдер
    try:
        from config.settings import settings
        current_provider = getattr(settings, 'listener_2fa_provider', 'google')
    except Exception:
        current_provider = 'google'

    if provider == current_provider:
        await callback.answer(f"✅ {provider} уже выбран", show_alert=False)
        return

    # Предупреждение если 2FA уже включена
    status = await user_repo.get_2fa_status(callback.from_user.id)
    if status['enabled']:
        provider_name = "Яндекс.Ключ" if provider == 'yandex' else "Google Authenticator"
        await callback.message.answer(
            "⚠️ **Внимание!**\n\n"
            f"2FA уже включена. После смены провайдера на **{provider_name}** потребуется:\n\n"
            "1. Отключить текущую 2FA: `/2fa disable`\n"
            "2. Изменить провайдер в `.env`: `LISTENER_2FA_PROVIDER={provider}`\n"
            "3. Перезапустить бота\n"
            "4. Настроить 2FA заново: `/2fa setup`\n\n"
            "_Это необходимо потому, что разные провайдеры используют разные форматы URI_",
            parse_mode='Markdown'
        )
        await callback.answer()
    else:
        # 2FA не включена — просто информируем
        provider_name = "Яндекс.Ключ" if provider == 'yandex' else "Google Authenticator"
        await callback.message.answer(
            f"✅ Выбран провайдер: **{provider_name}**\n\n"
            f"Для применения измените в `.env`:\n"
            f"`LISTENER_2FA_PROVIDER={provider}`\n\n"
            f"Затем перезапустите бота и настройте 2FA: `/2fa setup`",
            parse_mode='Markdown'
        )
        await callback.answer()
