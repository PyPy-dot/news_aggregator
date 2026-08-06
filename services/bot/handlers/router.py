from aiogram import Router

admin = Router()

# Импортируем роутеры для регистрации
from services.bot.handlers import publishers  # noqa: F401
from services.bot.handlers import direct_news  # noqa: F401

# Регистрируем роутеры
admin.include_router(publishers.router)
admin.include_router(direct_news.router)
