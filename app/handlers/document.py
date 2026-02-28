import logging
import os
import uuid
from collections import OrderedDict
from datetime import datetime

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.services.openai_service import OpenAIService
from config.settings import settings

from app.database.repositories.document_repo import get_user_documents, save_document
from app.database.repositories.user_requisites_repo import get_user_requisites
from app.database.repositories.user_template_repo import (
    delete_user_template,
    get_user_template_by_id,
    get_user_templates,
)
from app.keyboards.inline import (
    build_after_generation_keyboard,
    build_ai_queries_keyboard,
    build_confirm_keyboard,
    build_edit_fields_keyboard,
    build_field_nav_keyboard,
    build_keep_value_keyboard,
    build_template_keyboard,
)
from app.keyboards.reply import (
    BTN_HISTORY,
    BTN_MY_TEMPLATES,
    BTN_NEW_DOC,
    REMOVE_KEYBOARD,
    main_menu_keyboard,
)
from app.lexicon.ru import LEXICON_RU
from app.services.document_service import DocumentService
from app.services.template_registry import TemplateRegistry
from app.states.document import DocumentCreation

logger = logging.getLogger(__name__)

router = Router()


# ---------------------------------------------------------------------------
# /newdoc — start document creation
# ---------------------------------------------------------------------------


@router.message(Command("newdoc"))
@router.message(F.text == BTN_NEW_DOC)
async def cmd_newdoc(
    message: Message,
    state: FSMContext,
    template_registry: TemplateRegistry,
    db: aiosqlite.Connection,
):
    # Global templates
    templates = template_registry.list_templates()

    # User's personal templates
    user_templates = await get_user_templates(db, message.from_user.id)
    personal = [
        {"id": f"user:{ut['id']}", "display_name": ut["template_name"]}
        for ut in user_templates
    ]

    if not templates and not personal:
        await message.answer(LEXICON_RU["no_templates"])
        return

    keyboard = build_template_keyboard(templates, personal if personal else None)
    await message.answer(
        LEXICON_RU["choose_template"],
        reply_markup=keyboard,
    )
    await state.set_state(DocumentCreation.choosing_template)


# ---------------------------------------------------------------------------
# /history
# ---------------------------------------------------------------------------


@router.message(Command("history"))
@router.message(F.text == BTN_HISTORY)
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


# ---------------------------------------------------------------------------
# /mytemplates, /deltemplate
# ---------------------------------------------------------------------------


@router.message(Command("mytemplates"))
@router.message(F.text == BTN_MY_TEMPLATES)
async def cmd_mytemplates(message: Message, db: aiosqlite.Connection):
    templates = await get_user_templates(db, message.from_user.id)
    if not templates:
        await message.answer(
            "📁 У вас пока нет личных шаблонов.\n\n"
            "📎 Отправьте мне заполненный .docx файл — я создам из него шаблон."
        )
        return

    lines = []
    for t in templates:
        fields_count = len(t["fields"])
        lines.append(
            f"• [{t['id']}] {t['template_name']} ({fields_count} полей)"
        )

    await message.answer(
        "📁 Ваши шаблоны:\n\n"
        + "\n".join(lines)
        + "\n\nУдалить: /deltemplate <id>"
    )


@router.message(Command("deltemplate"))
async def cmd_deltemplate(message: Message, db: aiosqlite.Connection):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /deltemplate <id>")
        return

    try:
        template_id = int(args[1])
    except ValueError:
        await message.answer("Укажите числовой ID шаблона.")
        return

    deleted = await delete_user_template(db, template_id, message.from_user.id)
    if deleted:
        await message.answer(f"✅ Шаблон #{template_id} удалён.")
    else:
        await message.answer("⚠️ Шаблон не найден или не принадлежит вам.")


# ---------------------------------------------------------------------------
# FSM: Template selection
# ---------------------------------------------------------------------------


