import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.database.connection import init_db
from app.handlers import admin, chat, common, document, requisites, upload
from app.middlewares.db_middleware import DatabaseMiddleware
from app.middlewares.user_middleware import UserRegistrationMiddleware
from app.middlewares.whitelist_middleware import WhitelistMiddleware
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
        base_url=settings.openai_base_url,
        model=settings.openai_chat_model,
    )
    template_registry = TemplateRegistry(settings.templates_dir)
    document_service = DocumentService(settings.templates_dir, settings.output_dir)

    # Create bot and dispatcher
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Register middlewares (order matters: DB first, then whitelist, then user registration)
    dp.message.middleware(DatabaseMiddleware())
    dp.message.middleware(WhitelistMiddleware())
    dp.message.middleware(UserRegistrationMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(WhitelistMiddleware())

    # Inject services into handler data
    dp["openai_service"] = openai_service
    dp["template_registry"] = template_registry
    dp["document_service"] = document_service

    # Register routers (order matters: specific first, catch-all last)
    dp.include_routers(
        common.router,
        admin.router,
        requisites.router,  # requisites setup (before document)
        document.router,
        upload.router,   # .docx file upload handler (before catch-all chat)
        chat.router,
    )

    # Start polling with retry on network errors
    logger = logging.getLogger(__name__)
    while True:
        try:
            logger.info("Bot starting...")
            await dp.start_polling(bot)
            break
        except Exception as e:
            logger.error("Bot crashed: %s. Retrying in 5 seconds...", e)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
