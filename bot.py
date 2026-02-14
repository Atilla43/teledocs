import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.database.connection import init_db
from app.handlers import chat, common, document
from app.middlewares.db_middleware import DatabaseMiddleware
from app.middlewares.user_middleware import UserRegistrationMiddleware
from app.services.document_service import DocumentService
from app.services.openai_service import OpenAIService
from app.services.template_registry import TemplateRegistry
from config.settings import settings


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize database
    await init_db()

    # Create services
    openai_service = OpenAIService(
        api_key=settings.openai_api_key,
        model=settings.openai_chat_model,
    )
    template_registry = TemplateRegistry(settings.templates_dir)
    document_service = DocumentService(settings.templates_dir, settings.output_dir)

    # Create bot and dispatcher
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Register middlewares (order matters: DB first, then user registration)
    dp.message.middleware(DatabaseMiddleware())
    dp.message.middleware(UserRegistrationMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())

    # Inject services into handler data
    dp["openai_service"] = openai_service
    dp["template_registry"] = template_registry
    dp["document_service"] = document_service

    # Register routers (order matters: specific first, catch-all last)
    dp.include_routers(
        common.router,
        document.router,
        chat.router,
    )

    # Start polling
    logging.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
