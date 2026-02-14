from aiogram.fsm.state import State, StatesGroup


class DocumentCreation(StatesGroup):
    choosing_template = State()
    collecting_requisites = State()
    confirming_data = State()
    generating_document = State()