@router.callback_query(
    DocumentCreation.choosing_template, F.data.startswith("template:")
)
async def template_chosen(
    callback: CallbackQuery,
    state: FSMContext,
    template_registry: TemplateRegistry,
    db: aiosqlite.Connection,
):
    raw_id = callback.data.split(":", 1)[1]

    # Check if it's a user template (format: "user:123")
    if raw_id.startswith("user:"):
        user_template_id = int(raw_id.split(":")[1])
        ut = await get_user_template_by_id(db, user_template_id, callback.from_user.id)
        if not ut:
            await callback.answer("Шаблон не найден")
            return

        fields = ut["fields"]
        await state.update_data(
            template_id=f"user:{ut['id']}",
            template_display_name=ut["template_name"],
            template_filename=ut["filename"],
            fields=fields,
            current_field_index=0,
            collected_data={},
            skipped_fields=[],
        )
    else:
        # Global template
        meta = template_registry.get_template_meta(raw_id)
        if not meta:
            await callback.answer("Шаблон не найден")
            return

        fields = meta["fields"]
        await state.update_data(
            template_id=raw_id,
            template_display_name=meta["display_name"],
            template_filename=meta["filename"],
            fields=fields,
            current_field_index=0,
            collected_data={},
            skipped_fields=[],
        )

    await callback.message.edit_reply_markup(reply_markup=None)

    # Auto-fill executor fields from saved requisites
    saved_req = await get_user_requisites(db, callback.from_user.id)
    auto_filled_count = 0
    collected: dict = {}
    if saved_req:
        from app.services.requisite_parser import map_requisites_to_fields

        executor_mapped = map_requisites_to_fields(saved_req, fields, "executor")
        if executor_mapped:
            collected.update(executor_mapped)
            auto_filled_count = len(executor_mapped)

    # Pre-fill auto-generated fields (contract_number, dates, city, etc.)
    for field in fields:
        auto = field.get("auto")
        if not auto:
            continue
        if auto == "contract_number":
            doc_count = await _count_user_documents(db, callback.from_user.id)
            num = doc_count + 1
            collected[field["key"]] = f"{num:02d}/{datetime.now().strftime('%m-%Y')}"
        elif auto == "today":
            collected[field["key"]] = datetime.now().strftime("%d.%m.%Y")
        elif auto == "today_ru":
            collected[field["key"]] = _format_date_ru(datetime.now())
        elif auto == "executor_city" and saved_req:
            city = _extract_city(saved_req.get("legal_address", ""))
            if city:
                collected[field["key"]] = city
        elif auto == "static" and field.get("auto_value"):
            collected[field["key"]] = field["auto_value"]

    if collected:
        await state.update_data(collected_data=collected)

    # Find first unfilled field
    first_idx = _next_unfilled_index(fields, collected, 0)

    if auto_filled_count:
        await callback.message.answer(
            LEXICON_RU["executor_auto_filled"].format(count=auto_filled_count)
        )

    if first_idx is not None:
        await state.update_data(current_field_index=first_idx)
        await _send_field_prompt(callback.message, state, fields, first_idx)
    else:
        # All fields filled
        await _show_confirmation(callback.message, state)

    await state.set_state(DocumentCreation.collecting_requisites)
    await callback.answer()


# ---------------------------------------------------------------------------
# Ignore "noop" callback (section headers)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


# ---------------------------------------------------------------------------
# FSM: Field navigation (back / cancel) via inline buttons
# ---------------------------------------------------------------------------


@router.callback_query(
    DocumentCreation.collecting_requisites, F.data == "field:back"
)
async def field_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data["current_field_index"]
    if idx <= 0:
        await callback.answer("Это первое поле")
        return

    new_idx = idx - 1
    await state.update_data(current_field_index=new_idx)
    fields = data["fields"]
    collected = data["collected_data"]
    skipped = set(data.get("skipped_fields", []))
    field = fields[new_idx]
    if field["key"] in skipped:
        prev_value = "(пропущено)"
    else:
        prev_value = collected.get(field["key"])

    await callback.message.edit_reply_markup(reply_markup=None)
    await _send_field_prompt_back(
        callback.message, state, fields, new_idx, prev_value
    )
    await callback.answer()


