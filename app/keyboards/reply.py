from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

# Button labels — used both for keyboard and text matching in handlers
BTN_NEW_DOC = "📝 Новый документ"
BTN_MY_TEMPLATES = "📁 Мои шаблоны"
BTN_MY_REQUISITES = "🏢 Мои реквизиты"
BTN_HISTORY = "📋 История"
BTN_HELP = "❓ Помощь"
BTN_CANCEL = "Отмена"

# Keep old constant for backward compat in handler filters
BTN_TEMPLATES = "Шаблоны"

REMOVE_KEYBOARD = ReplyKeyboardRemove()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEW_DOC), KeyboardButton(text=BTN_MY_TEMPLATES)],
            [KeyboardButton(text=BTN_MY_REQUISITES), KeyboardButton(text=BTN_HISTORY)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )
