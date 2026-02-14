from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.lexicon.ru import LEXICON_RU

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(LEXICON_RU["start"])


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(LEXICON_RU["help"])


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(LEXICON_RU["cancelled"])
    else:
        await message.answer(LEXICON_RU["nothing_to_cancel"])