@router.callback_query(
    DocumentCreation.collecting_requisites, F.data == "field:cancel"
)
@router.callback_query(
    DocumentCreation.editing_field, F.data == "field:cancel"
)
async def field_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        LEXICON_RU["cancelled"],
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    DocumentCreation.collecting_requisites, F.data == "field:keep"
)
async def field_keep(callback: CallbackQuery, state: FSMContext):
    """Keep current value and move to next field."""
    data = await state.get_data()
    fields = data["fields"]
    idx = data["current_field_index"]
    collected = data.get("collected_data", {})
    skipped = set(data.get("skipped_fields", []))

    await callback.message.edit_reply_markup(reply_markup=None)

    next_idx = _next_unfilled_index(fields, collected, idx + 1, skipped)
    if next_idx is not None:
        await state.update_data(current_field_index=next_idx)
        await _send_field_prompt(callback.message, state, fields, next_idx)
    else:
        # All fields done — show confirmation
        await _show_confirmation(callback.message, state)

    await callback.answer()


@router.callback_query(
    DocumentCreation.collecting_requisites, F.data == "field:skip"
)
async def field_skip(callback: CallbackQuery, state: FSMContext):
    """Skip an optional field and move to the next one."""
    data = await state.get_data()
    fields = data["fields"]
    idx = data["current_field_index"]
    field = fields[idx]

    if field.get("required", True):
        await callback.answer("Это поле обязательно")
        return

    skipped = set(data.get("skipped_fields", []))
    skipped.add(field["key"])
    collected = data.get("collected_data", {})
    collected.pop(field["key"], None)

    await callback.message.edit_reply_markup(reply_markup=None)

    next_idx = _next_unfilled_index(fields, collected, idx + 1, skipped)
    if next_idx is not None:
        await state.update_data(
            current_field_index=next_idx,
            skipped_fields=list(skipped),
            collected_data=collected,
        )
        await _send_field_prompt(callback.message, state, fields, next_idx)
    else:
        await state.update_data(skipped_fields=list(skipped), collected_data=collected)
        await _show_confirmation(callback.message, state)

    await callback.answer()


# ---------------------------------------------------------------------------
# FSM: File upload for requisite auto-fill
# ---------------------------------------------------------------------------


@router.message(
    DocumentCreation.collecting_requisites,
    F.document.file_name.func(lambda n: n.lower().endswith((".docx", ".pdf"))),
)
async def handle_requisite_file(
    message: Message,
    state: FSMContext,
    bot: Bot,
    openai_service: OpenAIService,
):
    """User uploaded a company card during field collection — parse and auto-fill."""
    file_name = message.document.file_name
    is_pdf = file_name.lower().endswith(".pdf")

    await message.answer(LEXICON_RU["requisite_analyzing"])

    # Download file
    file = await bot.get_file(message.document.file_id)
    ext = ".pdf" if is_pdf else ".docx"
    unique_id = uuid.uuid4().hex[:8]
    temp_path = os.path.join(settings.output_dir, f"req_{unique_id}{ext}")
    await bot.download_file(file.file_path, temp_path)

    try:
        from app.services.requisite_parser import (
            detect_side,
            extract_text_from_docx,
            extract_text_from_pdf,
            map_requisites_to_fields,
        )

        # Extract text
        text = extract_text_from_pdf(temp_path) if is_pdf else extract_text_from_docx(temp_path)

        if len(text.strip()) < 20:
            await message.answer(LEXICON_RU["requisite_empty_file"])
            return

        # AI extraction
        requisites = await openai_service.extract_requisites(text)

        # Map to template fields
        data = await state.get_data()
        fields = data["fields"]
        idx = data["current_field_index"]
        side = detect_side(fields, idx)

        mapped = map_requisites_to_fields(requisites, fields, side)

        if not mapped:
            await message.answer(LEXICON_RU["requisite_no_match"])
            return

        # Pre-fill collected_data
        collected = data["collected_data"]
        collected.update(mapped)

        # Remove auto-filled keys from skipped
        skipped = set(data.get("skipped_fields", []))
        for key in mapped:
            skipped.discard(key)
        await state.update_data(collected_data=collected, skipped_fields=list(skipped))

        # Build summary of filled fields
        filled_lines = []
        for field in fields:
            val = mapped.get(field["key"])
            if val:
                filled_lines.append(f"│ {field['label']}: {val}")
        summary = "\n".join(filled_lines)

        # Find unfilled fields
        first_empty_idx = _next_unfilled_index(fields, collected, 0, skipped)

        if first_empty_idx is not None:
            remaining = sum(
                1 for f in fields
                if f["key"] not in collected
                and not collected.get(f["key"])
                and f["key"] not in skipped
            )
            await state.update_data(current_field_index=first_empty_idx)
            await message.answer(
                LEXICON_RU["requisite_filled"].format(
                    summary=summary, remaining=remaining
                )
            )
            await _send_field_prompt(message, state, fields, first_empty_idx)
        else:
            # All fields filled
            await message.answer(
                LEXICON_RU["requisite_all_filled"].format(summary=summary)
            )
            await _show_confirmation(message, state)

    except Exception:
        logger.exception("Requisite extraction failed")
        await message.answer(LEXICON_RU["requisite_error"])
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# FSM: Requisite collection (text input)
# ---------------------------------------------------------------------------


