import asyncio
import logging
import bot.bot as bot

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print('Бот запущен')
    try:
        asyncio.run(bot.on_startup())
    except KeyboardInterrupt:
        print('Бот выключен')
