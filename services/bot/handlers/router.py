from aiogram import Router

admin = Router()

# Импортируем хендлеры для регистрации
# commands.py регистрирует хендлеры напрямую на admin через декораторы
from services.bot.handlers import commands  # noqa: F401
from services.bot.handlers import publishers  # noqa: F401
from services.bot.handlers import direct_news  # noqa: F401
from services.bot.handlers import callbacks  # noqa: F401
from services.bot.handlers import messages  # noqa: F401
from services.bot.handlers import subscription  # noqa: F401
from services.bot.handlers import tasks  # noqa: F401
from services.bot.handlers import two_factor_auth  # noqa: F401
# listener_auth больше не используется — авторизация только через консоль

# Регистрируем роутеры (publishers и direct_news имеют свои роутеры)
admin.include_router(publishers.router)
admin.include_router(direct_news.router)
admin.include_router(two_factor_auth.router)
# listener_auth.router больше не регистрируется — авторизация только через консоль
# Старый роутер services/listener/handlers/auth.py больше не используется
