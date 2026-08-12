#!/usr/bin/env python3
"""
Скрипт для проверки каналов публикации.

Использование:
    python scripts/check_publishers.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в PATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


async def check_publishers():
    """Проверка каналов публикации."""
    from services.database import get_database_service
    from database import RepositoryFactory

    db_service = get_database_service()
    await db_service.connect()

    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        publishers_repo = factory.publishers()

        # Получаем все каналы
        publishers = await publishers_repo.get_all(active_only=False)

        logger.info("=" * 70)
        logger.info("📊 Каналы публикации")
        logger.info("=" * 70)

        if not publishers:
            logger.info("❌ Нет каналов в базе данных")
        else:
            for pub in publishers:
                status_icon = "✅" if pub.is_active else "❌"
                channel_id_info = pub.channel_id if pub.channel_id else "❌ НЕ УКАЗАН"

                # Проверяем формат Telegram channel ID
                if pub.channel_id:
                    if str(pub.channel_id).startswith('-100'):
                        format_ok = "✅ (верный формат)"
                    else:
                        format_ok = "⚠️ (должен начинаться с -100...)"
                else:
                    format_ok = ""

                logger.info(
                    f"\n{status_icon} ID={pub.id} | {pub.title}"
                    f"\n   Telegram channel_id: {channel_id_info} {format_ok}"
                    f"\n   Активен: {pub.is_active}"
                    f"\n   Описание: {pub.description or '-'}"
                )

        # Показываем задачи на публикацию
        from database import RepositoryFactory
        task_repo = factory.tasks()
        tasks = await task_repo.get_pending_and_active_tasks(limit=10)

        direct_gen_tasks = [t for t in tasks if t.task_type == 'direct_generation' and t.publisher_channel_id]

        if direct_gen_tasks:
            logger.info("\n" + "=" * 70)
            logger.info("📋 Задачи на прямую генерацию с публикацией")
            logger.info("=" * 70)

            for task in direct_gen_tasks:
                logger.info(
                    f"  ID={task.id} status={task.status} publisher_id={task.publisher_channel_id} "
                    f"scheduled_at={task.scheduled_at}"
                )

    await db_service.disconnect()
    logger.info("\n✅ Проверка завершена")


if __name__ == "__main__":
    asyncio.run(check_publishers())