@router.message(DocumentCreation.collecting_requisites)
async def collect_requisite(
    message: Message,
    state: FSMContext,
    template_registry: TemplateRegistry,
    openai_service: OpenAIService,
):
    data = await state.get_data()
    fields = data["fields"]
    idx = data["current_field_index"]
    current_field = fields[idx]

    value = message.text.strip() if message.text else ""

    # Handle AI query generation: user entered business type
    if current_field.get("auto") == "ai_queries" and not data.get("ai_queries_manual"):
        waiting_msg = await message.answer("🤖 Генерирую запросы...")
        try:
            queries = await openai_service.generate_target_queries(value)
        except Exception as e:
            logger.error("AI query generation failed: %s", e)
            await waiting_msg.delete()
            is_opt = not current_field.get("required", True)
            await message.answer(
                "Не удалось сгенерировать запросы. Попробуйте ещё раз или введите вручную.",
                reply_markup=build_field_nav_keyboard(
                    show_back=idx > 0, show_skip=is_opt
                ),
            )
            return

        await waiting_msg.delete()
        await state.update_data(ai_generated_queries=queries, ai_queries_business=value)
        await message.answer(
            f"🤖 Сгенерированные запросы для «{value}»:\n\n{queries}",
            reply_markup=build_ai_queries_keyboard(),
        )
        return

    # Handle "today" default for date fields
    if current_field.get("type") == "date" and current_field.get("default") == "today":
        if value.lower() in ("сегодня", "today", ""):
            value = datetime.now().strftime("%d.%m.%Y")

    # Handle empty input for optional field as skip
    is_optional = not current_field.get("required", True)
    if not value and is_optional:
        skipped = set(data.get("skipped_fields", []))
        skipped.add(current_field["key"])
        collected = data.get("collected_data", {})
        collected.pop(current_field["key"], None)
        await state.update_data(ai_queries_manual=None)

        next_idx = _next_unfilled_index(fields, collected, idx + 1, skipped)
        if next_idx is not None:
            await state.update_data(
                current_field_index=next_idx, skipped_fields=list(skipped)
            )
            await _send_field_prompt(message, state, fields, next_idx)
        else:
            await state.update_data(skipped_fields=list(skipped))
            await _show_confirmation(message, state)
        return

    # Validate
    error = template_registry.validate_field(current_field, value)
    if error:
        hint = current_field.get("validation_hint", error)
        await message.answer(
            LEXICON_RU["validation_error"].format(hint=hint, value=value),
            reply_markup=build_field_nav_keyboard(
                show_back=idx > 0, show_skip=is_optional
            ),
        )
        return

    # Store value and remove from skipped if it was there
    collected = data["collected_data"]
    collected[current_field["key"]] = value
    skipped = set(data.get("skipped_fields", []))
    skipped.discard(current_field["key"])

    # Clear manual mode flag if it was set
    await state.update_data(ai_queries_manual=None, skipped_fields=list(skipped))

    next_idx = _next_unfilled_index(fields, collected, idx + 1, skipped)
    if next_idx is not None:
        await state.update_data(current_field_index=next_idx, collected_data=collected)
        await _send_field_prompt(message, state, fields, next_idx)
    else:
        # All fields collected — show confirmation
        await state.update_data(collected_data=collected)
        await _show_confirmation(message, state)


