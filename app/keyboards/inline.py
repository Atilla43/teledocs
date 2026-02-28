from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_template_keyboard(
    global_templates: list[dict],
    personal_templates: list[dict] | None = None,
) -> InlineKeyboardMarkup:
    buttons = []

    if global_templates:
        for tmpl in global_templates:
            icon = tmpl.get("icon", "📄")
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{icon} {tmpl['display_name']}",
                        callback_data=f"template:{tmpl['id']}",
                    )
                ]
            )

    if personal_templates:
        buttons.append(
            [InlineKeyboardButton(text="📌 Ваши шаблоны:", callback_data="noop")]
        )
        for tmpl in personal_templates:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"📎 {tmpl['display_name']}",
                        callback_data=f"template:{tmpl['id']}",
                    )
                ]
            )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_field_nav_keyboard(
    show_back: bool = False, show_skip: bool = False
) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    if show_back:
        row.append(InlineKeyboardButton(text="↩️ Назад", callback_data="field:back"))
    if show_skip:
        row.append(
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="field:skip")
        )
    row.append(InlineKeyboardButton(text="❌ Отмена", callback_data="field:cancel"))
    buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_keep_value_keyboard(show_skip: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Оставить текущее", callback_data="field:keep")],
    ]
    if show_skip:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить", callback_data="field:skip"
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="field:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Создать документ", callback_data="confirm:yes"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить", callback_data="confirm:edit"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="confirm:cancel"
                ),
            ],
        ]
    )


def build_edit_fields_keyboard(fields: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, field in enumerate(fields):
        row.append(
            InlineKeyboardButton(
                text=field["label"],
                callback_data=f"editfield:{i}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append(
        [InlineKeyboardButton(text="↩️ Назад к подтверждению", callback_data="editfield:back")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_requisites_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сохранить", callback_data="reqsetup:save"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Загрузить другой файл", callback_data="reqsetup:retry"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="reqsetup:cancel"
                ),
            ],
        ]
    )


def build_ai_queries_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять", callback_data="ai_queries:accept"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Перегенерировать",
                    callback_data="ai_queries:regenerate",
                ),
                InlineKeyboardButton(
                    text="✏️ Ввести вручную",
                    callback_data="ai_queries:manual",
                ),
            ],
        ]
    )


def build_after_generation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Новый документ", callback_data="action:newdoc"
                ),
            ],
        ]
    )
