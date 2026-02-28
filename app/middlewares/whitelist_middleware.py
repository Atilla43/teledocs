from typing import Any, Awaitable, Callable

import aiosqlite
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.database.repositories.whitelist_repo import is_whitelisted
from config.settings import settings


class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not settings.whitelist_enabled:
            return await handler(event, data)

        user_id = _get_user_id(event)
        if user_id is None:
            return await handler(event, data)

        # Admins always have access
        if user_id in settings.admin_ids:
            return await handler(event, data)

        # Check whitelist
        db: aiosqlite.Connection = data["db"]
        if await is_whitelisted(db, user_id):
            return await handler(event, data)

        # Deny access
        if isinstance(event, Message):
            await event.answer(
                "У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору для получения доступа."
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("Нет доступа", show_alert=True)

        return None


def _get_user_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message) and event.from_user:
        return event.from_user.id
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user.id
    return None