# ---------------------------------------------------------------------------
# FSM: AI-generated queries callbacks
# ---------------------------------------------------------------------------


@router.callback_query(
    DocumentCreation.collecting_requisites, F.data == "ai_queries:accept"
)
async def ai_queries_accept(
    callback: CallbackQuery,
    state: FSMContext,
    openai_service: OpenAIService,
):
    """Accept AI-generated queries and move to next field."""
    data = await state.get_data()
    fields = data["fields"]
    idx = data["current_field_index"]
    queries = data.get("ai_generated_queries", "")
    business_type = data.get("ai_queries_business", "")

    collected = data["collected_data"]
    collected[fields[idx]["key"]] = queries

    # Convert business type to genitive case for Appendix 1
    if business_type:
        try:
            genitive = await openai_service.convert_business_type_genitive(
                business_type
            )
            collected["customer_business_type_genitive"] = genitive
        except Exception:
            logger.warning("Failed to convert business type to genitive")

    await callback.message.edit_reply_markup(reply_markup=None)

    skipped = set(data.get("skipped_fields", []))
    next_idx = _next_unfilled_index(fields, collected, idx + 1, skipped)
    if next_idx is not None:
        await state.update_data(
            current_field_index=next_idx,
            collected_data=collected,
            ai_generated_queries=None,
        )
        await _send_field_prompt(callback.message, state, fields, next_idx)
    else:
        await state.update_data(collected_data=collected, ai_generated_queries=None)
        await _show_confirmation(callback.message, state)

    await callback.answer()


@router.callback_query(
    DocumentCreation.collecting_requisites, F.data == "ai_queries:regenerate"
)
async def ai_queries_regenerate(callback: CallbackQuery, state: FSMContext):
    """Re-show the business type prompt for another generation."""
    data = await state.get_data()
    fields = data["fields"]
    idx = data["current_field_index"]

    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(ai_generated_queries=None)
    await _send_field_prompt(callback.message, state, fields, idx)
    await callback.answer()


