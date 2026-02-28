"""Handler for user requisites setup — save executor info once, reuse in all documents."""

import logging
import os
import uuid

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database.repositories.user_requisites_repo import (
    delete_user_requisites,
    get_user_requisites,
    save_user_requisites,
)
from app.keyboards.inline import build_requisites_confirm_keyboard
from app.keyboards.reply import BTN_MY_REQUISITES, main_menu_keyboard
from app.lexicon.ru import LEXICON_RU
from app.services.openai_service import OpenAIService
from app.services.requisite_parser import format_requisites_summary
from app.states.document import RequisitesSetup
from config.settings import settings

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("myrequisites"))
@router.message(F.text == BTN_MY_REQUISITES)
async def cmd_my_requisites(message: Message, state: FSMContext, db: aiosqlite.Connection):
    """Show current requisites or prompt to set them up."""
    await state.clear()
    requisites = await get_user_requisites(db, message.from_user.id)

    if requisites:
        summary = format_requisites_summary(requisites)
        await message.answer(
            f"🏢 Ваши реквизиты:\n\n{summary}\n\n"
            "Чтобы обновить — отправьте новую карточку предприятия (.docx / .pdf)\n"
            "Удалить: /clearrequisites"
        )
        await state.set_state(RequisitesSetup.waiting_for_file)
    else:
        await message.answer(LEXICON_RU["requisites_not_set"])
        await state.set_state(RequisitesSetup.waiting_for_file)


@router.message(Command("clearrequisites"))
async def cmd_clear_requisites(message: Message, db: aiosqlite.Connection):
    """Delete saved requisites."""
    deleted = await delete_user_requisites(db, message.from_user.id)
    if deleted:
        await message.answer("✅ Реквизиты удалены.")
    else:
        await message.answer("У вас нет сохранённых реквизитов.")


# --- FSM: waiting for file ---


@router.message(
    RequisitesSetup.waiting_for_file,
    F.document.file_name.func(lambda n: n.lower().endswith((".docx", ".pdf"))),
)
async def requisites_file_upload(
    message: Message,
    state: FSMContext,
    bot: Bot,
    openai_service: OpenAIService,
):
    """Parse uploaded company card for requisites setup."""
    file_name = message.document.file_name
    is_pdf = file_name.lower().endswith(".pdf")

    await message.answer(LEXICON_RU["requisite_analyzing"])

    file = await bot.get_file(message.document.file_id)
    ext = ".pdf" if is_pdf else ".docx"
    unique_id = uuid.uuid4().hex[:8]
    temp_path = os.path.join(settings.output_dir, f"reqsetup_{unique_id}{ext}")
    await bot.download_file(file.file_path, temp_path)

    try:
        from app.services.requisite_parser import (
            extract_text_from_docx,
            extract_text_from_pdf,
        )

        text = extract_text_from_pdf(temp_path) if is_pdf else extract_text_from_docx(temp_path)

        if len(text.strip()) < 20:
            await message.answer(LEXICON_RU["requisite_empty_file"])
            return

        requisites = await openai_service.extract_requisites(text)

        if not requisites:
            await message.answer(LEXICON_RU["requisite_no_match"])
            return

        # Store parsed requisites in FSM for confirmation
        await state.update_data(parsed_requisites=requisites)

        summary = format_requisites_summary(requisites)
        await message.answer(
            f"🏢 Найденные реквизиты:\n\n{summary}\n\nСохранить?",
            reply_markup=build_requisites_confirm_keyboard(),
        )
        await state.set_state(RequisitesSetup.confirming)

    except Exception:
        logger.exception("Requisite setup parsing failed")
        await message.answer(LEXICON_RU["requisite_error"])
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


@router.message(RequisitesSetup.waiting_for_file)
async def requisites_waiting_text(message: Message):
    """User sent text instead of file."""
    await message.answer(
        "📎 Отправьте файл с реквизитами (.docx или .pdf).\n"
        "Или нажмите /cancel для отмены."
    )


# --- FSM: confirming parsed requisites ---


@router.callback_query(RequisitesSetup.confirming, F.data == "reqsetup:save")
async def requisites_save(
    callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection
):
    data = await state.get_data()
    requisites = data["parsed_requisites"]

    await save_user_requisites(db, callback.from_user.id, requisites)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ Реквизиты сохранены! Они будут автоматически подставляться при создании документов.",
        reply_markup=main_menu_keyboard(),
    )
    await state.clear()
    await callback.answer()


@router.callback_query(RequisitesSetup.confirming, F.data == "reqsetup:retry")
async def requisites_retry(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📎 Отправьте другой файл с реквизитами (.docx или .pdf)."
    )
    await state.set_state(RequisitesSetup.waiting_for_file)
    await callback.answer()


@router.callback_query(RequisitesSetup.confirming, F.data == "reqsetup:cancel")
async def requisites_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        LEXICON_RU["cancelled"],
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
