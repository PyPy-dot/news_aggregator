from aiogram import Bot, Dispatcher
import bot.config as conf
import bot.handlers.router as r

bot = Bot(token=conf.BOT_TOKEN)
dp = Dispatcher()

dp.include_routers(r.router)


async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