@router.callback_query(
    DocumentCreation.collecting_requisites, F.data == "ai_queries:manual"
)
async def ai_queries_manual(callback: CallbackQuery, state: FSMContext):
    """Switch to manual text input for queries."""
    data = await state.get_data()
    fields = data["fields"]
    idx = data["current_field_index"]

    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(ai_generated_queries=None, ai_queries_manual=True)

    await callback.message.answer(
        "Введите целевые поисковые запросы вручную (каждый с новой строки, с нумерацией):\n"
        "💡 1. запрос один\n2. запрос два\n3. ...",
        reply_markup=build_field_nav_keyboard(show_back=idx > 0),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# FSM: Confirmation
# ---------------------------------------------------------------------------


@router.callback_query(DocumentCreation.confirming_data, F.data == "confirm:yes")
async def confirm_yes(
    callback: CallbackQuery,
    state: FSMContext,
    document_service: DocumentService,
    db: aiosqlite.Connection,
):
    data = await state.get_data()
    await callback.message.edit_reply_markup(reply_markup=None)

    # Send "generating" message that we'll edit later
    status_msg = await callback.message.answer(
        LEXICON_RU["generating"],
        reply_markup=REMOVE_KEYBOARD,
    )
    await state.set_state(DocumentCreation.generating_document)

    try:
        docx_path = await document_service.generate_document(
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

        # Build short summary for the "ready" message
        details = _build_generation_details(data)

        # Edit the status message to show success
        try:
            await status_msg.edit_text(
                LEXICON_RU["document_ready"].format(
                    template_name=data["template_display_name"],
                    details=details,
                )
            )
        except Exception:
            pass

        # Send DOCX
        docx_file = FSInputFile(
            docx_path, filename=f"{data['template_display_name']}.docx"
        )
        await callback.message.answer_document(
            docx_file,
            reply_markup=build_after_generation_keyboard(),
        )

        # Cleanup temp files
        document_service.cleanup_files(docx_path)

    except Exception:
        logger.exception("Document generation failed")
        try:
            await status_msg.edit_text(LEXICON_RU["generation_error"])
        except Exception:
            await callback.message.answer(LEXICON_RU["generation_error"])

    await state.clear()
    await callback.message.answer(
        LEXICON_RU["what_next"], reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(DocumentCreation.confirming_data, F.data == "confirm:edit")
async def confirm_edit(callback: CallbackQuery, state: FSMContext):
    """Show field selection for editing."""
    data = await state.get_data()
    fields = data["fields"]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        LEXICON_RU["edit_which_field"],
        reply_markup=build_edit_fields_keyboard(fields),
    )
    await callback.answer()


@router.callback_query(DocumentCreation.confirming_data, F.data == "confirm:cancel")
async def confirm_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        LEXICON_RU["cancelled"],
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# FSM: Edit specific field from confirmation
# ---------------------------------------------------------------------------


@router.callback_query(
    DocumentCreation.confirming_data, F.data.startswith("editfield:")
)
async def edit_field_chosen(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]

    if value == "back":
        # Return to confirmation
        await callback.message.edit_reply_markup(reply_markup=None)
        await _show_confirmation(callback.message, state)
        await callback.answer()
        return

    field_idx = int(value)
    data = await state.get_data()
    fields = data["fields"]
    collected = data["collected_data"]
    skipped = set(data.get("skipped_fields", []))
    field = fields[field_idx]

    if field["key"] in skipped:
        current_value = "(пропущено)"
    else:
        current_value = collected.get(field["key"], "")

    await state.update_data(editing_field_index=field_idx)
    await callback.message.edit_reply_markup(reply_markup=None)

    template_name = data["template_display_name"]
    hint = field.get("hint", "")
    hint_line = f"💡 {hint}" if hint else ""

    is_optional = not field.get("required", True)
    if is_optional:
        hint_line += "\nПоле необязательное — можно пропустить"

    text = LEXICON_RU["field_prompt_back"].format(
        template_name=template_name,
        current=field_idx + 1,
        total=len(fields),
        prompt=field["prompt_ru"],
        hint=hint_line,
        value=current_value or "—",
    )
    await callback.message.answer(
        text,
        reply_markup=build_keep_value_keyboard(show_skip=is_optional),
    )
    await state.set_state(DocumentCreation.editing_field)
    await callback.answer()


@router.callback_query(DocumentCreation.editing_field, F.data == "field:keep")
async def editing_field_keep(callback: CallbackQuery, state: FSMContext):
    """Keep current value and return to confirmation."""
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(DocumentCreation.confirming_data)
    await _show_confirmation(callback.message, state)
    await callback.answer()


@router.callback_query(DocumentCreation.editing_field, F.data == "field:skip")
async def editing_field_skip(callback: CallbackQuery, state: FSMContext):
    """Skip this field during editing and return to confirmation."""
    data = await state.get_data()
    field_idx = data["editing_field_index"]
    fields = data["fields"]
    field = fields[field_idx]

    if field.get("required", True):
        await callback.answer("Это поле обязательно")
        return

    skipped = set(data.get("skipped_fields", []))
    skipped.add(field["key"])
    collected = data["collected_data"]
    collected.pop(field["key"], None)

    await state.update_data(
        collected_data=collected, skipped_fields=list(skipped)
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(DocumentCreation.confirming_data)
    await _show_confirmation(callback.message, state)
    await callback.answer()


@router.message(DocumentCreation.editing_field)
async def editing_field_value(
    message: Message,
    state: FSMContext,
    template_registry: TemplateRegistry,
):
    data = await state.get_data()
    field_idx = data["editing_field_index"]
    fields = data["fields"]
    field = fields[field_idx]

    value = message.text.strip() if message.text else ""

    # Handle "today" default for date fields
    if field.get("type") == "date" and field.get("default") == "today":
        if value.lower() in ("сегодня", "today", ""):
            from datetime import datetime

            value = datetime.now().strftime("%d.%m.%Y")

    # Validate
    error = template_registry.validate_field(field, value)
    if error:
        hint = field.get("validation_hint", error)
        await message.answer(
            LEXICON_RU["validation_error"].format(hint=hint, value=value),
        )
        return

    # Store updated value and un-skip if it was skipped
    collected = data["collected_data"]
    collected[field["key"]] = value
    skipped = set(data.get("skipped_fields", []))
    skipped.discard(field["key"])
    await state.update_data(collected_data=collected, skipped_fields=list(skipped))

    # Return to confirmation
    await state.set_state(DocumentCreation.confirming_data)
    await _show_confirmation(message, state)


# ---------------------------------------------------------------------------
# Post-generation inline action: new doc
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "action:newdoc")
async def action_newdoc(
    callback: CallbackQuery,
    state: FSMContext,
    template_registry: TemplateRegistry,
    db: aiosqlite.Connection,
):
    await callback.message.edit_reply_markup(reply_markup=None)
    # Reuse cmd_newdoc logic
    templates = template_registry.list_templates()
    user_templates = await get_user_templates(db, callback.from_user.id)
    personal = [
        {"id": f"user:{ut['id']}", "display_name": ut["template_name"]}
        for ut in user_templates
    ]

    if not templates and not personal:
        await callback.message.answer(LEXICON_RU["no_templates"])
        await callback.answer()
        return

    keyboard = build_template_keyboard(templates, personal if personal else None)
    await callback.message.answer(
        LEXICON_RU["choose_template"],
        reply_markup=keyboard,
    )
    await state.set_state(DocumentCreation.choosing_template)
    await callback.answer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _send_field_prompt(
    message: Message, state: FSMContext, fields: list[dict], idx: int
):
    """Send the prompt for field at given index with progress indicator."""
    data = await state.get_data()
    template_name = data["template_display_name"]
    field = fields[idx]

    hint = field.get("hint", "")
    hint_line = f"💡 {hint}" if hint else ""

    if field.get("default") == "today":
        hint_line += '\n📅 Отправьте «сегодня» для текущей даты'

    # Show file upload hint at the start of a new group with requisite fields
    group = field.get("group", "")
    is_new_group = idx == 0 or (idx > 0 and group != fields[idx - 1].get("group", ""))
    if is_new_group and any(
        kw in group for kw in ("Заказчик", "Плательщик", "Исполнитель", "Получатель", "Стороны")
    ):
        hint_line += LEXICON_RU["requisite_upload_hint"]

    is_optional = not field.get("required", True)
    if is_optional:
        hint_line += "\nПоле необязательное — можно пропустить"

    text = LEXICON_RU["field_prompt"].format(
        template_name=template_name,
        current=idx + 1,
        total=len(fields),
        prompt=field["prompt_ru"],
        hint=hint_line,
    )

    await message.answer(
        text,
        reply_markup=build_field_nav_keyboard(
            show_back=idx > 0, show_skip=is_optional
        ),
    )


async def _send_field_prompt_back(
    message: Message,
    state: FSMContext,
    fields: list[dict],
    idx: int,
    prev_value: str | None,
):
    """Send prompt for going back — shows current value."""
    data = await state.get_data()
    template_name = data["template_display_name"]
    field = fields[idx]

    hint = field.get("hint", "")
    hint_line = f"💡 {hint}" if hint else ""

    is_optional = not field.get("required", True)
    if is_optional:
        hint_line += "\nПоле необязательное — можно пропустить"

    text = LEXICON_RU["field_prompt_back"].format(
        template_name=template_name,
        current=idx + 1,
        total=len(fields),
        prompt=field["prompt_ru"],
        hint=hint_line,
        value=prev_value or "—",
    )

    await message.answer(
        text,
        reply_markup=build_keep_value_keyboard(show_skip=is_optional),
    )


async def _show_confirmation(message: Message, state: FSMContext):
    """Show grouped confirmation summary."""
    data = await state.get_data()
    fields = data["fields"]
    collected = data["collected_data"]
    template_name = data["template_display_name"]
    skipped = set(data.get("skipped_fields", []))

    summary = _format_grouped_summary(fields, collected, skipped)

    await message.answer(
        LEXICON_RU["confirm_data"].format(
            template_name=template_name, summary=summary
        ),
        reply_markup=build_confirm_keyboard(),
    )
    await state.set_state(DocumentCreation.confirming_data)


def _format_grouped_summary(
    fields: list[dict],
    collected: dict,
    skipped_fields: set | None = None,
) -> str:
    """Format fields into grouped display with box-drawing characters."""
    skipped = skipped_fields or set()
    groups: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
    for field in fields:
        group = field.get("group", "Данные")
        key = field["key"]
        if key in skipped:
            value = "(пропущено)"
        else:
            value = collected.get(key, "—")
        if group not in groups:
            groups[group] = []
        groups[group].append((field["label"], value))

    lines = []
    group_list = list(groups.items())
    for i, (group_name, entries) in enumerate(group_list):
        is_last = i == len(group_list) - 1
        prefix = "└" if is_last else "┌" if i == 0 else "├"
        lines.append(f"{prefix} {group_name}")

        for label, value in entries:
            lines.append(f"│ {label}: {value}")

        if not is_last:
            lines.append("│")

    return "\n".join(lines)


_MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _format_date_ru(dt: datetime) -> str:
    """Format datetime as «DD» месяца YYYY г."""
    return f"\u00ab{dt.day:02d}\u00bb {_MONTHS_RU[dt.month]} {dt.year} г."


def _extract_city(address: str) -> str | None:
    """Try to extract city from a Russian address string like '354004, Россия, ..., г. Сочи, ...'"""
    import re
    # Match "г. CityName" pattern
    m = re.search(r"г\.\s*([^,]+)", address)
    if m:
        return f"г. {m.group(1).strip()}"
    return None


def _next_unfilled_index(
    fields: list[dict],
    collected: dict,
    start: int,
    skipped_fields: set | None = None,
) -> int | None:
    """Return the index of the next field that has no value in collected, or None."""
    skipped = skipped_fields or set()
    for i in range(start, len(fields)):
        key = fields[i]["key"]
        if key in skipped:
            continue
        if key not in collected or not collected[key]:
            return i
    return None


async def _count_user_documents(db: aiosqlite.Connection, user_id: int) -> int:
    """Count total documents generated by a user."""
    cursor = await db.execute(
        "SELECT COUNT(*) FROM generated_documents WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


def _build_generation_details(data: dict) -> str:
    """Build a short detail line for the generation success message."""
    collected = data.get("collected_data", {})
    parts = []

    # Try to show executor/client names
    for key in ("executor_name", "executor_full_name", "client_name", "customer_company_name"):
        val = collected.get(key)
        if val:
            # Shorten to last name + initial
            name_parts = val.split()
            if len(name_parts) >= 2:
                parts.append(f"{name_parts[0]} {name_parts[1][0]}.")
            else:
                parts.append(val)

    detail = " ↔ ".join(parts) if parts else ""

    # Try to show amount
    for key in ("contract_amount", "amount", "first_period_cost"):
        val = collected.get(key)
        if val:
            detail += f"\nСумма: {val} руб."
            break

    return detail
