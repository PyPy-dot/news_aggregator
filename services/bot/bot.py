from aiogram import Bot, Dispatcher
import services.bot.config as conf
import services.bot.handlers.router as r

import database.models as db

bot = Bot(
    token=conf.BOT_TOKEN,
    # default=DefaultBotProperties(ParseMode.HTML),
)
dp = Dispatcher()

dp.include_routers(r.admin)
dp.startup.register(db.startup_db)


async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        bot,
        allowed_updates=['message', 'channel_post', 'edited_channel_post', 'callback_query'],
    )



