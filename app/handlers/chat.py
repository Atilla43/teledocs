import logging

from aiogram import Router
from aiogram.types import Message

from app.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

router = Router()


@router.message()
async def handle_chat_message(message: Message, openai_service: OpenAIService):
    """Catch-all handler: any text not matched by commands or FSM goes to AI chat."""
    if not message.text:
        return

    try:
        response = await openai_service.chat(
            user_id=message.from_user.id,
            user_message=message.text,
        )
        await message.answer(response)
    except Exception:
        logger.exception("OpenAI chat error")
        await message.answer(
            "Произошла ошибка при обращении к AI. Попробуйте позже."
        )
