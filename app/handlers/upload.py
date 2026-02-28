import logging
import os
import shutil
import uuid

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from docxtpl import DocxTemplate

from app.states.document import DocumentCreation, RequisitesSetup

from app.database.repositories.user_template_repo import save_user_template
from app.services.openai_service import OpenAIService
from config.settings import settings

logger = logging.getLogger(__name__)

router = Router()


@router.message(
    F.document.file_name.endswith(".docx"),
    ~StateFilter(DocumentCreation.collecting_requisites, RequisitesSetup.waiting_for_file),
)
async def handle_docx_upload(
    message: Message,
    bot: Bot,
    openai_service: OpenAIService,
    db: aiosqlite.Connection,
):
    """Handle .docx upload: scan for {{ }} placeholders and create a user template."""

    # Download file
    file = await bot.get_file(message.document.file_id)
    unique_id = uuid.uuid4().hex[:8]
    temp_path = os.path.join(settings.output_dir, f"upload_{unique_id}.docx")

    await bot.download_file(file.file_path, temp_path)

    try:
        # Scan for {{ }} placeholders using docxtpl
        doc = DocxTemplate(temp_path)
        variables = doc.get_undeclared_template_variables()

        if not variables:
            await message.answer(
                "В документе не найдены плейсхолдеры {{ }}.\n\n"
                "📝 Как создать шаблон:\n"
                "1. Откройте .docx в Word\n"
                "2. Замените конкретные данные на плейсхолдеры:\n"
                "   • ФИО → {{ executor_name }}\n"
                "   • ИНН → {{ executor_inn }}\n"
                "   • Сумма → {{ amount }}\n"
                "   • Адрес → {{ address }}\n"
                "3. Сохраните и отправьте файл повторно\n\n"
                "💡 Используйте латинские snake_case имена"
            )
            return

        sorted_vars = sorted(variables)
        logger.info("Found %d template variables: %s", len(sorted_vars), sorted_vars)

        # Use AI to generate Russian labels for variable names
        await message.answer("🔍 Найдено полей: %d. Генерирую описания..." % len(sorted_vars))

        try:
            labels = await openai_service.generate_field_labels(sorted_vars)
        except Exception:
            logger.exception("AI label generation failed, using defaults")
            labels = {}

        # Build field metadata
        fields = []
        for var_name in sorted_vars:
            ai_info = labels.get(var_name, {})
            fields.append({
                "key": var_name,
                "label": ai_info.get("label", var_name.replace("_", " ").title()),
                "prompt_ru": ai_info.get("prompt_ru", f"Введите {var_name}:"),
                "type": ai_info.get("type", "string"),
                "required": True,
            })

        # Copy .docx as-is to templates directory (no modification needed!)
        user_id = message.from_user.id
        template_filename = f"user_{user_id}_{unique_id}.docx"
        template_path = os.path.join(settings.templates_dir, template_filename)
        shutil.copy2(temp_path, template_path)

        # Generate template name from filename or AI
        original_name = message.document.file_name or "Шаблон"
        template_name = original_name.rsplit(".", 1)[0]

        # Save to DB
        await save_user_template(
            db,
            user_id=user_id,
            template_name=template_name,
            filename=template_filename,
            fields=fields,
        )

        # Format response
        fields_list = "\n".join(f"  • {f['label']}" for f in fields)
        await message.answer(
            f"✅ Шаблон создан: «{template_name}»\n\n"
            f"Найденные поля ({len(fields)}):\n{fields_list}\n\n"
            f"Теперь вы можете использовать его через /newdoc\n"
            f"Для управления шаблонами: /mytemplates"
        )

    except Exception:
        logger.exception("Template upload failed")
        await message.answer(
            "❌ Ошибка при обработке документа. "
            "Убедитесь, что файл — корректный .docx документ."
        )
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
