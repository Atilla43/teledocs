import aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.database.repositories.whitelist_repo import (
    add_to_whitelist,
    get_whitelist,
    remove_from_whitelist,
)
from config.settings import settings

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("allow"))
async def cmd_allow(message: Message, db: aiosqlite.Connection):
    """Add a user to the whitelist. Usage: /allow 123456789 [optional note]"""
    if not _is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer(
            "Использование: /allow <user_id> [комментарий]\n"
            "Пример: /allow 123456789 Клиент Иванов"
        )
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("Неверный user_id. Укажите числовой ID пользователя.")
        return

    note = args[2] if len(args) > 2 else None
    added = await add_to_whitelist(db, target_id, message.from_user.id, note)

    if added:
        await message.answer(f"Пользователь {target_id} добавлен в белый список.")
    else:
        await message.answer(f"Пользователь {target_id} уже в белом списке.")


@router.message(Command("deny"))
async def cmd_deny(message: Message, db: aiosqlite.Connection):
    """Remove a user from the whitelist. Usage: /deny 123456789"""
    if not _is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /deny <user_id>")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("Неверный user_id. Укажите числовой ID пользователя.")
        return

    removed = await remove_from_whitelist(db, target_id)

    if removed:
        await message.answer(f"Пользователь {target_id} удалён из белого списка.")
    else:
        await message.answer(f"Пользователь {target_id} не найден в белом списке.")


@router.message(Command("whitelist"))
async def cmd_whitelist(message: Message, db: aiosqlite.Connection):
    """Show the current whitelist."""
    if not _is_admin(message.from_user.id):
        return

    users = await get_whitelist(db)

    if not users:
        await message.answer("Белый список пуст.")
        return

    lines = []
    for u in users:
        name = u["username"] or u["first_name"] or "—"
        note = f" ({u['note']})" if u["note"] else ""
        lines.append(f"• {u['user_id']} — @{name}{note}")

    await message.answer("Белый список:\n\n" + "\n".join(lines))


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    """Show the user's Telegram ID (useful for whitelist setup)."""
    await message.answer(f"Ваш Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")
