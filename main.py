import asyncio
import logging
import signal
import sys

# НАСТРОЙКА ЛОГИРОВАНИЯ ДО ВСЕХ ОСТАЛЬНЫХ ИМПОРТОВ
from services.logging_config import setup_logging, get_logger

setup_logging(
    level=logging.INFO,
    log_to_file=True,
    max_bytes=10 * 1024 * 1024,  # 10 MB
    backup_count=7
)

logger = get_logger(__name__)

# Импорты после настройки логирования
import services.bot.bot as main_bot
from services.listener.bot import ListenerBot
from services.scheduler.scheduler import Scheduler


async def main():
    listener = ListenerBot()
    scheduler = Scheduler()
    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("Получен сигнал остановки...")
        shutdown_event.set()

    # Windows не поддерживает add_signal_handler, используем try/except
    loop = asyncio.get_running_loop()
    if sys.platform != 'win32':
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_signal)

    logger.info("🤖 Бот запущен (нажми Ctrl+C для остановки)")
    logger.info("Запуск ботов и планировщика...")

    # Запускаем процессы как задачи
    bot_task = asyncio.create_task(main_bot.on_startup())
    listener_task = asyncio.create_task(listener.on_start())
    scheduler_task = asyncio.create_task(scheduler.start())

    logger.info("✅ Все процессы запущены")

    try:
        # Ждём сигнала остановки
        await shutdown_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Получен сигнал прерывания")
    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
    finally:
        logger.info("Остановка ботов и планировщика...")

        # Отменяем все задачи
        for task in [bot_task, listener_task, scheduler_task]:
            task.cancel()

        # Ждём завершения
        await asyncio.gather(bot_task, listener_task, scheduler_task, return_exceptions=True)

        try:
            await listener.on_stop()
        except Exception as e:
            logger.error(f"Ошибка при остановке listener: {e}")

        try:
            await scheduler.stop()
        except Exception as e:
            logger.error(f"Ошибка при остановке планировщика: {e}")

        try:
            await main_bot.bot.session.close()
        except Exception:
            pass

        logger.info('👋 Бот выключен')


if __name__ == "__main__":
    asyncio.run(main())
