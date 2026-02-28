import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.database.repositories.user_requisites_repo import get_user_requisites
from app.keyboards.reply import BTN_CANCEL, BTN_HELP, main_menu_keyboard
from app.lexicon.ru import LEXICON_RU

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: aiosqlite.Connection):
    await state.clear()
    await message.answer(
        LEXICON_RU["start"],
        reply_markup=main_menu_keyboard(),
    )

    # Check if user has requisites set up
    requisites = await get_user_requisites(db, message.from_user.id)
    if not requisites:
        await message.answer(LEXICON_RU["requisites_not_set"])


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message):
    await message.answer(LEXICON_RU["help"])


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(
            LEXICON_RU["cancelled"],
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(LEXICON_RU["nothing_to_cancel"])
