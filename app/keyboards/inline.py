from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_template_keyboard(templates: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=tmpl["display_name"],
                callback_data=f"template:{tmpl['id']}",
            )
        ]
        for tmpl in templates
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, всё верно", callback_data="confirm:yes"),
                InlineKeyboardButton(text="Нет, изменить", callback_data="confirm:no"),
            ],
            [
                InlineKeyboardButton(text="Отменить", callback_data="confirm:cancel"),
            ],
        ]
    )
