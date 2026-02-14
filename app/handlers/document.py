import logging

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.database.repositories.document_repo import get_user_documents, save_document
from app.keyboards.inline import build_confirm_keyboard, build_template_keyboard
from app.lexicon.ru import LEXICON_RU
from app.services.document_service import DocumentService
from app.services.template_registry import TemplateRegistry
from app.states.document import DocumentCreation

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("newdoc"))
async def cmd_newdoc(
    message: Message,
    state: FSMContext,
    template_registry: TemplateRegistry,
):
    templates = template_registry.list_templates()
    if not templates:
        await message.answer(LEXICON_RU["no_templates"])
        return

    keyboard = build_template_keyboard(templates)
    await message.answer(LEXICON_RU["choose_template"], reply_markup=keyboard)
    await state.set_state(DocumentCreation.choosing_template)


@router.message(Command("templates"))
async def cmd_templates(message: Message, template_registry: TemplateRegistry):
    templates = template_registry.list_templates()
    if not templates:
        await message.answer(LEXICON_RU["no_templates"])
        return

    lines = [f"• {tmpl['display_name']}" for tmpl in templates]
    await message.answer("Доступные шаблоны:\n\n" + "\n".join(lines))


@router.message(Command("history"))
async def cmd_history(message: Message, db: aiosqlite.Connection):
    docs = await get_user_documents(db, message.from_user.id)
    if not docs:
        await message.answer(LEXICON_RU["no_history"])
        return

    lines = [
        f"{i}. {doc['template_name']} — {doc['created_at']}"
        for i, doc in enumerate(docs, 1)
    ]
    await message.answer(LEXICON_RU["history_header"] + "\n".join(lines))


# --- FSM: Template selection ---


@router.callback_query(
    DocumentCreation.choosing_template, F.data.startswith("template:")
)
async def template_chosen(
    callback: CallbackQuery,
    state: FSMContext,
    template_registry: TemplateRegistry,
):
    template_id = callback.data.split(":")[1]
    meta = template_registry.get_template_meta(template_id)
    if not meta:
        await callback.answer("Шаблон не найден")
        return

    fields = meta["fields"]
    await state.update_data(
        template_id=template_id,
        template_display_name=meta["display_name"],
        template_filename=meta["filename"],
        fields=fields,
        current_field_index=0,
        collected_data={},
    )

    first_field = fields[0]
    await callback.message.answer(first_field["prompt_ru"])
    await state.set_state(DocumentCreation.collecting_requisites)
    await callback.answer()


# --- FSM: Requisite collection ---


@router.message(DocumentCreation.collecting_requisites)
async def collect_requisite(
    message: Message,
    state: FSMContext,
    template_registry: TemplateRegistry,
):
    data = await state.get_data()
    fields = data["fields"]
    idx = data["current_field_index"]
    current_field = fields[idx]

    value = message.text.strip() if message.text else ""

    # Handle "today" default for date fields
    if current_field.get("type") == "date" and current_field.get("default") == "today":
        if value.lower() in ("сегодня", "today", ""):
            from datetime import datetime

            value = datetime.now().strftime("%d.%m.%Y")

    # Validate
    error = template_registry.validate_field(current_field, value)
    if error:
        await message.answer(LEXICON_RU["validation_error"].format(error=error))
        return

    # Store value
    collected = data["collected_data"]
    collected[current_field["key"]] = value

    next_idx = idx + 1
    if next_idx < len(fields):
        # Ask for the next field
        await state.update_data(current_field_index=next_idx, collected_data=collected)
        next_field = fields[next_idx]
        prompt = next_field["prompt_ru"]
        if next_field.get("default") == "today":
            prompt += '\n(Отправьте "сегодня" для текущей даты)'
        await message.answer(prompt)
    else:
        # All fields collected — show confirmation
        await state.update_data(collected_data=collected)
        summary = _format_summary(fields, collected)
        await message.answer(
            LEXICON_RU["confirm_data"].format(summary=summary),
            reply_markup=build_confirm_keyboard(),
        )
        await state.set_state(DocumentCreation.confirming_data)


# --- FSM: Confirmation ---


@router.callback_query(DocumentCreation.confirming_data, F.data == "confirm:yes")
async def confirm_yes(
    callback: CallbackQuery,
    state: FSMContext,
    document_service: DocumentService,
    db: aiosqlite.Connection,
):
    data = await state.get_data()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(LEXICON_RU["generating"])
    await state.set_state(DocumentCreation.generating_document)

    try:
        docx_path, pdf_path = await document_service.generate_document(
            template_filename=data["template_filename"],
            context=data["collected_data"],
            user_id=callback.from_user.id,
        )

        # Save to DB
        await save_document(
            db,
            user_id=callback.from_user.id,
            template_id=data["template_id"],
            template_name=data["template_display_name"],
            context=data["collected_data"],
        )

        # Send PDF
        pdf_file = FSInputFile(
            pdf_path, filename=f"{data['template_display_name']}.pdf"
        )
        await callback.message.answer_document(
            pdf_file, caption=LEXICON_RU["document_ready"]
        )

        # Cleanup temp files
        document_service.cleanup_files(docx_path, pdf_path)

    except Exception:
        logger.exception("Document generation failed")
        await callback.message.answer(LEXICON_RU["generation_error"])

    await state.clear()
    await callback.answer()


@router.callback_query(DocumentCreation.confirming_data, F.data == "confirm:no")
async def confirm_no(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    fields = data["fields"]

    # Reset to first field
    await state.update_data(current_field_index=0, collected_data={})
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Давайте заполним заново.\n\n" + fields[0]["prompt_ru"]
    )
    await state.set_state(DocumentCreation.collecting_requisites)
    await callback.answer()


@router.callback_query(DocumentCreation.confirming_data, F.data == "confirm:cancel")
async def confirm_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(LEXICON_RU["cancelled"])
    await callback.answer()


# --- Helpers ---


def _format_summary(fields: list[dict], collected: dict) -> str:
    lines = []
    for field in fields:
        value = collected.get(field["key"], "—")
        lines.append(f"• {field['label']}: {value}")
    return "\n".join(lines)
