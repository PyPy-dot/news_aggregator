"""
User repository для работы с пользователями.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from database.repositories.base import BaseRepository
from services.util import encrypt_user_id, decrypt_user_id, hash_user_id_for_lookup

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """
    Репозиторий для работы с пользователями.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def _fix_empty_datetime_fields(self, telegram_id: int) -> None:
        """
        Исправить пустые строки в datetime полях для пользователя.

        Вызывается перед загрузкой пользователя для предотвращения ошибки
        "Invalid isoformat string: ''"
        """
        user_hash = hash_user_id_for_lookup(telegram_id)
        await self.session.execute(
            text("""
                UPDATE users
                SET subscription_started_at = NULL
                WHERE user_id_hash = :user_hash AND subscription_started_at = ''
            """),
            {'user_hash': user_hash}
        )
        await self.session.execute(
            text("""
                UPDATE users
                SET subscription_ends_at = NULL
                WHERE user_id_hash = :user_hash AND subscription_ends_at = ''
            """),
            {'user_hash': user_hash}
        )
        await self.session.commit()

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """
        Найти пользователя по Telegram ID.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            Пользователь или None
        """
        user_hash = hash_user_id_for_lookup(telegram_id)

        logger.debug(f"🔍 Поиск пользователя в БД: telegram_id={telegram_id}, hash={user_hash[:20]}...")

        # Сначала исправляем пустые строки в БД (до загрузки!)
        await self._fix_empty_datetime_fields(telegram_id)

        result = await self.session.execute(
            select(User).where(User.user_id_hash == user_hash)
        )
        user = result.scalar_one_or_none()

        if user:
            logger.debug(f"✅ Пользователь найден: ID={user.id}, role={user.role}")
        else:
            logger.warning(f"❌ Пользователь не найден в БД: telegram_id={telegram_id}")

        return user

    async def create_user(
        self,
        telegram_id: int,
        role: str = 'user',
        preferred_tags: list[str] | None = None,
        preferred_categories: list[str] | None = None,
    ) -> User:
        """
        Создать нового пользователя.

        Args:
            telegram_id: ID пользователя в Telegram
            role: Роль пользователя ('user' или 'admin')
            preferred_tags: Предпочтительные теги
            preferred_categories: Предпочтительные категории

        Returns:
            Созданный пользователь
        """
        encrypted_id = encrypt_user_id(telegram_id)
        user_hash = hash_user_id_for_lookup(telegram_id)

        # Проверяем, существует ли уже пользователь
        existing = await self.get_by_telegram_id(telegram_id)
        if existing:
            return existing

        now = datetime.now(timezone.utc)

        user = User(
            user_id_encrypted=encrypted_id,
            user_id_hash=user_hash,
            role=role,
            created_at=now,
            has_subscription=(role == 'admin'),  # Admin получает подписку
            subscription_started_at=now if role == 'admin' else None,
            subscription_ends_at=None if role == 'admin' else None,  # NULL = бессрочно для admin
            # Нормализация тэгов и категорий к нижнему регистру
            preferred_tags=json.dumps(
                [tag.lower() for tag in preferred_tags] if preferred_tags else [],
                ensure_ascii=False
            ),
            preferred_categories=json.dumps(
                [cat.lower() for cat in preferred_categories] if preferred_categories else [],
                ensure_ascii=False
            ),
        )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_or_create_user(
        self,
        telegram_id: int,
        preferred_tags: list[str] | None = None,
        preferred_categories: list[str] | None = None,
    ) -> User:
        """
        Получить пользователя или создать нового.

        Args:
            telegram_id: ID пользователя в Telegram
            preferred_tags: Предпочтительные теги (для нового пользователя)
            preferred_categories: Предпочтительные категории (для нового пользователя)

        Returns:
            Существующий или newly созданный пользователь
        """
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            return user

        return await self.create_user(
            telegram_id,
            preferred_tags=preferred_tags,
            preferred_categories=preferred_categories,
        )

    async def update_subscription(
        self,
        telegram_id: int,
        has_subscription: bool,
        started_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> bool:
        """
        Обновить подписку пользователя.

        Args:
            telegram_id: ID пользователя в Telegram
            has_subscription: Флаг наличия подписки
            started_at: Дата начала подписки
            ends_at: Дата окончания подписки (None = бессрочно)

        Returns:
            True если обновлено, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        user.has_subscription = has_subscription
        # Нормализуем пустые строки в None
        user.subscription_started_at = started_at if started_at != '' else None
        user.subscription_ends_at = ends_at if ends_at != '' else None

        await self.session.commit()
        await self.session.refresh(user)
        return True

    async def update_preferences(
        self,
        telegram_id: int,
        preferred_tags: list[str] | None = None,
        preferred_categories: list[str] | None = None,
    ) -> bool:
        """
        Обновить предпочтения пользователя.

        Args:
            telegram_id: ID пользователя в Telegram
            preferred_tags: Предпочтительные теги
            preferred_categories: Предпочтительные категории

        Returns:
            True если обновлено, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        if preferred_tags is not None:
            # Нормализация тэгов к нижнему регистру
            user.preferred_tags = json.dumps(
                [tag.lower() for tag in preferred_tags], ensure_ascii=False
            )

        if preferred_categories is not None:
            # Нормализация категорий к нижнему регистру
            user.preferred_categories = json.dumps(
                [cat.lower() for cat in preferred_categories], ensure_ascii=False
            )

        await self.session.commit()
        await self.session.refresh(user)
        return True

    async def add_preferred_tag(self, telegram_id: int, tag: str) -> bool:
        """
        Добавить предпочтительный тег (case-insensitive).

        Args:
            telegram_id: ID пользователя в Telegram
            tag: Тег для добавления

        Returns:
            True если добавлен, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        tag_normalized = tag.lower()
        tags = [t.lower() for t in json.loads(user.preferred_tags or '[]')]
        if tag_normalized not in tags:
            tags.append(tag_normalized)
            user.preferred_tags = json.dumps(tags, ensure_ascii=False)
            await self.session.commit()
        return True

    async def remove_preferred_tag(self, telegram_id: int, tag: str) -> bool:
        """
        Удалить предпочтительный тег (case-insensitive).

        Args:
            telegram_id: ID пользователя в Telegram
            tag: Тег для удаления

        Returns:
            True если удалён, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        tag_normalized = tag.lower()
        tags = [t.lower() for t in json.loads(user.preferred_tags or '[]')]
        if tag_normalized in tags:
            tags.remove(tag_normalized)
            user.preferred_tags = json.dumps(tags, ensure_ascii=False)
            await self.session.commit()
        return True

    async def add_preferred_category(self, telegram_id: int, category: str) -> bool:
        """
        Добавить предпочтительную категорию (case-insensitive).

        Args:
            telegram_id: ID пользователя в Telegram
            category: Категория для добавления

        Returns:
            True если добавлена, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        category_normalized = category.lower()
        categories = [c.lower() for c in json.loads(user.preferred_categories or '[]')]
        if category_normalized not in categories:
            categories.append(category_normalized)
            user.preferred_categories = json.dumps(categories, ensure_ascii=False)
            await self.session.commit()
        return True

    async def remove_preferred_category(self, telegram_id: int, category: str) -> bool:
        """
        Удалить предпочтительную категорию (case-insensitive).

        Args:
            telegram_id: ID пользователя в Telegram
            category: Категория для удаления

        Returns:
            True если удалена, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        category_normalized = category.lower()
        categories = [c.lower() for c in json.loads(user.preferred_categories or '[]')]
        if category_normalized in categories:
            categories.remove(category_normalized)
            user.preferred_categories = json.dumps(categories, ensure_ascii=False)
            await self.session.commit()
        return True

    async def get_preferences(self, telegram_id: int) -> dict:
        """
        Получить предпочтения пользователя.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            dict: {
                'preferred_tags': list[str],
                'preferred_categories': list[str]
            }
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return {'preferred_tags': [], 'preferred_categories': []}

        return {
            'preferred_tags': json.loads(user.preferred_tags or '[]'),
            'preferred_categories': json.loads(user.preferred_categories or '[]')
        }

    async def fix_categories_case(
        self,
        telegram_id: int,
        categories_repo
    ) -> bool:
        """
        Исправить регистр категорий на оригинальный (из справочника).

        Конвертирует категории из нижнего регистра (например, "политика")
        в оригинальный регистр из справочника (например, "Политика").

        Args:
            telegram_id: ID пользователя
            categories_repo: Репозиторий категорий для получения справочника

        Returns:
            True если были внесены изменения
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        current_categories = json.loads(user.preferred_categories or '[]')
        if not current_categories:
            return False

        # Получаем все категории из справочника
        all_categories = await categories_repo.get_all_categories(active_only=False)
        categories_map = {cat.name.lower(): cat.name for cat in all_categories}

        # Конвертируем категории в оригинальный регистр
        fixed_categories = []
        changed = False

        for cat in current_categories:
            cat_lower = cat.lower()
            if cat_lower in categories_map:
                # Категория есть в справочнике — используем оригинальный регистр
                fixed_categories.append(categories_map[cat_lower])
                if cat != categories_map[cat_lower]:
                    changed = True
            else:
                # Категория не найдена в справочнике — оставляем как есть
                fixed_categories.append(cat)

        if changed:
            user.preferred_categories = json.dumps(fixed_categories, ensure_ascii=False)
            await self.session.commit()
            logger.info(f"🔧 Исправлен регистр категорий для пользователя ID={telegram_id}")

        return changed

    async def get_admins(self) -> list[User]:
        """
        Получить всех администраторов.

        Returns:
            Список пользователей с ролью admin
        """
        result = await self.session.execute(
            select(User).where(User.role == 'admin')
        )
        return result.scalars().all()

    async def is_admin(self, telegram_id: int) -> bool:
        """
        Проверить, является ли пользователь администратором.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            True если администратор, False иначе
        """
        user = await self.get_by_telegram_id(telegram_id)
        return user is not None and user.role == 'admin'

    async def has_active_subscription(self, telegram_id: int) -> bool:
        """
        Проверить, есть ли у пользователя активная подписка.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            True если подписка активна, False иначе
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False
        return user.has_active_subscription

    def get_user_telegram_id(self, user: User) -> int:
        """
        Расшифровать Telegram ID пользователя.

        Args:
            user: Пользователь

        Returns:
            Telegram ID

        Raises:
            ValueError: Если не удалось расшифровать ID
        """
        try:
            return decrypt_user_id(user.user_id_encrypted)
        except ValueError as e:
            logger.error(f"Ошибка расшифровки user_id для пользователя ID={user.id}: {e}")
            raise

    def get_user_telegram_id_safe(self, user: User) -> int | None:
        """
        Безопасно расшифровать Telegram ID пользователя.

        В отличие от get_user_telegram_id(), возвращает None вместо выброса исключения.

        Args:
            user: Пользователь

        Returns:
            Telegram ID или None если не удалось расшифровать
        """
        try:
            return decrypt_user_id(user.user_id_encrypted)
        except ValueError as e:
            logger.warning(f"Не удалось расшифровать user_id для пользователя ID={user.id}: {e}")
            return None

    async def fix_empty_datetime_fields(self) -> int:
        """
        Исправить записи с пустыми строками в datetime полях.

        Возвращает количество исправленных записей.
        """
        from sqlalchemy import text

        # Исправляем subscription_started_at
        result_started = await self.session.execute(
            text("UPDATE users SET subscription_started_at = NULL WHERE subscription_started_at = ''")
        )
        # Исправляем subscription_ends_at
        result_ends = await self.session.execute(
            text("UPDATE users SET subscription_ends_at = NULL WHERE subscription_ends_at = ''")
        )

        await self.session.commit()

        fixed_count = result_started.rowcount + result_ends.rowcount
        if fixed_count > 0:
            logger.info(f"Исправлено {fixed_count} записей с пустыми datetime полями")

        return fixed_count

    async def clear_preferences(self, telegram_id: int) -> bool:
        """
        Очистить предпочтения пользователя (категории и тэги).

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            True если успешно
        """
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.preferred_categories = '[]'
            user.preferred_tags = '[]'
            await self.session.commit()
            logger.info(f"🗑️ Предпочтения пользователя ID={telegram_id} очищены")
            return True

        logger.warning(f"Пользователь ID={telegram_id} не найден для очистки предпочтений")
        return False

    # =============================================================================
    # 2FA методы
    # =============================================================================

    async def set_totp_secret(
        self,
        telegram_id: int,
        totp_secret: str
    ) -> bool:
        """
        Установить TOTP секрет для пользователя.

        Args:
            telegram_id: Telegram ID пользователя
            totp_secret: TOTP секрет (Base32)

        Returns:
            True если установлено, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        user.totp_secret = totp_secret
        user.totp_enabled = False  # Пока не включено, пока пользователь не подтвердит
        await self.session.commit()

        logger.info(f"🔑 TOTP секрет установлен для пользователя ID={telegram_id}")
        return True

    async def enable_2fa(self, telegram_id: int) -> bool:
        """
        Включить 2FA для пользователя.

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            True если включено, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        user.totp_enabled = True
        await self.session.commit()

        logger.info(f"✅ 2FA включена для пользователя ID={telegram_id}")
        return True

    async def disable_2fa(self, telegram_id: int) -> bool:
        """
        Отключить 2FA для пользователя.

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            True если отключено, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        user.totp_enabled = False
        user.totp_secret = None
        user.totp_backup_codes = None
        await self.session.commit()

        logger.info(f"🚫 2FA отключена для пользователя ID={telegram_id}")
        return True

    async def set_backup_codes(
        self,
        telegram_id: int,
        backup_codes_json: str
    ) -> bool:
        """
        Установить резервные коды для пользователя.

        Args:
            telegram_id: Telegram ID пользователя
            backup_codes_json: JSON строка с резервными кодами

        Returns:
            True если установлены, False если пользователь не найден
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return False

        user.totp_backup_codes = backup_codes_json
        await self.session.commit()

        logger.info(f"🔑 Резервные коды установлены для пользователя ID={telegram_id}")
        return True

    async def get_2fa_status(self, telegram_id: int) -> dict:
        """
        Получить статус 2FA для пользователя.

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            dict: {
                'enabled': bool,
                'has_secret': bool,
                'has_backup_codes': bool
            }
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return {
                'enabled': False,
                'has_secret': False,
                'has_backup_codes': False
            }

        return {
            'enabled': user.totp_enabled,
            'has_secret': user.totp_secret is not None,
            'has_backup_codes': user.totp_backup_codes is not None
        }

    async def consume_backup_code(
        self,
        telegram_id: int,
        code: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Использовать резервный код и удалить его из базы.

        Args:
            telegram_id: Telegram ID пользователя
            code: Резервный код

        Returns:
            Tuple[bool, Optional[str]]:
                - (True, new_codes_json) если код верный
                - (False, None) если код неверный
        """
        user = await self.get_by_telegram_id(telegram_id)
        if not user or not user.totp_backup_codes:
            return False, None

        try:
            codes = json.loads(user.totp_backup_codes)
        except json.JSONDecodeError:
            logger.error(f"Ошибка парсинга резервных кодов для пользователя ID={telegram_id}")
            return False, None

        if code in codes:
            codes.remove(code)
            new_codes_json = json.dumps(codes, ensure_ascii=False)
            user.totp_backup_codes = new_codes_json
            await self.session.commit()

            logger.info(f"✅ Резервный код использован для пользователя ID={telegram_id}, осталось {len(codes)} кодов")
            return True, new_codes_json

        logger.warning(f"Неверный резервный код для пользователя ID={telegram_id}")
        return False, None
