from aiogram.fsm.state import State, StatesGroup


class DocumentCreation(StatesGroup):
    choosing_template = State()
    collecting_requisites = State()
    confirming_data = State()
    editing_field = State()
    generating_document = State()


class RequisitesSetup(StatesGroup):
    waiting_for_file = State()
    confirming = State()
